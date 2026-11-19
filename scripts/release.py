"""Plan, prepare immutable images, then explicitly apply a backed-up maintenance release.

Default mode only prints the plan. No automatic rollback after migration: older
agent runtimes may be unable to read checkpoints written by the new runtime.
"""

import argparse
import gzip
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICES = (
    "frontend",
    "app",
    "task_worker",
    "celery_worker",
    "celery_beat",
    "flower",
    "reranker",
)
READY = ("app", "task_worker", "frontend", "reranker")


class ReleaseError(RuntimeError):
    pass


def private_file(path, mode="w"):
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    return os.fdopen(descriptor, mode)


class Release:
    def __init__(self, version, *, root=ROOT, evidence=None):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", version) or version in {
            "dev",
            "latest",
            "candidate",
        }:
            raise ReleaseError(
                "Choose an explicit version tag, excluding dev/latest/candidate"
            )
        self.root, self.version = Path(root), version
        self.evidence = (
            Path(evidence) if evidence else self.root / "backups" / "prepared" / version
        )
        self.env = {
            **os.environ,
            "BACKEND_IMAGE": f"agent_backend:{version}",
            "FRONTEND_IMAGE": f"agent-frontend:{version}",
        }
        self.compose = [
            "docker",
            "compose",
            "--env-file",
            "backend/.env",
            "-f",
            "docker-compose.prod.yml",
        ]
        self.migration_started = False
        self.running_before = []
        self.sequence = 0

    def run(
        self, command, *, label, output=None, input_file=None, capture=False, check=True
    ):
        self.sequence += 1
        # Never persist Compose's fully interpolated configuration: it contains secrets.
        result = subprocess.run(
            command,
            cwd=self.root,
            env=self.env,
            stdout=output if output is not None else subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=input_file,
            check=False,
        )
        if not capture:
            with private_file(
                self.evidence / f"{self.sequence:02d}-{label}.log", "wb"
            ) as stream:
                stream.write(result.stdout or b"")
                stream.write(result.stderr or b"")
        if check and result.returncode:
            raise ReleaseError(f"{label} failed; inspect private release evidence")
        return result

    def revision(self):
        commit = (
            self.run(["git", "rev-parse", "HEAD"], label="revision", capture=True)
            .stdout.decode()
            .strip()
        )
        dirty = self.run(
            ["git", "status", "--porcelain"], label="source-status", capture=True
        ).stdout.strip()
        if dirty:
            raise ReleaseError(
                "Commit and review the release source before preparing or applying images"
            )
        return commit

    def config(self):
        result = self.run(
            self.compose + ["config", "--format", "json"],
            label="compose-config",
            capture=True,
        )
        config = json.loads(result.stdout)
        network = config["networks"]["model-gateway"]["name"]
        self.run(
            ["docker", "network", "inspect", network, "--format", "{{.Id}}"],
            label="gateway-network",
        )
        if any(
            config["services"][name]["image"] != self.env["BACKEND_IMAGE"]
            for name in SERVICES
            if name != "frontend"
        ):
            raise ReleaseError("All backend services must use the same versioned image")
        if config["services"]["frontend"]["image"] != self.env["FRONTEND_IMAGE"]:
            raise ReleaseError("Frontend must use its versioned image")
        return config

    def image(self, name):
        result = self.run(
            [
                "docker",
                "image",
                "inspect",
                name,
                "--format",
                '{"id":"{{.Id}}","revision":{{json (index .Config.Labels "org.opencontainers.image.revision")}}}',
            ],
            label="image-inspect",
            capture=True,
            check=False,
        )
        return json.loads(result.stdout) if result.returncode == 0 else None

    def container(self, service):
        cid = (
            self.run(
                self.compose + ["ps", "--all", "--quiet", service],
                label="container-id",
                capture=True,
            )
            .stdout.decode()
            .strip()
        )
        if not cid:
            return None
        result = self.run(
            [
                "docker",
                "inspect",
                cid,
                "--format",
                '{"id":"{{.Id}}","image":"{{.Image}}","running":{{.State.Running}},"health":{{if .State.Health}}{{json .State.Health.Status}}{{else}}null{{end}}}',
            ],
            label="container-state",
            capture=True,
        )
        return json.loads(result.stdout)

    def prepare(self):
        commit = self.revision()
        self.evidence.mkdir(parents=True, mode=0o700, exist_ok=False)
        self.config()
        for service, key in (("app", "BACKEND_IMAGE"), ("frontend", "FRONTEND_IMAGE")):
            existing = self.image(self.env[key])
            if existing and existing["revision"] != commit:
                raise ReleaseError(
                    "Release tag already belongs to a different revision"
                )
            if not existing:
                self.run(
                    self.compose
                    + ["build", "--build-arg", f"RELEASE_REVISION={commit}", service],
                    label=f"build-{service}",
                )
        images = {
            key: self.image(self.env[key])
            for key in ("BACKEND_IMAGE", "FRONTEND_IMAGE")
        }
        if any(not image or image["revision"] != commit for image in images.values()):
            raise ReleaseError("Built images must identify the frozen source revision")
        self.write_manifest(
            "prepared.json",
            {
                "revision": commit,
                "images": images,
            },
        )

    def write_manifest(self, name, value):
        with private_file(self.evidence / name) as stream:
            json.dump(value, stream, indent=2)
            stream.write("\n")

    def apply(self):
        commit = self.revision()
        self.evidence.mkdir(parents=True, mode=0o700, exist_ok=False)
        self.config()
        images = {
            key: self.image(self.env[key])
            for key in ("BACKEND_IMAGE", "FRONTEND_IMAGE")
        }
        if any(not image or image["revision"] != commit for image in images.values()):
            raise ReleaseError(
                "Prepare both images from this exact revision before applying"
            )
        prepared = json.loads(
            (
                self.root / "backups" / "prepared" / self.version / "prepared.json"
            ).read_text()
        )
        if prepared.get("revision") != commit or prepared.get("images") != images:
            raise ReleaseError(
                "Image IDs changed since preparation; do not apply an unreviewed image"
            )
        self.images = images
        for service in ("db", "redis"):
            container = self.container(service)
            if (
                not container
                or not container["running"]
                or container["health"] != "healthy"
            ):
                raise ReleaseError(
                    "Existing database and Redis must be healthy; this is an upgrade command"
                )
        before = {service: self.container(service) for service in SERVICES}
        self.running_before = [
            name for name, state in before.items() if state and state["running"]
        ]
        rollback_tags = {}
        for service, state in before.items():
            if not state or state["image"] in rollback_tags:
                continue
            repository = "agent-frontend" if service == "frontend" else "agent_backend"
            tag = f"{repository}:rollback-{self.version}-{state['image'].split(':')[-1][:12]}"
            self.run(
                ["docker", "image", "tag", state["image"], tag],
                label="preserve-rollback-image",
            )
            rollback_tags[state["image"]] = tag
        self.write_manifest(
            "before.json",
            {
                "revision": commit,
                "images": images,
                "containers": before,
                "rollback_tags": rollback_tags,
                "checkpoint_rollback": "manual compatibility review required",
            },
        )
        try:
            self.run(
                self.compose + ["stop", "--timeout", "60", *SERVICES],
                label="stop-writers",
            )
            with private_file(self.evidence / "database.dump", "wb") as stream:
                self.run(
                    self.compose
                    + [
                        "exec",
                        "-T",
                        "db",
                        "sh",
                        "-c",
                        'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom',
                    ],
                    label="backup-database",
                    output=stream,
                )
            with (self.evidence / "database.dump").open("rb") as stream:
                self.run(
                    self.compose
                    + ["exec", "-T", "db", "pg_restore", "--file=/dev/null"],
                    label="verify-database-archive",
                    input_file=stream,
                )
            with private_file(self.evidence / "media.tar.gz", "wb") as stream:
                self.run(
                    self.compose
                    + [
                        "run",
                        "--rm",
                        "--no-deps",
                        "-T",
                        "app",
                        "python",
                        "-c",
                        "import sys,tarfile; t=tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz'); t.add('/app/media',arcname='media'); t.close()",
                    ],
                    label="backup-media",
                    output=stream,
                )
            with gzip.open(self.evidence / "media.tar.gz", "rb") as stream:
                while stream.read(1024 * 1024):
                    pass
            backups = {}
            for name in ("database.dump", "media.tar.gz"):
                digest = hashlib.sha256()
                with (self.evidence / name).open("rb") as stream:
                    while chunk := stream.read(1024 * 1024):
                        digest.update(chunk)
                backups[name] = {
                    "sha256": digest.hexdigest(),
                    "size": (self.evidence / name).stat().st_size,
                }
            self.write_manifest("backups.json", backups)
            self.migration_started = True
            self.run(
                self.compose
                + ["run", "--rm", "--no-deps", "-T", "app", "agent", "db", "upgrade"],
                label="migrate",
            )
            self.run(
                self.compose
                + [
                    "run",
                    "--rm",
                    "--no-deps",
                    "-T",
                    "app",
                    "python",
                    "-m",
                    "app.worker.agent_runs",
                    "--setup",
                ],
                label="checkpoint-schema",
            )
            self.run(
                self.compose + ["up", "-d", "--no-build", "--no-deps", *SERVICES],
                label="start-release",
            )
            self.wait_ready()
            self.run(
                self.compose
                + [
                    "exec",
                    "-T",
                    "celery_worker",
                    "sh",
                    "-c",
                    'exec celery -A app.worker.celery_app inspect ping --timeout 10 --destination "celery@$HOSTNAME"',
                ],
                label="celery-probe",
            )
            self.write_manifest(
                "released.json",
                {
                    "revision": commit,
                    "images": images,
                    "status": "ready",
                    "real_model_smoke": "separate verification required",
                },
            )
        except BaseException:
            if not self.migration_started and self.running_before:
                # Start the existing containers, never recreate them with new images.
                self.run(
                    self.compose + ["start", *self.running_before],
                    label="restore-before-migration",
                    check=False,
                )
            elif self.migration_started:
                self.run(
                    self.compose + ["stop", "--timeout", "60", *SERVICES],
                    label="hold-maintenance",
                    check=False,
                )
            raise

    def wait_ready(self):
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            ready = True
            for service in SERVICES:
                state = self.container(service)
                ready = ready and bool(state and state["running"])
                if service in READY:
                    ready = ready and bool(state and state["health"] == "healthy")
                expected = self.images[
                    "FRONTEND_IMAGE" if service == "frontend" else "BACKEND_IMAGE"
                ]
                if state and state["image"] != expected["id"]:
                    raise ReleaseError(
                        "Running container does not match the prepared image"
                    )
            if ready:
                return
            time.sleep(2)
        raise ReleaseError(
            "Release readiness timed out; keep maintenance and inspect evidence"
        )


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--version")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-dir", type=Path)
    args = parser.parse_args()
    if not args.prepare and not args.apply:
        print(
            json.dumps(
                {
                    "mode": "plan",
                    "version": args.version,
                    "steps": [
                        "freeze clean source",
                        "prepare versioned images",
                        "verify dependencies",
                        "stop API and writers",
                        "back up database/checkpoints and media",
                        "migrate using new one-shot container",
                        "initialize checkpoint schema",
                        "start matching API/workers/frontend",
                        "wait for probes",
                        "real model/sandbox smoke",
                    ],
                    "rollback": "No automatic downgrade or old-runtime restart after migration",
                },
                indent=2,
            )
        )
        return 0
    if not args.version or (args.apply and not args.backup_dir):
        parser.error(
            "Preparation needs --version; application also needs a new --backup-dir"
        )
    try:
        release = Release(
            args.version, evidence=args.backup_dir if args.apply else None
        )
        print(
            "Preparing immutable images"
            if args.prepare
            else "Applying maintenance release"
        )
        release.prepare() if args.prepare else release.apply()
        print(
            "Release preparation complete"
            if args.prepare
            else "Services ready; complete real-model acceptance"
        )
        return 0
    except (ReleaseError, OSError, ValueError):
        print(
            "Release stopped. Inspect private evidence; after migration, do not restart the old runtime blindly."
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
