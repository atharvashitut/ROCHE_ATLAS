"""LLM-context-assisted root cause analysis with traceable evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol


@dataclass(frozen=True)
class LogTrace:
    trace_id: str
    content: str


@dataclass(frozen=True)
class TicketHistory:
    number: str
    summary: str
    impact: str = "medium"


@dataclass(frozen=True)
class RootCauseCandidate:
    cause: str
    confidence: float
    rationale: str


@dataclass(frozen=True)
class EvidenceLink:
    label: str
    href: str
    excerpt: str


@dataclass(frozen=True)
class RootCauseAnalysis:
    probable_causes: tuple[RootCauseCandidate, ...]
    evidence_links: tuple[EvidenceLink, ...]
    llm_context: str

    def as_dict(self) -> dict:
        return {
            "probable_causes": [asdict(cause) for cause in self.probable_causes],
            "evidence_links": [asdict(link) for link in self.evidence_links],
        }


class LLMContextAdapter(Protocol):
    async def generate(self, context: str) -> list[RootCauseCandidate]: ...


class MockLLMContextAdapter:
    """Deterministic stand-in for an LLM completion endpoint in local environments."""

    async def generate(self, context: str) -> list[RootCauseCandidate]:
        lower_context = context.lower()
        if "timeout" in lower_context or "latency" in lower_context:
            return [RootCauseCandidate("Upstream service timeout or authentication latency", 0.84, "Repeated timeout signatures occur in logs and incident history.")]
        if "certificate" in lower_context or "tls" in lower_context:
            return [RootCauseCandidate("Expired or mismatched service certificate", 0.78, "TLS/certificate errors recur across the supplied traces.")]
        return [RootCauseCandidate("Insufficient correlated evidence", 0.35, "The supplied logs and history do not share a strong failure signature.")]


class RootCauseEngine:
    def __init__(self, llm_adapter: LLMContextAdapter):
        self.llm_adapter = llm_adapter

    async def analyse(self, logs: list[LogTrace], tickets: list[TicketHistory]) -> RootCauseAnalysis:
        if not logs and not tickets:
            raise ValueError("at least one log trace or ticket history entry is required")
        context = self._build_context(logs, tickets)
        causes = await self.llm_adapter.generate(context)
        evidence = tuple(
            [EvidenceLink(f"Log {trace.trace_id}", f"log://traces/{trace.trace_id}", trace.content[:180]) for trace in logs]
            + [EvidenceLink(ticket.number, f"servicenow://incidents/{ticket.number}", ticket.summary[:180]) for ticket in tickets]
        )
        return RootCauseAnalysis(tuple(self._normalise_confidence(cause) for cause in causes), evidence, context)

    @staticmethod
    def _build_context(logs: list[LogTrace], tickets: list[TicketHistory]) -> str:
        log_context = "\n".join(f"LOG {trace.trace_id}: {trace.content}" for trace in logs)
        ticket_context = "\n".join(f"TICKET {ticket.number} [{ticket.impact}]: {ticket.summary}" for ticket in tickets)
        return f"Analyze correlated operational evidence.\n{log_context}\n{ticket_context}".strip()

    @staticmethod
    def _normalise_confidence(candidate: RootCauseCandidate) -> RootCauseCandidate:
        return RootCauseCandidate(candidate.cause, max(0.0, min(1.0, candidate.confidence)), candidate.rationale)
