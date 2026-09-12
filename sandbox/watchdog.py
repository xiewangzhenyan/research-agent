"""Host systemd timer: independent hard cleanup when the manager is unavailable."""

import json
import subprocess
import time
from datetime import UTC, datetime
from uuid import UUID


def reap():
    ids = subprocess.check_output(
        ["docker", "ps", "-aq", "--filter", "label=agent.sandbox=v1"], text=True
    ).split()
    for container_id in ids:
        info = json.loads(subprocess.check_output(["docker", "inspect", container_id], text=True))[
            0
        ]
        # Docker timestamps may contain nanoseconds; fromisoformat accepts these.
        created = datetime.fromisoformat(info["Created"].replace("Z", "+00:00"))
        if (datetime.now(UTC) - created).total_seconds() > 120:
            subprocess.run(
                ["docker", "rm", "-f", "-v", container_id],
                check=True,
                stdout=subprocess.DEVNULL,
            )

    volumes = subprocess.check_output(
        ["docker", "volume", "ls", "-q", "--filter", "label=agent.sandbox=v2-input"], text=True
    ).split()
    for volume in volumes:
        info = json.loads(
            subprocess.check_output(["docker", "volume", "inspect", volume], text=True)
        )[0]
        labels = info.get("Labels") or {}
        try:
            job = str(UUID(labels.get("agent.job", "")))
            expired = time.time() - float(labels["agent.created"]) > 120
        except (ValueError, KeyError):
            continue
        if labels.get("agent.sandbox") == "v2-input" and volume == "agent-input-" + job and expired:
            subprocess.run(["docker", "volume", "rm", volume], check=False, stdout=subprocess.DEVNULL)
        if labels.get("agent.sandbox") == "v2-output" and volume == "agent-output-" + job and expired:
            # No force: a volume still referenced by a container must remain intact.
            subprocess.run(
                ["docker", "volume", "rm", volume], check=False, stdout=subprocess.DEVNULL
            )


if __name__ == "__main__":
    reap()
