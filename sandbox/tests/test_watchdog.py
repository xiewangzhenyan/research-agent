import json
import time
from unittest.mock import Mock
from uuid import uuid4

from sandbox import watchdog


def test_orphan_inputs_and_outputs_are_reaped_without_force(monkeypatch):
    job = str(uuid4())

    def output(args, **kwargs):
        if args[1] == "ps":
            return ""
        if args[2] == "ls":
            return "agent-" + ("input" if args[-1].endswith("v2-input") else "output") + "-" + job
        kind = "input" if args[-1].startswith("agent-input") else "output"
        return json.dumps(
            [
                {
                    "Labels": {
                        "agent.sandbox": "v2-" + kind,
                        "agent.job": job,
                        "agent.created": str(time.time() - 121),
                    }
                }
            ]
        )

    monkeypatch.setattr(watchdog.subprocess, "check_output", output)
    remove = Mock()
    monkeypatch.setattr(watchdog.subprocess, "run", remove)
    watchdog.reap()
    assert [c.args[0] for c in remove.call_args_list] == [
        ["docker", "volume", "rm", "agent-input-" + job],
        ["docker", "volume", "rm", "agent-output-" + job],
    ]
