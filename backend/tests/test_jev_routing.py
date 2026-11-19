"""Decision-service contracts and permission-preserving orchestration fallback."""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.clients import jev
from app.services import chat_execution as chat
from app.services.model_config import resolve_generation_config


def response(choice="knowledge_collaboration", confidence=0.9):
    return {
        "model": "jev-1.14.0",
        "answers": {
            "route": {
                "type": "choice",
                "choice": choice,
                "confidence": confidence,
                "probabilities": {key: 0.94 if key == choice else 0.03 for key in jev.CRITERIA},
            }
        },
        "usage": {"input_tokens": 130, "output_tokens": 0},
    }


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch):
    monkeypatch.setattr(chat.settings, "JEV_ROUTING_MODE", "active")
    monkeypatch.setattr(chat.settings, "JEV_API_KEY", SecretStr("test-jev-key"))
    monkeypatch.setattr(chat.settings, "JEV_MIN_CONFIDENCE", 0.8)
    monkeypatch.setattr(chat.settings, "JEV_TIMEOUT_SECONDS", 0.2)


def request(**updates):
    return {
        # Deliberately lacks the baseline regex keywords.
        "prompt": "将几份资料中的结论逐一交叉核验，解释相互矛盾之处并形成研究报告",
        "knowledge_base_ids": ["authorized-base"],
        "knowledge_strict": True,
        "knowledge_document_ids": None,
        "file_ids": [],
        **updates,
    }


async def choose(data=None):
    return await chat.choose_route(
        data or request(),
        {"query": "resolved question", "history": ["private history"], "memory_context": "private"},
        resolve_generation_config({}),
    )


@pytest.mark.anyio
async def test_http_contract_uses_separate_credential_and_minimal_state():
    observed = []

    def handler(req):
        observed.append(req)
        return httpx.Response(200, json=response())

    factory = httpx.AsyncClient
    with patch.object(
        jev.httpx,
        "AsyncClient",
        side_effect=lambda **kwargs: factory(transport=httpx.MockTransport(handler), **kwargs),
    ):
        result = await choose()
    assert result["route"] == "knowledge_collaboration"
    assert result["decision"]["applied"] is True
    assert result["decision"]["model"] == "jev-1.14.0"
    assert len(observed) == 1
    assert str(observed[0].url) == "https://api.typesafe.ai/v1/systemone"
    assert observed[0].headers["Authorization"] == "Bearer test-jev-key"
    payload = json.loads(observed[0].content)
    assert payload["state"] == {
        "message": request()["prompt"],
        "resolved_question": "resolved question",
    }
    assert set(payload["questions"]["route"]["criteria"]) == set(jev.CRITERIA)
    assert "private" not in observed[0].content.decode()
    assert "test-jev-key" not in json.dumps(result)


@pytest.mark.anyio
@pytest.mark.parametrize("choice", ["standard", "knowledge_collaboration"])
async def test_active_confident_route_skips_generation_router(choice):
    with (
        patch.object(
            chat, "classify_route", AsyncMock(return_value=jev.JevResponse(**response(choice)))
        ),
        patch.object(chat, "structured_call") as agent,
    ):
        result = await choose()
    assert result["route"] == choice
    assert set(result) == {"route", "reason", "decision"}
    agent.assert_not_called()


@pytest.mark.anyio
async def test_shadow_preserves_baseline_and_records_disagreement(monkeypatch):
    monkeypatch.setattr(chat.settings, "JEV_ROUTING_MODE", "shadow")
    with patch.object(
        chat, "classify_route", AsyncMock(return_value=jev.JevResponse(**response()))
    ):
        result = await choose()
    assert result["route"] == "standard"
    assert result["decision"]["disagrees"] is True
    assert result["decision"]["applied"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("choice,confidence", [("none", 0.99), ("knowledge_collaboration", 0.79)])
async def test_uncertain_or_none_falls_back(choice, confidence):
    with patch.object(
        chat,
        "classify_route",
        AsyncMock(return_value=jev.JevResponse(**response(choice, confidence))),
    ):
        result = await choose()
    assert result["route"] == "standard"
    assert result["decision"]["status"] == "abstained"


@pytest.mark.anyio
async def test_service_error_does_not_persist_sensitive_exception():
    with patch.object(chat, "classify_route", AsyncMock(side_effect=TimeoutError("secret body"))):
        result = await choose()
    assert result["route"] == "standard"
    assert result["decision"]["status"] == "unavailable"
    assert "secret body" not in json.dumps(result)


@pytest.mark.anyio
async def test_failure_still_uses_existing_confident_collaboration_route():
    baseline = {"route": "knowledge_collaboration", "reason": "existing router choice"}
    with (
        patch.object(chat, "classify_route", AsyncMock(side_effect=TimeoutError)),
        patch.object(chat, "_choose_existing_route", AsyncMock(return_value=baseline)) as fallback,
    ):
        result = await choose()
    fallback.assert_awaited_once()
    assert result["route"] == "knowledge_collaboration"
    assert result["decision"]["applied"] is False
    assert result["decision"]["status"] == "unavailable"


@pytest.mark.anyio
async def test_cancellation_is_not_swallowed():
    with (
        patch.object(chat, "classify_route", AsyncMock(side_effect=asyncio.CancelledError)),
        pytest.raises(asyncio.CancelledError),
    ):
        await choose()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "updates",
    [
        {"knowledge_base_ids": []},
        {"knowledge_strict": False},
        {"file_ids": ["file"]},
        {"knowledge_document_ids": ["document"]},
        {"knowledge_document_ids": []},
    ],
)
async def test_restricted_routes_never_call_decision_service(updates):
    with patch.object(chat, "classify_route", AsyncMock()) as classify:
        assert (await choose(request(**updates)))["route"] == "standard"
    classify.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize("condition", ["off", "missing_key", "long", "work_context"])
async def test_disabled_unconfigured_and_incomplete_goals_send_nothing(condition, monkeypatch):
    data = request()
    context = {"query": "resolved"}
    if condition == "off":
        monkeypatch.setattr(chat.settings, "JEV_ROUTING_MODE", "off")
    elif condition == "missing_key":
        monkeypatch.setattr(chat.settings, "JEV_API_KEY", SecretStr(""))
    elif condition == "long":
        data["prompt"] = "x" * 8001
    else:
        context["work_context"] = "authoritative work requirements"
    with patch.object(chat, "classify_route", AsyncMock()) as classify:
        result = await chat.choose_route(data, context, resolve_generation_config({}))
    classify.assert_not_awaited()
    assert result["route"] == "standard"


@pytest.mark.parametrize("mutation", ["unknown", "nan", "missing", "sum", "winner", "bool"])
def test_invalid_provider_choices_are_rejected(mutation):
    body = response()
    answer = body["answers"]["route"]
    if mutation == "unknown":
        answer["choice"] = "run_arbitrary_code"
    elif mutation == "nan":
        answer["confidence"] = float("nan")
    elif mutation == "missing":
        del answer["probabilities"]["none"]
    elif mutation == "sum":
        answer["probabilities"]["standard"] = 0.8
    elif mutation == "winner":
        answer["choice"] = "standard"
    else:
        answer["confidence"] = True
    with pytest.raises(ValidationError):
        jev.JevResponse.model_validate(body)


@pytest.mark.anyio
@pytest.mark.parametrize("status", [302, 401, 429, 503])
async def test_http_errors_and_redirects_fall_back_without_retry(status):
    seen = []

    def handler(req):
        seen.append(req)
        return httpx.Response(status, headers={"Location": "https://other.invalid"})

    factory = httpx.AsyncClient
    with patch.object(
        jev.httpx,
        "AsyncClient",
        side_effect=lambda **kwargs: factory(transport=httpx.MockTransport(handler), **kwargs),
    ):
        result = await choose()
    assert len(seen) == 1
    assert result["route"] == "standard"
    assert result["decision"]["status"] == "unavailable"


@pytest.mark.anyio
async def test_total_deadline_is_bounded(monkeypatch):
    monkeypatch.setattr(chat.settings, "JEV_TIMEOUT_SECONDS", 0.01)

    async def handler(req):
        await asyncio.sleep(1)
        return httpx.Response(200, json=response())

    factory = httpx.AsyncClient
    with patch.object(
        jev.httpx,
        "AsyncClient",
        side_effect=lambda **kwargs: factory(transport=httpx.MockTransport(handler), **kwargs),
    ):
        result = await choose()
    assert result["decision"]["error_type"] == "TimeoutError"
    assert result["route"] == "standard"


@pytest.mark.anyio
@pytest.mark.parametrize("body", [{}, {"answers": {}}, {"unexpected": "secret raw body"}])
async def test_malformed_http_response_is_not_used_or_exposed(body):
    factory = httpx.AsyncClient
    with patch.object(
        jev.httpx,
        "AsyncClient",
        side_effect=lambda **kwargs: factory(
            transport=httpx.MockTransport(lambda req: httpx.Response(200, json=body)), **kwargs
        ),
    ):
        result = await choose()
    assert result["route"] == "standard"
    assert result["decision"]["error_type"] == "ValidationError"
    assert "secret raw body" not in json.dumps(result)
