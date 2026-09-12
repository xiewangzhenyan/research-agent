#!/usr/bin/env python3
"""Opt-in commit-to-GitHub synchronization using only Python and Git."""

import os
from pathlib import Path
import re
import subprocess
import sys


MARKER = "# research-agent managed hook"
MAX_BLOB_BYTES = 10 * 1024 * 1024
SECRET_PATTERNS = [
    rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----",
    rb"\bgh[pousr]_[A-Za-z0-9]{36,}\b",
    rb"\bgithub_pat_[A-Za-z0-9_]{50,}\b",
    rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",
    rb"\bsk-(?:proj-|ant-api\d+-)?[A-Za-z0-9_-]{32,}\b",
    rb"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{20,}\b",
]


def git(*args, data=None, check=True):
    return subprocess.run(
        ["git", *args], input=data, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=check,
    )


def config(key):
    return git("config", "--local", "--get", key, check=False).stdout.decode().strip()


def local_secrets():
    """Read local env values in memory; never print or persist them."""
    values = set()
    for folder in (Path("."), Path("backend"), Path("frontend"), Path("sandbox")):
        for path in folder.glob(".env*"):
            if not path.is_file() or path.suffix in {".example", ".sample", ".template"}:
                continue
            for line in path.read_text(errors="replace").splitlines():
                key, sep, value = line.partition("=")
                if not sep or key.lstrip().startswith("#"):
                    continue
                if not re.search(r"PASSWORD|SECRET|TOKEN|API_KEY|ACCESS_KEY|PRIVATE_KEY", key):
                    continue
                value = value.strip().strip("\"'")
                if len(value) >= 12 and not any(
                    word in value.lower() for word in ("example", "change-me", "changeme", "your-")
                ):
                    values.add(value.encode())
    return values


def audit(ranges):
    """Inspect every outgoing revision, including secrets later deleted."""
    revisions = set()
    for new, old in ranges:
        args = ["rev-list", new]
        if old.strip("0") and git("cat-file", "-e", old, check=False).returncode == 0:
            args.append("^" + old)
        revisions.update(git(*args).stdout.decode().splitlines())

    records = set()
    for revision in revisions:
        for entry in git("ls-tree", "-rz", "--full-tree", revision).stdout.split(b"\0"):
            if entry:
                meta, name = entry.split(b"\t", 1)
                mode, kind, oid = meta.decode().split()
                records.add((mode, kind, oid, os.fsdecode(name)))
    if not records:
        return 0

    paths = {record[3] for record in records}
    ignored = git(
        "check-ignore", "--no-index", "-z", "--stdin",
        data=b"\0".join(os.fsencode(path) for path in paths) + b"\0", check=False,
    )
    if ignored.returncode not in (0, 1):
        raise RuntimeError("Cannot evaluate upload exclusions")
    findings = {(os.fsdecode(path), "excluded by ignore rules") for path in ignored.stdout.split(b"\0") if path}
    patterns = [re.compile(pattern) for pattern in SECRET_PATTERNS]
    secrets = local_secrets()
    blob_findings = {}
    for mode, kind, oid, path in sorted(records):
        if kind != "blob" or mode == "120000":
            findings.add((path, "symlink or nested repository requires review"))
            continue
        if oid not in blob_findings:
            size = int(git("cat-file", "-s", oid).stdout)
            reason = ""
            if size > MAX_BLOB_BYTES:
                reason = "file exceeds 10 MiB source limit"
            else:
                content = git("cat-file", "blob", oid).stdout
                if any(pattern.search(content) for pattern in patterns):
                    reason = "possible credential or private key"
                elif any(value in content for value in secrets):
                    reason = "matches a local environment secret"
            blob_findings[oid] = reason
        if blob_findings[oid]:
            findings.add((path, blob_findings[oid]))

    if findings:
        print("Upload check blocked the push. Review these paths (values hidden):", file=sys.stderr)
        for path, reason in sorted(findings)[:30]:
            print(f"  {path!r}: {reason}", file=sys.stderr)
        print(f"{len(findings)} finding(s). Local commits are preserved.", file=sys.stderr)
        return 1
    print(f"Upload check passed: {len(revisions)} revision(s), {len(paths)} path(s).")
    return 0


def hook_directory():
    hook_dir = Path(git("rev-parse", "--path-format=absolute", "--git-path", "hooks").stdout.decode().strip())
    if hook_dir.name == "_" and hook_dir.parent.name == ".husky":
        # Husky owns generated wrappers in '_'; put user hooks alongside them.
        hook_dir = hook_dir.parent
    return hook_dir


def install():
    urls = git("remote", "get-url", "--push", "--all", "origin").stdout.decode().splitlines()
    if len(urls) != 1:
        raise RuntimeError("Configure exactly one origin push URL before installing")
    hook_dir = hook_directory()
    for name in ("post-commit", "pre-push"):
        target = hook_dir / name
        if target.exists() and MARKER not in target.read_text():
            raise RuntimeError(f"Existing {name} hook preserved; integrate it manually")
    hook_dir.mkdir(parents=True, exist_ok=True)
    for name, action in (("post-commit", "push"), ("pre-push", "check-push")):
        target = hook_dir / name
        body = (
            f"#!/bin/sh\n{MARKER}\n"
            'root=$(git rev-parse --show-toplevel) || exit 1\n'
            'cd "$root" || exit 1\n'
            f'python3 scripts/git_sync.py {action}\n'
        )
        if name == "post-commit":
            body += 'status=$?\nif [ "$status" -ne 0 ]; then\n  echo "Auto-push failed; local commit kept. Retry: python3 scripts/git_sync.py push" >&2\nfi\nexit 0\n'
        target.write_text(body)
        target.chmod(0o755)
    git("config", "--local", "researchAgent.syncUrl", urls[0])
    git("config", "--local", "researchAgent.autoPush", "true")
    print("Installed post-commit/pre-push hooks; existing pre-commit hooks preserved.")
    return 0


def push():
    if os.environ.get("RESEARCH_AGENT_SKIP_PUSH") == "1" or config("researchAgent.autoPush") != "true":
        print("Auto-push disabled; commit remains local.")
        return 0
    branch = git("symbolic-ref", "--quiet", "HEAD", check=False).stdout.decode().strip()
    if not branch.startswith("refs/heads/"):
        raise RuntimeError("Detached HEAD; select a branch before pushing")
    urls = git("remote", "get-url", "--push", "--all", "origin").stdout.decode().splitlines()
    if urls != [config("researchAgent.syncUrl")]:
        raise RuntimeError("Origin changed; review the destination and reinstall sync hooks")
    guard = hook_directory() / "pre-push"
    if not guard.is_file() or MARKER not in guard.read_text() or not os.access(guard, os.X_OK):
        raise RuntimeError("Upload hook changed or is missing; reinstall sync hooks")
    result = subprocess.run(
        ["git", "-c", "push.followTags=false",
         "push", "--set-upstream", "origin", f"{branch}:{branch}"],
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"},
        timeout=60,
    )
    return result.returncode


def main():
    root = git("rev-parse", "--show-toplevel").stdout.decode().strip()
    os.chdir(root)
    action = sys.argv[1] if len(sys.argv) == 2 else ""
    if action == "install":
        return install()
    if action == "push":
        return push()
    if action == "check":
        return audit([("HEAD", "0" * 40)])
    if action == "check-push":
        ranges = []
        for line in sys.stdin:
            _local_ref, new, _remote_ref, old = line.split()
            if new.strip("0"):
                ranges.append((new, old))
        return audit(ranges)
    print("Usage: python3 scripts/git_sync.py {install|check|push}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        # Git errors may contain credential-bearing URLs; don't echo stderr.
        message = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        print(f"Git sync stopped: {message}. Local commits are preserved.", file=sys.stderr)
        sys.exit(1)
