"""Destructive migration cycles require an explicitly selected disposable database."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from app.core.config import settings

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_MIGRATION_DB_TESTS") != "1", reason="explicit disposable migration DB only"
)
ROOT = Path(__file__).resolve().parents[1]


def migrate(*args):
    assert settings.POSTGRES_DB.endswith("_review"), "Refusing to migrate a non-review database"
    # Never discover the operator's backend/.env while testing an isolated DB.
    with tempfile.TemporaryDirectory(prefix="agent-migration-review-") as folder:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "-c", str(ROOT / "alembic.ini"), *args],
            capture_output=True,
            text=True,
            cwd=folder,
            timeout=60,
        )
    assert result.returncode == 0, f"alembic {args} failed:\n{result.stderr}"
    return result.stdout


def test_upgrade_downgrade_cycle():
    # Always restore head, including after an assertion fails.
    try:
        migrate("upgrade", "head")
        assert "(head)" in migrate("current")
        migrate("downgrade", "base")
        migrate("upgrade", "head")
        assert "(head)" in migrate("current")
    finally:
        migrate("upgrade", "head")
