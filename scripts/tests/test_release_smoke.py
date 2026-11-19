"""The release probe stays offline by default and never reports exception bodies."""

import asyncio
import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[2] / "backend/scripts/release_smoke.py"
spec = importlib.util.spec_from_file_location("release_smoke", SCRIPT)
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class SmokeSafetyTests(unittest.TestCase):
    def test_offline_needs_no_application_or_credentials(self):
        result = subprocess.run(
            [sys.executable, "-I", str(SCRIPT), "--model", "--sandbox"],
            capture_output=True,
            check=True,
            text=True,
        )
        self.assertEqual(json.loads(result.stdout)["calls"], 0)
        self.assertEqual(result.stderr, "")

    def test_live_failure_reports_type_without_response_body(self):
        async def failed():
            raise ValueError("private-response-marker")

        output = io.StringIO()
        with (
            patch.object(smoke, "model_smoke", failed),
            patch("sys.argv", [str(SCRIPT), "--live", "--model"]),
            contextlib.redirect_stdout(output),
        ):
            self.assertEqual(asyncio.run(smoke.main()), 1)
        self.assertNotIn("private-response-marker", output.getvalue())
        self.assertEqual(
            json.loads(output.getvalue())["checks"]["model"]["error_type"], "ValueError"
        )


if __name__ == "__main__":
    unittest.main()
