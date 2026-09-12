"""Review/apply an explicit image cleanup plan; never prune volumes or containers."""

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPOSITORIES = {"agent_backend", "agent-frontend"}


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True)


def inventory():
    image_ids = sorted(set(docker("image", "ls", "-q", "--no-trunc").split()))
    images = json.loads(docker("image", "inspect", *image_ids)) if image_ids else []
    container_ids = docker("ps", "-aq").split()
    # All containers, including stopped workers, protect their image IDs.
    containers = json.loads(docker("inspect", *container_ids)) if container_ids else []
    return images, {container["Image"] for container in containers}


def select(images, used, keep=2):
    protected = set(used)
    for repository in sorted(REPOSITORIES):
        rollback = [
            image for image in images
            if image["Id"] not in used
            and any(tag.startswith(repository + ":rollback-") for tag in image.get("RepoTags") or [])
        ]
        rollback.sort(key=lambda image: image["Created"], reverse=True)
        protected.update(image["Id"] for image in rollback[:keep])
    remove = []
    for image in images:
        tags = image.get("RepoTags") or []
        if image["Id"] in protected or not tags:
            continue
        if any(ref.split("@", 1)[0] not in REPOSITORIES for ref in image.get("RepoDigests") or []):
            continue
        # A release alias alone is not evidence that a version is obsolete.
        # Remove only versions explicitly tagged as rollback/before, and only
        # when every tag belongs to these two application repositories.
        if not all(tag.rsplit(":", 1)[0] in REPOSITORIES for tag in tags):
            continue
        if not any(tag.rsplit(":", 1)[1].startswith(("rollback-", "before-")) for tag in tags):
            continue
        if any(tag.rsplit(":", 1)[1] in {"dev", "latest"} for tag in tags):
            continue
        remove.append({"id": image["Id"], "tags": sorted(tags)})
    return sorted(remove, key=lambda item: item["tags"]), protected


def apply(plan, images, used):
    current_remove, _ = select(images, used, plan["keep_unused_rollbacks"])
    allowed = {item["id"]: item for item in current_remove}
    for item in plan["remove"]:
        if allowed.get(item["id"]) != item:
            raise RuntimeError("Inventory changed; regenerate the plan before deleting any image")
    for item in plan["remove"]:
        # Recheck container use and all aliases immediately before each deletion.
        fresh_images, fresh_used = inventory()
        fresh_remove, _ = select(fresh_images, fresh_used, plan["keep_unused_rollbacks"])
        if item not in fresh_remove:
            raise RuntimeError("Image protection changed; stopping cleanup")
        print("Removing", ", ".join(item["tags"]), flush=True)
        # No force: Docker retains in-use/shared layers and rejects conflicts.
        print(docker("image", "rm", *item["tags"]), end="", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=Path("/tmp/agent-image-cleanup-plan.json"))
    parser.add_argument("--apply", action="store_true", help="Apply the saved and reviewed plan")
    args = parser.parse_args()
    images, used = inventory()
    if args.apply:
        plan = json.loads(args.plan.read_text())
        if plan.get("version") != 1 or plan.get("keep_unused_rollbacks") != 2:
            raise ValueError("Unsupported retention policy")
        apply(plan, images, used)
        return
    remove, protected = select(images, used)
    plan = {
        "version": 1,
        "created": datetime.now(timezone.utc).isoformat(),
        "keep_unused_rollbacks": 2,
        "protected": [
            {"id": image["Id"], "tags": image.get("RepoTags") or []}
            for image in images if image["Id"] in protected
        ],
        "remove": remove,
    }
    args.plan.parent.mkdir(parents=True, exist_ok=True)
    args.plan.write_text(json.dumps(plan, indent=2) + "\n")
    print(json.dumps(plan, indent=2))
    print(f"Dry run: {len(remove)} obsolete images; plan saved to {args.plan}")


if __name__ == "__main__":
    main()
