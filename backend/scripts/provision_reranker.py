"""Download a pinned local model during provisioning, never during serving.

Run as a one-off container with /models writable and internet access. The runtime
service mounts the resulting volume read-only on an internal network.
"""

import hashlib
import json
from pathlib import Path

from huggingface_hub import snapshot_download

MODEL = "BAAI/bge-reranker-base"
REVISION = "2cfc18c9415c912f9d8155881c133215df768a70"
root = Path("/models/bge-reranker-base")
snapshot_download(
    MODEL,
    revision=REVISION,
    local_dir=root,
    allow_patterns=["onnx/model.onnx", "*.json", "README.md"],
)
files = {}
for path in sorted(root.rglob("*")):
    if path.is_file() and ".cache" not in path.parts:
        with path.open("rb") as stream:
            files[str(path.relative_to(root))] = hashlib.file_digest(stream, "sha256").hexdigest()
manifest = {"model": MODEL, "revision": REVISION, "license": "MIT", "sha256": files}
Path("/models/reranker-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(json.dumps(manifest, indent=2))
