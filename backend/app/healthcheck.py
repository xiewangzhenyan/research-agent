"""Small container probes; no application settings, secrets or model requests."""

import argparse
import json
import math
import os
import time
from pathlib import Path
from urllib.request import urlopen

HEARTBEAT = Path("/tmp/research-agent-task-worker.health")
MAX_AGE = 45


def http_ready(url="http://127.0.0.1:38001/api/v1/health/ready"):
    with urlopen(url, timeout=5) as response:
        return response.status == 200 and json.loads(response.read(65536))["status"] == "ready"


def worker_ready(path=HEARTBEAT, *, now=None):
    with Path(path).open() as stream:
        value = json.loads(stream.read(1024))
    if value.get("version") != 1 or type(value.get("pid")) is not int or value["pid"] <= 0:
        return False
    pulses = value.get("pulses")
    if not isinstance(pulses, list) or len(pulses) != 2:
        return False
    now = time.monotonic() if now is None else now
    if not all(
        type(tick) in (int, float) and math.isfinite(tick) and 0 <= now - tick <= MAX_AGE
        for tick in pulses
    ):
        return False
    os.kill(value["pid"], 0)
    return True


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("probe", choices=("http", "worker"))
    args = parser.parse_args()
    try:
        ready = http_ready() if args.probe == "http" else worker_ready()
    except Exception:
        ready = False
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
