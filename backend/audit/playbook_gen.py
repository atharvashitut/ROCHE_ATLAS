"""Generate deterministic, parameterized change implementation checklists."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class PlaybookItem:
    order: int
    phase: str
    instruction: str


@dataclass(frozen=True)
class ImplementationPlaybook:
    change_id: str
    target: str
    items: tuple[PlaybookItem, ...]

    def as_dict(self) -> dict:
        return {"change_id": self.change_id, "target": self.target, "items": [asdict(item) for item in self.items]}


class PlaybookGenerator:
    def generate(self, handoff: object) -> ImplementationPlaybook:
        target = f"{handoff.system} ({handoff.environment})"
        steps = [
            PlaybookItem(1, "prepare", f"Confirm {handoff.owner} owns the {target} window starting {handoff.planned_start.isoformat()}"),
        ]
        order = 2
        for action in handoff.implementation_steps:
            steps.append(PlaybookItem(order, "implement", action.format(system=handoff.system, environment=handoff.environment)))
            order += 1
        for action in handoff.validation_steps:
            steps.append(PlaybookItem(order, "validate", action.format(system=handoff.system, environment=handoff.environment)))
            order += 1
        for action in handoff.backout_steps:
            steps.append(PlaybookItem(order, "backout", action.format(system=handoff.system, environment=handoff.environment)))
            order += 1
        steps.append(PlaybookItem(order, "close", f"Record evidence and close {handoff.change_id} after {handoff.planned_end.isoformat()}"))
        return ImplementationPlaybook(handoff.change_id, target, tuple(steps))
