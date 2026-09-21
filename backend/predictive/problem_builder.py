"""Create ServiceNow Problem Records for recurring or high-impact incidents."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ProblemRecord:
    number: str
    short_description: str
    service: str
    priority: str
    incident_references: tuple[str, ...]
    assignment_group: str
    trigger_reason: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ProblemDecision:
    should_create: bool
    reason: str
    record: ProblemRecord | None = None

    def as_dict(self) -> dict:
        return {"should_create": self.should_create, "reason": self.reason, "record": self.record.as_dict() if self.record else None}


class ProblemRecordBuilder:
    def __init__(self, recurrence_threshold: int = 3):
        self.recurrence_threshold = recurrence_threshold

    def build(
        self,
        service: str,
        summary: str,
        incident_numbers: list[str],
        recurrence_count: int,
        high_impact_outage: bool,
    ) -> ProblemDecision:
        recurring = recurrence_count >= self.recurrence_threshold
        if not recurring and not high_impact_outage:
            return ProblemDecision(False, f"Recurrence count {recurrence_count} is below threshold {self.recurrence_threshold} and no high-impact outage was declared.")
        reason = "high-impact outage" if high_impact_outage else f"recurrence threshold reached ({recurrence_count})"
        priority = "P1" if high_impact_outage else "P2"
        stable_seed = sum(ord(character) for character in f"{service}|{summary}|{'|'.join(incident_numbers)}") % 1000000
        record = ProblemRecord(
            number=f"PRB{stable_seed:07d}",
            short_description=summary,
            service=service,
            priority=priority,
            incident_references=tuple(incident_numbers),
            assignment_group="problem_management",
            trigger_reason=reason,
        )
        return ProblemDecision(True, reason, record)
