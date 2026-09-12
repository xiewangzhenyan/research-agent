"""Snapshot integrity and public diagnostics contract."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.agent_run import AgentRunCreate
from app.schemas.knowledge import RetrievalConfig
from app.services.retrieval_snapshot import capture, execution_record, restore


def test_capture_copies_parameters_and_caps_only_collaboration():
    config = RetrievalConfig(result_limit=9)
    standard = capture(config)
    collaboration = capture(config, collaboration=True, override=True)
    config.result_limit = 2
    assert restore(standard).result_limit == 9
    assert restore(collaboration).result_limit == 5
    assert collaboration["origin"] == "task_override"
    assert collaboration["result_limit_capped"]
    assert not capture(config, collaboration=True)["result_limit_capped"]
    assert restore(None) is None


@pytest.mark.parametrize("field,value", [("schema_version", 2), ("configuration_id", "0" * 64)])
def test_corrupt_snapshots_fail_closed(field, value):
    snapshot = capture(RetrievalConfig())
    snapshot[field] = value
    with pytest.raises(ValueError):
        restore(snapshot)


def test_client_cannot_supply_server_snapshot():
    with pytest.raises(ValidationError):
        AgentRunCreate(
            idempotency_key=uuid4(), prompt="test", retrieval_snapshot=capture(RetrievalConfig())
        )


def test_public_record_excludes_internal_fields_at_all_levels():
    diagnostics = {
        "config": RetrievalConfig().model_dump(),
        "engine": "postgres",
        "secret": "private",
        "rerank": {"status": "applied", "model": "local", "url": "private", "token": "private"},
        "context": {"enabled": True, "added": 2, "internal": "private"},
    }
    record = execution_record("question", diagnostics)
    assert "private" not in str(record)
    assert record["rerank"] == {"status": "applied", "model": "local"}
    assert record["context"] == {"enabled": True, "added": 2}
    assert record["configuration_id"] == capture(RetrievalConfig())["configuration_id"]
    with pytest.raises(KeyError):
        execution_record("question", {})
