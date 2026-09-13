"""Destructive migration cycles require an explicitly selected disposable database."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.core.config import settings

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_MIGRATION_DB_TESTS") != "1", reason="explicit disposable migration DB only"
)
ROOT = Path(__file__).resolve().parents[1]


def migrate(*args):
    assert settings.POSTGRES_DB.endswith("_review"), "Refusing to migrate a non-review database"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ROOT / "alembic.ini"), *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
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
