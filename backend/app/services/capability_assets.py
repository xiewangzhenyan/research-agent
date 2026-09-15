"""CRUD with server-owned scope, optimistic revisions and write-only secrets."""

import hashlib
import json
from datetime import UTC, datetime

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import delete, func, or_, select

from app.core.config import settings
from app.core.exceptions import (
    AlreadyExistsError,
    AuthorizationError,
    BadRequestError,
    NotFoundError,
    RateLimitError,
)
from app.db.models.capability import CapabilityAsset as Asset
from app.db.models.capability import CapabilityAudit, SkillVersion
from app.db.models.capability import CapabilityBinding as Binding
from app.db.models.user import User
from app.schemas.capability import MCPConfig
from app.services.project import ProjectService
from app.services.skill_packages import MAX_EXPANDED, MAX_FILE, manifest, package_digest, safe_path
from app.services.skill_storage import get_skill_storage


def cryptor():
    try:
        return Fernet(settings.CAPABILITY_ENCRYPTION_KEY.get_secret_value().encode())
    except (ValueError, TypeError) as exc:
        raise BadRequestError(message="服务端尚未配置能力凭据加密密钥，请联系管理员") from exc


def seal(owner, asset_id, values):
    if not values:
        return None
    body = {"owner": str(owner), "asset": str(asset_id), "values": values}
    return cryptor().encrypt(json.dumps(body).encode()).decode()


def unseal(asset):
    if not asset.secret:
        return {}
    try:
        body = json.loads(cryptor().decrypt(asset.secret.encode()))
        if body["owner"] != str(asset.owner_id) or body["asset"] != str(asset.id):
            raise ValueError("scope")
        return body["values"]
    except (InvalidToken, ValueError, KeyError) as exc:
        raise BadRequestError(message="连接凭据不可用，请重新配置") from exc


class CapabilityService:
    def __init__(self, db, user, project_id=None):
        self.db, self.user, self.project_id = db, user, project_id

    def visible(self):
        return or_(Asset.owner_id == self.user.id, Asset.scope == "system")

    async def get(self, asset_id, *, write=False):
        stmt = select(Asset).where(Asset.id == asset_id, self.visible())
        if write:
            stmt = stmt.with_for_update()
        asset = await self.db.scalar(stmt)
        if not asset or (write and asset.owner_id != self.user.id and not self.user.is_app_admin):
            raise NotFoundError(message="能力不存在或没有访问权限")
        if write and asset.scope == "system" and not self.user.is_app_admin:
            raise AuthorizationError(message="仅管理员可管理系统能力")
        return asset

    def usable(self, asset):
        return asset.scope == "system" or (
            asset.owner_id == self.user.id
            and (asset.scope == "personal" or asset.project_id == self.project_id)
        )

    def public(self, asset, *, detail=False):
        config = dict(asset.config)
        if asset.kind == "skill":
            files = config.get("files", {})
            config = {
                "files": [
                    {"path": p, "size": f["size"], "sha256": f["sha256"]} for p, f in files.items()
                ]
            }
            if detail:
                config["entry"] = asset.config.get("entry", "")
        return {
            "id": str(asset.id),
            "kind": asset.kind,
            "name": asset.name,
            "description": asset.description,
            "scope": asset.scope,
            "project_id": str(asset.project_id) if asset.project_id else None,
            "tags": asset.tags,
            "enabled": asset.enabled,
            "revision": asset.revision,
            "config": config,
            "has_credentials": bool(asset.secret),
            "catalog": asset.catalog,
            "status": asset.status,
            "status_message": asset.status_message,
            "last_tested": asset.tested_at,
            "published_version": asset.published_version,
            "can_edit": asset.owner_id == self.user.id or self.user.is_app_admin,
            "can_bind": self.usable(asset),
            "updated_at": (asset.updated_at or asset.created_at).isoformat(),
        }

    async def audit(self, asset, action):
        self.db.add(
            CapabilityAudit(
                user_id=self.user.id,
                asset_id=asset.id,
                action=action,
                revision=asset.revision,
                timestamp=datetime.now(UTC).isoformat(),
            )
        )

    async def list(self, kind):
        rows = await self.db.scalars(
            select(Asset)
            .where(self.visible(), Asset.kind == kind)
            .order_by(Asset.created_at.desc())
            .limit(200)
        )
        return [self.public(a) for a in rows]

    @staticmethod
    def check_revision(asset, revision):
        if revision != asset.revision:
            raise AlreadyExistsError(message="内容已在另一个窗口更新，请刷新后重试")

    async def store_files(self, asset, members):
        files = {}
        storage = get_skill_storage()
        for path, content in members.items():
            safe_path(path)
            digest = hashlib.sha256(content).hexdigest()
            old = asset.config.get("files", {}).get(path)
            if old and old["sha256"] == digest:
                files[path] = old
            else:
                location = await storage.save(
                    str(asset.owner_id), f"skill-{asset.id}-{digest}", content
                )
                files[path] = {"storage": location, "sha256": digest, "size": len(content)}
        return {"entry": members["SKILL.md"].decode(), "files": files}

    async def save(self, kind, data, asset_id=None, *, members=None):
        await self.db.scalar(select(User.id).where(User.id == self.user.id).with_for_update())
        if data.scope == "system" and not self.user.is_app_admin:
            raise AuthorizationError(message="仅管理员可管理系统能力")
        if data.scope == "project" and self.project_id is None:
            raise BadRequestError(message="请先选择具名项目，再创建项目级能力")
        await ProjectService(self.db, self.user.id).validate(self.project_id)
        if asset_id:
            asset = await self.get(asset_id, write=True)
            if asset.kind != kind:
                raise BadRequestError(message="能力类型不匹配")
            self.check_revision(asset, data.revision)
            if asset.scope == data.scope == "project" and asset.project_id != self.project_id:
                raise BadRequestError(message="请切换到能力所属项目后编辑")
        else:
            count = await self.db.scalar(
                select(func.count()).select_from(Asset).where(Asset.owner_id == self.user.id)
            )
            if count >= 100:
                raise RateLimitError(message="每个账号最多管理 100 项自定义能力")
            asset = Asset(
                owner_id=self.user.id,
                kind=kind,
                scope=data.scope,
                name=data.name,
                config={},
                revision=0,
            )
            self.db.add(asset)
            await self.db.flush()
        old_config = asset.config
        if kind == "mcp":
            from pydantic import ValidationError

            try:
                config = MCPConfig.model_validate(data.config).model_dump()
            except ValidationError as exc:
                raise BadRequestError(message="MCP 配置无效，请检查地址、命令和工具选择") from exc
            from app.services.mcp_connections import validate_url

            if config["transport"] != "stdio":
                validate_url(config["url"])
            known = {t["name"] for t in asset.catalog.get("tools", [])}
            if not set(config["enabled_tools"]) <= known:
                raise BadRequestError(message="请先测试连接，再选择已发现的工具")
            changed = (
                any(config[k] != old_config.get(k) for k in ("transport", "url", "command", "args"))
                or data.secrets is not None
            )
            if (
                old_config
                and config["transport"] != old_config.get("transport")
                and asset.secret
                and data.secrets is None
            ):
                raise BadRequestError(message="切换传输方式时请重新填写凭据或清空凭据")
            if changed:
                asset.catalog, asset.status, asset.status_message, asset.tested_at = (
                    {},
                    "untested",
                    "配置已变化，请重新测试连接",
                    None,
                )
                config["enabled_tools"], config["auto_approved_tools"] = [], []
            if data.secrets is not None:
                from app.services.mcp_connections import validate_secrets

                validate_secrets(config["transport"], data.secrets)
                asset.secret = seal(asset.owner_id, asset.id, data.secrets)
            if (
                asset.secret
                and config["transport"] != "stdio"
                and not config["url"].startswith("https://")
            ):
                raise BadRequestError(message="携带认证信息的 MCP 连接必须使用 HTTPS")
            asset.config = config
        elif kind == "skill":
            if members is None:
                entry = data.config.get("entry")
                if not isinstance(entry, str):
                    raise BadRequestError(message="请填写 SKILL.md 正文")
                manifest(entry)
                files = dict(asset.config.get("files", {}))
                entry_config = await self.store_files(asset, {"SKILL.md": entry.encode()})
                files.update(entry_config["files"])
                asset.config = {"entry": entry, "files": files}
            else:
                manifest(members["SKILL.md"].decode())
                asset.config = await self.store_files(asset, members)
            asset.status = "draft" if asset.published_version is None else "published_with_draft"
        else:
            raise BadRequestError(message="未知能力类型")
        asset.name, asset.description, asset.tags = data.name.strip(), data.description, data.tags
        asset.scope, asset.project_id = (
            data.scope,
            self.project_id if data.scope == "project" else None,
        )
        asset.enabled = data.enabled
        asset.revision += 1
        await self.audit(asset, "created" if asset.revision == 1 else "updated")
        await self.db.flush()
        await self.db.refresh(asset)
        return self.public(asset, detail=True)

    async def publish(self, asset_id, revision):
        asset = await self.get(asset_id, write=True)
        self.check_revision(asset, revision)
        if asset.kind != "skill":
            raise BadRequestError(message="此能力不是技能")
        data = manifest(asset.config["entry"])
        number = (
            await self.db.scalar(
                select(func.max(SkillVersion.number)).where(SkillVersion.asset_id == asset.id)
            )
            or 0
        ) + 1
        if number > 50:
            raise RateLimitError(message="单个技能最多保留 50 个发布版本")
        self.db.add(
            SkillVersion(
                asset_id=asset.id,
                number=number,
                manifest=data,
                files=asset.config["files"],
                digest=package_digest(asset.config["files"]),
            )
        )
        asset.published_version, asset.revision, asset.status = (
            number,
            asset.revision + 1,
            "published",
        )
        await self.audit(asset, "published")
        await self.db.flush()
        await self.db.refresh(asset)
        return self.public(asset, detail=True)

    async def versions(self, asset_id):
        await self.get(asset_id)
        rows = await self.db.scalars(
            select(SkillVersion)
            .where(SkillVersion.asset_id == asset_id)
            .order_by(SkillVersion.number.desc())
            .limit(50)
        )
        return [
            {
                "version": v.number,
                "manifest": v.manifest,
                "digest": v.digest,
                "created_at": v.created_at.isoformat(),
            }
            for v in rows
        ]

    async def version(self, asset, number):
        value = await self.db.scalar(
            select(SkillVersion).where(
                SkillVersion.asset_id == asset.id, SkillVersion.number == number
            )
        )
        if not value:
            raise NotFoundError(message="技能版本不存在")
        return value

    async def read_file(self, asset, path, number=None):
        files = (
            (await self.version(asset, number)).files if number else asset.config.get("files", {})
        )
        item = files.get(safe_path(path))
        if not item:
            raise NotFoundError(message="技能文件不存在")
        try:
            content = await get_skill_storage().load(item["storage"])
        except FileNotFoundError as exc:
            raise NotFoundError(message="技能文件暂不可用，请恢复文件备份或重新导入") from exc
        if hashlib.sha256(content).hexdigest() != item["sha256"]:
            raise BadRequestError(message="技能文件完整性校验失败")
        return content

    async def restore(self, asset_id, revision, number):
        asset = await self.get(asset_id, write=True)
        self.check_revision(asset, revision)
        version = await self.version(asset, number)
        entry = await self.read_file(asset, "SKILL.md", number)
        asset.config = {"entry": entry.decode(), "files": version.files}
        asset.revision += 1
        asset.status = "published_with_draft"
        await self.audit(asset, "restored_draft")
        await self.db.flush()
        await self.db.refresh(asset)
        return self.public(asset, detail=True)

    async def toggle(self, asset_id, data):
        asset = await self.get(asset_id, write=True)
        self.check_revision(asset, data.revision)
        asset.enabled, asset.revision = data.enabled, asset.revision + 1
        await self.audit(asset, "enabled" if data.enabled else "disabled")
        await self.db.flush()
        await self.db.refresh(asset)
        return self.public(asset, detail=True)

    async def write_file(self, asset_id, data, *, remove=False):
        await self.db.scalar(select(User.id).where(User.id == self.user.id).with_for_update())
        asset = await self.get(asset_id, write=True)
        self.check_revision(asset, data.revision)
        if asset.kind != "skill":
            raise BadRequestError(message="此能力不是技能")
        path = safe_path(data.path)
        files = dict(asset.config["files"])
        entry = asset.config["entry"]
        if remove:
            if path == "SKILL.md":
                raise BadRequestError(message="不能删除技能入口")
            if path not in files:
                raise NotFoundError(message="技能文件不存在")
            del files[path]
        else:
            content = data.content.replace("\r\n", "\n").encode()
            if path == "SKILL.md":
                manifest(content.decode())
                entry = content.decode()
            if (
                len(content) > MAX_FILE
                or len(files) + (path not in files) > 100
                or sum(v["size"] for p, v in files.items() if p != path) + len(content)
                > MAX_EXPANDED
            ):
                raise BadRequestError(message="文件或技能包超过大小限制")
            stored = await self.store_files(asset, {"SKILL.md": entry.encode(), path: content})
            files.update(stored["files"])
        asset.config = {"entry": entry, "files": files}
        asset.status = "published_with_draft" if asset.published_version else "draft"
        asset.revision += 1
        await self.audit(asset, "file_deleted" if remove else "file_saved")
        await self.db.flush()
        await self.db.refresh(asset)
        return self.public(asset, detail=True)

    async def remove(self, asset_id, revision):
        asset = await self.get(asset_id, write=True)
        self.check_revision(asset, revision)
        await self.audit(asset, "deleted")
        await self.db.flush()
        await self.db.delete(asset)
        await self.db.flush()

    async def bindings(self):
        ids = sorted(
            str(x)
            for x in await self.db.scalars(
                select(Binding.asset_id)
                .join(Asset, Asset.id == Binding.asset_id)
                .where(
                    Binding.user_id == self.user.id,
                    Binding.context_key == str(self.project_id or "default"),
                    Binding.agent_key == "assistant",
                    self.visible(),
                    or_(
                        Asset.scope.in_(["personal", "system"]), Asset.project_id == self.project_id
                    ),
                )
            )
        )
        return {"asset_ids": ids, "revision": hashlib.sha256(json.dumps(ids).encode()).hexdigest()}

    async def bind(self, data):
        await self.db.scalar(select(User.id).where(User.id == self.user.id).with_for_update())
        if (await self.bindings())["revision"] != data.revision:
            raise AlreadyExistsError(message="能力绑定已更新，请刷新后重试")
        previous = set((await self.bindings())["asset_ids"])
        for asset_id in data.asset_ids:
            asset = await self.get(asset_id)
            if str(asset_id) in previous:
                continue
            if not self.usable(asset):
                raise AuthorizationError(message="该能力不属于当前账号或项目")
            if (
                not asset.enabled
                or (asset.kind == "skill" and not asset.published_version)
                or (asset.kind == "mcp" and asset.status != "ready")
            ):
                raise BadRequestError(message="请先启用能力，并完成技能发布或 MCP 连接测试")
        scope = (
            Binding.user_id == self.user.id,
            Binding.context_key == str(self.project_id or "default"),
            Binding.agent_key == "assistant",
        )
        await self.db.execute(delete(Binding).where(*scope))
        for asset_id in set(data.asset_ids):
            self.db.add(
                Binding(
                    user_id=self.user.id,
                    context_key=str(self.project_id or "default"),
                    agent_key="assistant",
                    asset_id=asset_id,
                )
            )
        await self.db.flush()
        await self.audit_binding()
        return await self.bindings()

    async def audit_binding(self):
        self.db.add(
            CapabilityAudit(
                user_id=self.user.id,
                asset_id=None,
                action="bindings_updated",
                revision=0,
                timestamp=datetime.now(UTC).isoformat(),
            )
        )
