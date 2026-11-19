"""Build trusted role envelopes from checked claims, never from model self-ratings."""

from app.schemas.agent_handoff import EvidenceReference, RoleHandoff
from app.services.knowledge_answer import GroundedAnswer, validate_answer


def evidence_handoff(role, findings, sources):
    text, cited = validate_answer(GroundedAnswer.model_validate(findings), sources)
    return RoleHandoff(
        role=role,
        validation="source_quotes_checked" if cited else "no_support",
        summary=text,
        evidence=[
            EvidenceReference(
                source_id=str(s["id"]),
                document_id=str(s["document_id"]),
                index=s["index"],
                revision=s.get("revision"),
                file_version=s.get("file_version"),
                quotes=s["quotes"],
            )
            for s in cited
        ],
    )


def review_handoff(review):
    return RoleHandoff(
        role="critic",
        validation="review_approved" if review["approved"] else "review_rejected",
        summary="审校通过" if review["approved"] else "审校仍有待解决问题",
        issues=review["issues"],
    )
