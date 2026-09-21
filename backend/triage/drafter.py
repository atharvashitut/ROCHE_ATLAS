"""Turn retrieval confidence into an appropriate support response."""

from dataclasses import dataclass
from enum import StrEnum

from triage.vision_search import KnowledgeMatch


class DraftType(StrEnum):
    CUSTOMER_RESOLUTION = "customer_resolution"
    L3_ESCALATION = "l3_escalation"


@dataclass(frozen=True)
class Draft:
    kind: DraftType
    content: str


def draft_response(match: KnowledgeMatch, confidence_threshold: float = 0.75) -> Draft:
    if match.confidence >= confidence_threshold:
        return Draft(
            kind=DraftType.CUSTOMER_RESOLUTION,
            content=(
                f"We identified guidance that matches this issue: {match.document_title} "
                f"({match.document_reference}). Please follow the documented resolution steps. "
                f"Screenshot analysis: {match.analysis}"
            ),
        )
    return Draft(
        kind=DraftType.L3_ESCALATION,
        content=(
            "L3 escalation summary\n"
            f"Observed: {match.analysis}\n"
            f"Best knowledge match: {match.document_title} ({match.document_reference})\n"
            f"Match confidence: {match.confidence:.0%}. Please investigate product logs and confirm impact."
        ),
    )
