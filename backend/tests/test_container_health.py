"""Container readiness must reject HTTP failures, stale loops and stale processes."""

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

from app import healthcheck
from app.worker.health import WorkerPulse


@pytest.fixture(scope="module")
def server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            status, body = {
                "/ready": (200, b'{"status":"ready"}'),
                "/failed": (503, b'{"status":"not_ready"}'),
                "/liveness": (200, b'{"status":"healthy"}'),
                "/invalid": (200, b"not-json"),
            }[self.path]
            self.send_response(status)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{http.server_port}"
    http.shutdown()
    http.server_close()
    thread.join()


def test_http_probe_checks_response_status_and_actual_readiness(server):
    assert healthcheck.http_ready(server + "/ready") is True
    assert healthcheck.http_ready(server + "/liveness") is False
    with pytest.raises(HTTPError):
        healthcheck.http_ready(server + "/failed")
    with pytest.raises(ValueError):
        healthcheck.http_ready(server + "/invalid")


def test_worker_probe_requires_both_dispatchers_and_rejects_stale_progress(tmp_path):
    path = tmp_path / "pulse"
    with patch("app.worker.health.time.monotonic", return_value=100) as clock:
        pulse = WorkerPulse(path)
        pulse.tick(0)
        assert not path.exists()
        pulse.tick(1)
        assert healthcheck.worker_ready(path, now=101)
        clock.return_value = 150
        pulse.tick(0)
        assert healthcheck.worker_ready(path, now=150) is False
        clock.return_value = 155
        pulse.tick(1)
        assert healthcheck.worker_ready(path, now=155)
        assert healthcheck.worker_ready(path, now=201) is False
        pulse.close()
    assert not path.exists()


@pytest.mark.parametrize("ticks", [[100], [100, True], [100, float("nan")], [100, 200], [1, 1]])
def test_malformed_or_future_worker_pulses_fail_closed(tmp_path, ticks):
    path = tmp_path / "pulse"
    path.write_text(json.dumps({"version": 1, "pid": os.getpid(), "pulses": ticks}))
    assert healthcheck.worker_ready(path, now=101) is False


def test_worker_probe_rejects_a_dead_process(tmp_path):
    path = tmp_path / "pulse"
    path.write_text(json.dumps({"version": 1, "pid": os.getpid(), "pulses": [100, 100]}))
    with (
        patch("app.healthcheck.os.kill", side_effect=ProcessLookupError),
        pytest.raises(ProcessLookupError),
    ):
        healthcheck.worker_ready(path, now=101)


def test_probe_failures_exit_unsuccessfully_without_error_details(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["healthcheck", "http"])
    with patch("app.healthcheck.http_ready", side_effect=OSError("private connection details")):
        assert healthcheck.main() == 1
    assert capsys.readouterr().out == ""


def test_heartbeat_io_failure_does_not_fail_the_business_operation(tmp_path):
    path = tmp_path / "pulse"
    pulse = WorkerPulse(path)
    pulse.tick(0)
    with patch("app.worker.health.os.replace", side_effect=OSError("disk unavailable")):
        pulse.tick(1)
    assert not path.exists()


def test_shutdown_does_not_remove_another_process_pulse(tmp_path):
    path = tmp_path / "pulse"
    pulse = WorkerPulse(path)
    path.write_text(json.dumps({"pid": os.getpid() + 1}))
    pulse.close()
    assert path.exists()
