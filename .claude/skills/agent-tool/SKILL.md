---
name: agent-tool
description: Add a typed, authorized tool to the project's native LangGraph execution graph.
---

# Add an Agent Tool (LangGraph)

Agent tools live in `backend/app/agents/tools/` and are surfaced to the model so it can call them mid-conversation. The assistant is defined in `backend/app/agents/`.

## Steps

1. **Write the tool function** in `backend/app/agents/tools/<tool_name>.py`:
   - Async, fully type-hinted, with a clear docstring — **the docstring and signature are what the model sees**, so make them precise.
   - Take typed args and return a bounded JSON-serializable result. Raise `ToolRetry` for recoverable input errors; propagate permission, cancellation and service failures.
   - Keep secrets/IO behind `settings` and the service layer; don't inline credentials.

2. **Authorize it:** add its specification to `tool_catalog.py` and the appropriate policy. Register it only when allowed; recheck authorization before effects.

3. **Register it** in `AssistantAgent.registry` or the durable graph's registry:
   - Decorate with `@registry.register` (injects `ToolContext`) or `@registry.register_plain` (no context):
     ```python
     from app.agents.runtime import ToolContext

     @registry.register
     async def my_tool(ctx: ToolContext, query: str) -> dict:
         """One-line description the model reads to decide when to call this."""
         ...
     ```

4. **Prompt guidance (optional but recommended):** if the tool should only be used in specific situations, add a sentence to the system prompt in `app/agents/prompts.py` so the model knows *when* to reach for it.

5. **Frontend rendering (optional):** tool calls render as cards in the chat UI. For a bespoke card, add a renderer under `frontend/src/components/chat/tool-results/`; otherwise the generic card handles it.

6. **Test it:** test the function, schema validation and authorization. Use `tests/model_fixtures.py` for native model fixtures and `tests/test_native_runtime.py` for checkpoint recovery patterns.

## Rules

- The docstring is the contract with the model — keep it accurate and action-oriented.
- Return small, structured payloads; don't dump huge blobs into the context.
- Long-running or side-effecting work belongs in a service (and possibly a background task), not inline in the tool.
- Each completed tool has a checkpoint; external effects still need durable idempotency keys for crashes before checkpoint persistence.
- See `docs/howto/add-agent-tool.md` for a fuller walkthrough.
