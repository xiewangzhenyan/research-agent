"""Fixed-source benchmark adapter for the same production collaboration nodes."""

import copy

from app.schemas.knowledge_answer import GroundedAnswer
from app.schemas.research_evaluation import ResearchCase
from app.services.knowledge_collaboration import _compile_collaboration_graph


def build_source_collaboration_graph(case: ResearchCase, configuration, *, checkpointer=None):
    # Copy caller-owned data so later mutations cannot change an in-flight trial.
    case = case.model_copy(deep=True)
    sources = [source.model_dump() for source in case.sources]

    async def authorize(state):
        if state.get("base_ids") or state.get("prompt") != case.question:
            raise ValueError("Benchmark scope changed")
        if "sources" in state and state["sources"] != sources:
            raise ValueError("Benchmark source snapshot changed")

    async def retrieve(state, queries):
        # Every route receives the same source order/indices; no query-based selection.
        await authorize(state)
        return copy.deepcopy(sources), []

    async def emit(kind, data):
        # Benchmark results are captured explicitly, never logged as runtime retrieval.
        pass

    return _compile_collaboration_graph(
        checkpointer,
        configuration=configuration,
        emit=emit,
        authorize=authorize,
        retrieve=retrieve,
    )


async def run_source_collaboration(case: ResearchCase, configuration):
    graph = build_source_collaboration_graph(case, configuration.model_dump())
    state = await graph.ainvoke({"prompt": case.question, "base_ids": []})
    collaboration = state["collaboration"]
    usage = state.get("usage", {})
    return {
        "answer": state.get("draft", GroundedAnswer(sufficient=False).model_dump()),
        "usage": {key: usage[key] for key in ("input_tokens", "output_tokens")}
        if usage.get("usage_complete")
        else None,
        "collaboration": {
            "version": collaboration["version"],
            "approved": collaboration["review"]["approved"],
            "revisions": collaboration["revisions"],
        },
    }
