"""A local pulse for both task dispatchers, refreshed only after successful DB work."""

import json
import os
import tempfile
import time
from contextlib import suppress

from app.healthcheck import HEARTBEAT


class WorkerPulse:
    def __init__(self, path=HEARTBEAT):
        self.path = path
        self.pulses = [None, None]
        self.written = None
        self.path.unlink(missing_ok=True)

    def tick(self, slot):
        now = time.monotonic()
        self.pulses[slot] = now
        if any(tick is None for tick in self.pulses):
            return
        if self.written is not None and now - self.written < 5:
            return
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", dir=self.path.parent, delete=False
            ) as stream:
                temporary = stream.name
                json.dump({"version": 1, "pid": os.getpid(), "pulses": self.pulses}, stream)
            os.replace(temporary, self.path)
            self.written = now
        except OSError:
            # An observability failure must not turn a successful task into a failure.
            # The existing pulse expires and the container probe becomes unhealthy.
            pass
        finally:
            if temporary and os.path.exists(temporary):
                with suppress(OSError):
                    os.unlink(temporary)

    def close(self):
        try:
            if json.loads(self.path.read_text()).get("pid") == os.getpid():
                self.path.unlink(missing_ok=True)
        except (OSError, ValueError):
            pass
