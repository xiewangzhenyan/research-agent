"""Bounded file protocol. Archives are inspected in memory, never extracted."""

import base64
import hashlib
import io
import re
import tarfile

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_INPUT_BYTES = 5 * 1024**2
MAX_ARTIFACT_BYTES = 2 * 1024**2
MAX_ARTIFACT_TOTAL = 4 * 1024**2
MAX_ARCHIVE_BYTES = 5 * 1024**2
FILE_TYPES = {
    ".csv": "text/csv",
    ".json": "application/json",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".pdf": "application/pdf",
}


def safe_name(name):
    return bool(re.fullmatch(r"[\w][\w .-]{0,119}", name)) and ".." not in name


class InputFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(max_length=120)
    content_base64: str = Field(max_length=7 * 1024**2)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_file(self):
        if not safe_name(self.name):
            raise ValueError("Invalid input filename")
        data = base64.b64decode(self.content_base64, validate=True)
        if len(data) > MAX_INPUT_BYTES or hashlib.sha256(data).hexdigest() != self.sha256:
            raise ValueError("Input size or digest mismatch")
        return self


def input_archive(files):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as archive:
        for item in files:
            data = base64.b64decode(item.content_base64, validate=True)
            info = tarfile.TarInfo(item.name)
            info.size, info.mode, info.uid, info.gid = len(data), 0o444, 65532, 65532
            archive.addfile(info, io.BytesIO(data))
    return output.getvalue()


def parse_artifacts(raw, root_name="outputs"):
    if len(raw) > MAX_ARCHIVE_BYTES:
        raise ValueError("Artifact archive exceeds limit")
    output, total, seen = [], 0, set()
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        for index, item in enumerate(archive):
            if index > 10:
                raise ValueError("Too many artifact entries")
            if item.name.rstrip("/") == "outputs" and item.isdir():
                continue
            parts = item.name.split("/")
            if root_name == "outputs" and len(parts) == 1 and safe_name(parts[0]):
                parts = ["outputs", parts[0]]
            if len(parts) != 2 or parts[0] != root_name or not safe_name(parts[1]):
                raise ValueError("Invalid artifact path")
            name = parts[1]
            suffix = "." + name.rsplit(".", 1)[-1].lower()
            if (
                not item.isreg()
                or item.issym()
                or item.islnk()
                or item.sparse is not None
                or any(k.startswith("GNU.sparse") for k in item.pax_headers)
                or item.size < 0
                or item.size > MAX_ARTIFACT_BYTES
                or suffix not in FILE_TYPES
                or name in seen
            ):
                raise ValueError("Unsupported artifact")
            seen.add(name)
            total += item.size
            if total > MAX_ARTIFACT_TOTAL or len(output) >= 10:
                raise ValueError("Artifact quota exceeded")
            stream = archive.extractfile(item)
            data = stream.read(MAX_ARTIFACT_BYTES + 1)
            if len(data) != item.size:
                raise ValueError("Incomplete artifact")
            output.append(
                {
                    "name": name,
                    "mime_type": FILE_TYPES[suffix],
                    "size": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "content_base64": base64.b64encode(data).decode("ascii"),
                }
            )
    return output


def parse_completion(raw):
    """Only a tiny regular file may announce completion; never follow links."""
    import json

    if len(raw) > 16384:
        raise ValueError("Completion archive exceeds limit")
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        members = archive.getmembers()
        if len(members) != 1:
            raise ValueError("Invalid completion metadata")
        item = members[0]
        if (
            item.name != ".execution-result.json"
            or not item.isreg()
            or not 0 <= item.size <= 128
            or item.sparse is not None
            or any(k.startswith("GNU.sparse") for k in item.pax_headers)
        ):
            raise ValueError("Invalid completion file")
        data = json.load(archive.extractfile(item))
    if (
        not isinstance(data, dict)
        or set(data) != {"exit_code"}
        or type(data["exit_code"]) is not int
    ):
        raise ValueError("Invalid completion result")
    if not -255 <= data["exit_code"] <= 255:
        raise ValueError("Invalid exit code")
    return data
