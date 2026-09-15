"""Ask-the-user tool helpers.

Question schemas are shared with the durable graph. PostgreSQL checkpoints and
LangGraph interrupt own waiting and resumption; a browser connection is optional.
"""

from typing import Any

from app.services.clarification import ClarificationQuestion

MAX_QUESTIONS = 3
QuestionItem = ClarificationQuestion


def format_answers(questions: list[dict[str, Any]], answers: list[dict[str, Any]]) -> str:
    """Render the collected answers as a readable Q/A transcript for the model."""
    lines: list[str] = []
    for i, q in enumerate(questions):
        a = answers[i] if i < len(answers) else {}
        if not isinstance(a, dict):
            a = {}
        ans = "(skipped)" if a.get("skipped") else str(a.get("answer", "")).strip() or "(no answer)"
        lines.append(f"Q: {q.get('question', '')}\nA: {ans}")
    return "\n\n".join(lines)
