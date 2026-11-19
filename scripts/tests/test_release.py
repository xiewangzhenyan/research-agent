"""Rehearse release ordering and failure handling without touching Docker or production."""

import gzip
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "release", Path(__file__).resolve().parents[1] / "release.py"
)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class Rehearsal(release.Release):
    def __init__(self, root, fail=None):
        super().__init__("v-test", root=root, evidence=root / "evidence")
        self.fail, self.calls = fail, []
        prepared = root / "backups/prepared/v-test"
        prepared.mkdir(parents=True)
        self.expected_images = {
            key: self.image(self.env[key])
            for key in ("BACKEND_IMAGE", "FRONTEND_IMAGE")
        }
        (prepared / "prepared.json").write_text(
            json.dumps({"revision": "test-revision", "images": self.expected_images})
        )

    def revision(self):
        return "test-revision"

    def config(self):
        return {}

    def image(self, name):
        return {
            "id": "sha256:new-frontend" if "frontend" in name else "sha256:new-backend",
            "revision": "test-revision",
        }

    def container(self, name):
        return {
            "id": name,
            "image": "sha256:old-" + name,
            "running": True,
            "health": "healthy",
        }

    def run(self, command, *, label, output=None, **kwargs):
        self.calls.append((label, command))
        if self.fail == label:
            raise release.ReleaseError("injected failure")
        if output:
            output.write(
                gzip.compress(b"media-backup")
                if label == "backup-media"
                else b"database-archive"
            )
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    def wait_ready(self):
        self.calls.append(("readiness", []))
        if self.fail == "readiness":
            raise release.ReleaseError("not ready")


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_default_is_a_read_only_plan(self):
        with (
            patch("sys.argv", ["release.py"]),
            patch.object(release.subprocess, "run") as run,
        ):
            self.assertEqual(release.main(), 0)
        run.assert_not_called()

    def test_stop_backup_migrate_start_and_probe_order(self):
        task = Rehearsal(self.root)
        task.apply()
        steps = [label for label, _ in task.calls]
        required = [
            "stop-writers",
            "backup-database",
            "verify-database-archive",
            "backup-media",
            "migrate",
            "checkpoint-schema",
            "start-release",
            "readiness",
            "celery-probe",
        ]
        self.assertEqual(sorted(required, key=steps.index), required)
        self.assertTrue((task.evidence / "backups.json").exists())
        self.assertTrue((task.evidence / "released.json").exists())
        for path in task.evidence.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_backup_failure_restarts_only_existing_old_containers(self):
        task = Rehearsal(self.root, fail="backup-database")
        with self.assertRaises(release.ReleaseError):
            task.apply()
        steps = dict(task.calls)
        self.assertIn("restore-before-migration", steps)
        self.assertIn("start", steps["restore-before-migration"])
        self.assertNotIn("migrate", steps)
        self.assertNotIn("start-release", steps)

    def test_after_migration_failure_never_restarts_old_runtime(self):
        for phase in ("migrate", "checkpoint-schema", "readiness"):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as folder:
                task = Rehearsal(Path(folder), fail=phase)
                with self.assertRaises(release.ReleaseError):
                    task.apply()
                steps = dict(task.calls)
                self.assertNotIn("restore-before-migration", steps)
                self.assertIn("hold-maintenance", steps)
                self.assertNotIn(
                    "down",
                    " ".join(arg for command in steps.values() for arg in command),
                )

    def test_prepared_image_drift_is_rejected_before_stopping_services(self):
        task = Rehearsal(self.root)
        prepared = self.root / "backups/prepared/v-test/prepared.json"
        value = json.loads(prepared.read_text())
        value["images"]["BACKEND_IMAGE"]["id"] = "sha256:unreviewed"
        prepared.write_text(json.dumps(value))
        with self.assertRaises(release.ReleaseError):
            task.apply()
        self.assertNotIn("stop-writers", dict(task.calls))

    def test_ambiguous_image_tags_are_not_releases(self):
        for value in ("dev", "latest", "candidate", "", "x;echo-secret"):
            with self.subTest(value=value), self.assertRaises(release.ReleaseError):
                release.Release(value)

    def test_prepare_rejects_missing_or_wrong_revision_after_build(self):
        for image in (None, {"id": "sha256:wrong", "revision": "another-revision"}):
            with self.subTest(image=image), tempfile.TemporaryDirectory() as folder:
                task = release.Release("v-test", root=folder)
                with (
                    patch.object(task, "revision", return_value="test-revision"),
                    patch.object(task, "config"),
                    patch.object(task, "run"),
                    patch.object(task, "image", side_effect=[None, None, image, image]),
                    self.assertRaises(release.ReleaseError),
                ):
                    task.prepare()
                self.assertFalse((task.evidence / "prepared.json").exists())


if __name__ == "__main__":
    unittest.main()
