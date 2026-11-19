# How to: Add a New Agent Tool

LangGraph executes model and tool nodes. `ToolRegistry` registers typed functions
as native LangChain `StructuredTool` instances; it does not run an agent loop.

Add a tool specification to `app/agents/tool_catalog.py` and include it in the
appropriate authorization policy. Register the function only when its name is
in the resolved allowed-tool set. See `AssistantAgent.registry` and the document
and Python registrations in `app/services/agent_run_graph.py` for working examples.

```python
from app.agents.runtime import ToolContext, ToolRetry

# Inside registry construction, after resolving allowed tools:
if "lookup_record" in allowed:
    @registry.register(name="lookup_record")
    async def lookup_record(ctx: ToolContext, record_id: str) -> dict:
        """Read one record available to the current user."""
        await ctx.deps.authorize_tool("lookup_record")
        if not record_id.strip():
            raise ToolRetry("Supply a non-empty record ID")
        return await read_authorized_record(ctx.deps.user_id, record_id)
```

The snippet assumes an application `read_authorized_record` function. Enforce
object ownership there too. Plain functions without injected dependencies use
`@registry.register_plain`. Parameter schemas come from function annotations;
Pydantic validates them before dispatch. Keep docstrings specific and results bounded.

Raise `ToolRetry` only for recoverable input mistakes. Permission, cancellation
and service errors must propagate; do not disguise them as successful results.
Durable questions use `ToolDeferred` and the existing outer `await_input` flow.
MCP tools must retain exact-argument consent and the dispatch ledger.

Each completed tool has its own checkpoint. A crash between an external effect
and checkpoint persistence can still retry a tool: use a durable idempotency key
for effects. Keep tool deadlines explicit and recheck permissions before effects.

Test schema validation, authorization and recovery using the native
`tests.model_fixtures.ScriptedModel`; see `tests/test_native_runtime.py`.

For a new assistant role, define an `AgentDefinition` and call `create_agent`
from `app/agents/factory.py`. Set its `ExecutionLimits` there. Shared checks belong
in `ExecutionPolicy`; retain object permissions and idempotency in the service.
Research roles with an output schema cannot acquire an executable tool registry.
