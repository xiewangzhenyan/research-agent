"""End-user capability management. Ownership is exclusively from authentication."""

import asyncio
import io
import zipfile
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.routing import APIRoute

from app.api.deps import CurrentUser, DBSession
from app.api.project_deps import CurrentProject
from app.core.exceptions import BadRequestError
from app.schemas.capability import (
    AssetWrite,
    BindingsWrite,
    RestoreAction,
    RevisionAction,
    SkillFileWrite,
    ToggleAction,
)
from app.services.capability_assets import CapabilityService, cryptor
from app.services.mcp_connections import test_connection
from app.services.skill_packages import MAX_EXPANDED, MAX_FILE, MAX_PACKAGE, safe_path, unpack


class BoundedCapabilityRoute(APIRoute):
    """Enforce limits before JSON/multipart parsing can allocate/spool the body."""

    async def handle(self, scope, receive, send):
        limit = 9 * 1024 * 1024 if "/skills/import" in scope["path"] else 400000
        size = 0
        deadline = asyncio.get_running_loop().time() + 20

        async def bounded_receive():
            nonlocal size
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise HTTPException(408, "上传超时，请重试")
            try:
                message = await asyncio.wait_for(receive(), remaining)
            except TimeoutError as exc:
                raise HTTPException(408, "上传超时，请重试") from exc
            size += len(message.get("body", b""))
            if size > limit:
                raise HTTPException(413, "请求内容超过大小限制")
            return message

        await super().handle(scope, bounded_receive, send)


router = APIRouter(
    prefix="/capabilities", tags=["capabilities"], route_class=BoundedCapabilityRoute
)


@router.get("/availability")
async def availability(user: CurrentUser):
    from app.services import mcp_sandbox

    try:
        cryptor()
        credentials_ready = True
    except BadRequestError:
        credentials_ready = False
    return {
        "credentials_ready": credentials_ready,
        "stdio_ready": (await mcp_sandbox.health())["status"] == "ready",
        "shared_workspaces": False,
        "agent_keys": ["assistant"],
    }


@router.get("/bindings")
async def bindings(db: DBSession, user: CurrentUser, project: CurrentProject):
    return await CapabilityService(db, user, project).bindings()


@router.put("/bindings")
async def bind(data: BindingsWrite, db: DBSession, user: CurrentUser, project: CurrentProject):
    return await CapabilityService(db, user, project).bind(data)


@router.post("/skills/import", status_code=201)
async def import_skill(
    db: DBSession,
    user: CurrentUser,
    project: CurrentProject,
    file: UploadFile = File(),
    scope: Literal["personal", "project", "system"] = Form("personal"),
):
    data = await file.read(MAX_PACKAGE + 1)
    meta, members = unpack(data, file.filename or "skill.zip")
    return await CapabilityService(db, user, project).save(
        "skill",
        AssetWrite(name=meta["name"], description=meta["description"], scope=scope),
        members=members,
    )


@router.post("/skills/import-directory", status_code=201)
async def import_directory(
    db: DBSession,
    user: CurrentUser,
    project: CurrentProject,
    files: list[UploadFile] = File(),
    scope: Literal["personal", "project", "system"] = Form("personal"),
):
    if len(files) > 100:
        raise BadRequestError(message="技能目录最多包含 100 个文件")
    buffer, size, names = io.BytesIO(), 0, set()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in files:
            path = safe_path(file.filename or "")
            data = await file.read(MAX_FILE + 1)
            size += len(data)
            if path in names or len(data) > MAX_FILE or size > MAX_EXPANDED:
                raise BadRequestError(message="目录含重复文件或超过大小限制")
            names.add(path)
            archive.writestr(path, data)
    meta, members = unpack(buffer.getvalue(), "skill.zip", max_compressed=MAX_EXPANDED + 32000)
    return await CapabilityService(db, user, project).save(
        "skill",
        AssetWrite(name=meta["name"], description=meta["description"], scope=scope),
        members=members,
    )


@router.get("/{kind}")
async def list_assets(
    kind: Literal["mcp", "skills"], db: DBSession, user: CurrentUser, project: CurrentProject
):
    return await CapabilityService(db, user, project).list("skill" if kind == "skills" else kind)


@router.post("/{kind}", status_code=201)
async def create_asset(
    kind: Literal["mcp", "skills"],
    data: AssetWrite,
    db: DBSession,
    user: CurrentUser,
    project: CurrentProject,
):
    return await CapabilityService(db, user, project).save(
        "skill" if kind == "skills" else kind, data
    )


@router.get("/assets/{asset_id}")
async def get_asset(asset_id: UUID, db: DBSession, user: CurrentUser, project: CurrentProject):
    service = CapabilityService(db, user, project)
    return service.public(await service.get(asset_id), detail=True)


@router.put("/assets/{asset_id}")
async def update_asset(
    asset_id: UUID, data: AssetWrite, db: DBSession, user: CurrentUser, project: CurrentProject
):
    service = CapabilityService(db, user, project)
    asset = await service.get(asset_id)
    return await service.save(asset.kind, data, asset_id)


@router.delete("/assets/{asset_id}", status_code=204)
async def delete_asset(
    asset_id: UUID,
    db: DBSession,
    user: CurrentUser,
    project: CurrentProject,
    revision: int = Query(ge=1),
):
    await CapabilityService(db, user, project).remove(asset_id, revision)
    return Response(status_code=204)


@router.post("/assets/{asset_id}/toggle")
async def toggle(
    asset_id: UUID, data: ToggleAction, db: DBSession, user: CurrentUser, project: CurrentProject
):
    return await CapabilityService(db, user, project).toggle(asset_id, data)


@router.post("/assets/{asset_id}/test")
async def test(
    asset_id: UUID, data: RevisionAction, db: DBSession, user: CurrentUser, project: CurrentProject
):
    return await test_connection(CapabilityService(db, user, project), asset_id, data.revision)


@router.get("/assets/{asset_id}/versions")
async def versions(asset_id: UUID, db: DBSession, user: CurrentUser, project: CurrentProject):
    return await CapabilityService(db, user, project).versions(asset_id)


@router.post("/assets/{asset_id}/publish")
async def publish(
    asset_id: UUID, data: RevisionAction, db: DBSession, user: CurrentUser, project: CurrentProject
):
    return await CapabilityService(db, user, project).publish(asset_id, data.revision)


@router.post("/assets/{asset_id}/restore")
async def restore(
    asset_id: UUID, data: RestoreAction, db: DBSession, user: CurrentUser, project: CurrentProject
):
    return await CapabilityService(db, user, project).restore(asset_id, data.revision, data.version)


@router.get("/assets/{asset_id}/file")
async def read_file(
    asset_id: UUID,
    db: DBSession,
    user: CurrentUser,
    project: CurrentProject,
    path: str = Query(max_length=240),
    version: int | None = Query(default=None, ge=1),
):
    service = CapabilityService(db, user, project)
    content = await service.read_file(await service.get(asset_id), path, version)
    try:
        return {"path": path, "content": content.decode("utf-8")}
    except UnicodeError as exc:
        raise BadRequestError(message="此文件为二进制格式，请通过导出技能包下载") from exc


@router.put("/assets/{asset_id}/file")
async def save_file(
    asset_id: UUID, data: SkillFileWrite, db: DBSession, user: CurrentUser, project: CurrentProject
):
    return await CapabilityService(db, user, project).write_file(asset_id, data)


@router.delete("/assets/{asset_id}/file")
async def remove_file(
    asset_id: UUID,
    db: DBSession,
    user: CurrentUser,
    project: CurrentProject,
    path: str = Query(max_length=240),
    revision: int = Query(ge=1),
):
    return await CapabilityService(db, user, project).write_file(
        asset_id, SkillFileWrite(path=path, revision=revision, content=""), remove=True
    )


@router.get("/assets/{asset_id}/export")
async def export_skill(
    asset_id: UUID,
    db: DBSession,
    user: CurrentUser,
    project: CurrentProject,
    version: int | None = Query(default=None, ge=1),
):
    service = CapabilityService(db, user, project)
    asset = await service.get(asset_id)
    if asset.kind != "skill":
        raise BadRequestError(message="此能力不是技能")
    files = (await service.version(asset, version)).files if version else asset.config["files"]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.writestr(path, await service.read_file(asset, path, version))
    return Response(
        buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="skill-{asset_id}.zip"',
            "Cache-Control": "private, no-store",
        },
    )
