"""Validate portable Skill packages without executing or extracting user paths."""

import hashlib
import io
import re
import stat
import zipfile
from pathlib import PurePosixPath

import yaml

from app.core.exceptions import BadRequestError

MAX_PACKAGE = 4 * 1024 * 1024
MAX_EXPANDED = 8 * 1024 * 1024
MAX_FILE = 1024 * 1024


def safe_path(value):
    path = PurePosixPath(value)
    if (
        not value
        or len(value) > 240
        or "\\" in value
        or "\x00" in value
        or ":" in value
        or path.is_absolute()
        or any(p in ("", ".", "..") for p in value.split("/"))
    ):
        raise BadRequestError(message="文件路径无效")
    return value


def manifest(entry):
    if len(entry.encode()) > 100000 or not entry.startswith("---\n"):
        raise BadRequestError(message="SKILL.md 需以 YAML 元信息开头，正文最多 100 KB")
    end = entry.find("\n---", 4)
    if end < 0 or end > 6000:
        raise BadRequestError(message="SKILL.md 元信息未闭合或过长")
    header = entry[4:end]
    try:
        if any(
            isinstance(t, (yaml.tokens.AnchorToken, yaml.tokens.AliasToken))
            for t in yaml.scan(header)
        ):
            raise ValueError("aliases")
        data = yaml.safe_load(header)
        if not isinstance(data, dict):
            raise ValueError("mapping")
        name, description = data.get("name"), data.get("description")
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name)
            or len(name) > 64
        ):
            raise ValueError("name")
        if not isinstance(description, str) or not description.strip() or len(description) > 1024:
            raise ValueError("description")
        if not entry[end + 4 :].strip():
            raise ValueError("instructions")
        return {
            "name": name,
            "description": description,
            "when_to_use": str(data.get("when_to_use", description))[:1200],
        }
    except (ValueError, yaml.YAMLError) as exc:
        raise BadRequestError(
            message="请填写合法的技能名称、description 和正文；元信息不支持 YAML 引用"
        ) from exc


def unpack(data, filename, *, max_compressed=MAX_PACKAGE):
    if len(data) > max_compressed:
        raise BadRequestError(message="技能包最多 4 MiB")
    if filename.lower().endswith(".md"):
        members = {"SKILL.md": data}
    else:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                infos = archive.infolist()
                if len(infos) > 100 or sum(i.file_size for i in infos) > MAX_EXPANDED:
                    raise ValueError("package limit")
                members = {}
                for info in infos:
                    name = safe_path(info.filename.rstrip("/"))
                    mode = info.external_attr >> 16
                    if stat.S_ISLNK(mode) or (
                        stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)
                    ):
                        raise ValueError("special file")
                    if info.is_dir():
                        continue
                    if info.flag_bits & 1 or info.file_size > MAX_FILE or name in members:
                        raise ValueError("entry limit")
                    members[name] = archive.read(info)
        except (ValueError, zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
            raise BadRequestError(message="技能包无效：请检查文件大小、重复路径和压缩格式") from exc
    entries = [p for p in members if PurePosixPath(p).name == "SKILL.md"]
    if len(entries) != 1:
        raise BadRequestError(message="每个技能包必须且只能包含一份 SKILL.md")
    prefix = entries[0][: -len("SKILL.md")]
    if any(not p.startswith(prefix) for p in members):
        raise BadRequestError(message="技能包包含技能目录之外的文件")
    members = {safe_path(k[len(prefix) :]): v for k, v in members.items()}
    try:
        entry = members["SKILL.md"].decode("utf-8-sig").replace("\r\n", "\n")
    except UnicodeError as exc:
        raise BadRequestError(message="SKILL.md 必须使用 UTF-8 编码") from exc
    members["SKILL.md"] = entry.encode()
    return manifest(entry), members


def package_digest(files):
    return hashlib.sha256(
        "\n".join(f"{k}:{v['sha256']}" for k, v in sorted(files.items())).encode()
    ).hexdigest()
