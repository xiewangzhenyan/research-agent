"""Real pinned SDK, synthetic model/encoder: no external services or API calls."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from app.schemas.memory import ExtractionResult
from app.services import mem0_memory as module
from app.services.model_config import resolve_generation_config

TEXT = "之后请使用中文回答，涉及的专业术语保留英文名称。"
VECTOR = [1.0] + [0.0] * 511


def fact(text=TEXT, **extra):
    return {
        "title": "回答语言",
        "content": text,
        "kind": "preference",
        "action": "add",
        "target": None,
        "reason": "长期回答偏好",
        "quote": text,
        **extra,
    }


def item(text=TEXT):
    return SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        project_id=uuid4(),
        title="回答语言",
        content=text,
        kind="preference",
        revision=1,
        pinned=False,
        embedding=VECTOR,
        embedding_revision=1,
        embedding_model="test",
        expires_on=None,
        created_at=datetime.now(UTC),
    )


@pytest.mark.anyio
async def test_real_sdk_stages_automatic_facts_without_sqlite_or_factory_connections():
    calls = []

    def model(messages, info):
        calls.append(messages)
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, {"memories": [fact()]})]
        )

    with (
        patch.object(module, "_build_model", return_value=FunctionModel(model)),
        patch("app.services.memory_semantic.encode_query", return_value=(VECTOR, "test")),
        patch("app.services.memory_semantic.encode_note", return_value=(VECTOR, "test")) as encode,
        patch("mem0.memory.main.SQLiteManager", side_effect=AssertionError("No SQLite")),
        patch(
            "mem0.memory.main.VectorStoreFactory.create", side_effect=AssertionError("No second DB")
        ),
        patch("urllib.request.urlopen", side_effect=AssertionError("No notice downloads")),
    ):
        batch = await module.extract(
            TEXT,
            ["之前的语言偏好"],
            [],
            resolve_generation_config({}).model_dump(),
            scope=module.scope_key(uuid4(), None),
        )
    assert len(calls) == 1 and batch.usage["requests"] == 1
    assert batch.result.memories[0].quote == TEXT
    assert batch.vectors[TEXT] == VECTOR
    encode.assert_called_once_with("回答语言", TEXT)


@pytest.mark.anyio
async def test_sdk_preserves_authorized_correction_target_and_rejects_invented_quotes():
    old = item("之后请使用英语回答，并保留专业术语的英文名称。")

    def model(messages, info):
        assert old.content in str(messages)
        result = {
            "memories": [
                fact(action="update", target=0),
                fact("虚构的信息与用户无关", quote="从未在新消息出现的依据"),
            ]
        }
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, result)])

    with (
        patch.object(module, "_build_model", return_value=FunctionModel(model)),
        patch("app.services.memory_semantic.encode_query", return_value=(VECTOR, "test")),
        patch("app.services.memory_semantic.encode_note", return_value=(VECTOR, "test")),
        patch("app.services.memory_semantic.fingerprint", return_value="test"),
    ):
        batch = await module.extract(
            TEXT,
            [],
            [old],
            resolve_generation_config({}).model_dump(),
            scope=module.scope_key(old.user_id, old.project_id),
        )
    assert len(batch.result.memories) == 1
    assert batch.result.memories[0].action == "update" and batch.targets[0].id == old.id
    assert old.content != TEXT  # SDK did not mutate canonical or detached inputs.


@pytest.mark.anyio
async def test_sdk_hash_dedup_does_not_create_a_second_fact():
    old = item()

    def model(messages, info):
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, {"memories": [fact()]})]
        )

    with (
        patch.object(module, "_build_model", return_value=FunctionModel(model)),
        patch("app.services.memory_semantic.encode_query", return_value=(VECTOR, "test")),
        patch("app.services.memory_semantic.encode_note", return_value=(VECTOR, "test")),
        patch("app.services.memory_semantic.fingerprint", return_value="test"),
    ):
        batch = await module.extract(
            TEXT, [], [old], resolve_generation_config({}).model_dump(), scope="test-scope"
        )
    assert batch.result.memories == [] and batch.vectors == {}


def test_all_sdk_vector_operations_require_the_exact_server_scope():
    a, b = module.scope_key(uuid4(), None), module.scope_key(uuid4(), None)
    assert a != b
    uid = uuid4()
    assert module.scope_key(uid, None) != module.scope_key(uid, uuid4())
    store = module.ProjectStore(a, module.snapshot([item()]))
    for filters in (None, {}, {"user_id": b}, {"user_id": a, "project_id": "forged"}):
        with pytest.raises(ValueError):
            store.search("中文", VECTOR, 10, filters)
        with pytest.raises(ValueError):
            store.keyword_search("中文", 10, filters)
    with pytest.raises(ValueError):
        store.insert([VECTOR], [str(uuid4())], [{"user_id": b, "data": TEXT}])
    assert store.writes == {}


def test_real_sdk_search_ranks_only_scoped_pg_candidates_and_filters_expiry():
    active, expired, unselected = item(), item("过期的中文回答要求"), item("别的内容")
    from datetime import timedelta

    expired.expires_on = datetime.now(UTC).date() - timedelta(days=1)
    result = module.rank(
        "中文回答",
        [active, expired, unselected],
        {str(active.id): 0.9, str(expired.id): 0.95},
        VECTOR,
        scope="test-scope",
    )
    assert list(result) == [str(active.id)]


def test_sdk_is_single_pinned_engine_with_telemetry_and_nlp_downloads_disabled():
    import mem0
    from mem0.memory.telemetry import MEM0_TELEMETRY

    assert mem0.__version__ == "2.0.20" and MEM0_TELEMETRY is False
    assert module.spacy_models.get_nlp_full() is None
    assert module.spacy_models.get_nlp_lemma() is None
    assert ExtractionResult().memories == []


def test_extraction_keeps_complete_constraints_within_its_context_budget():
    from app.services.memory_recall import estimated_tokens

    notes = [item("中文约束" * 240 + f"最后的禁止条件{i}不可丢失。") for i in range(10)]
    store = module.ProjectStore("test-scope", module.snapshot(notes))
    with patch("app.services.memory_semantic.fingerprint", return_value="test"):
        rows = store.search("中文约束", VECTOR, 10, {"user_id": "test-scope"})
    assert 0 < len(rows) < 10
    assert sum(estimated_tokens(r.payload["data"]) + 40 for r in rows) <= 2400
    assert all(r.payload["data"] in {n.content for n in notes} for r in rows)
