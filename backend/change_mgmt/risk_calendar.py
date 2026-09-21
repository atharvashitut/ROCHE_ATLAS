"""Explainable CMDB and calendar-aware change risk scoring."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from change_mgmt.veeva_rules import ChangeType


@dataclass(frozen=True)
class ConfigurationItem:
    ci_id: str
    criticality: str
    owner: str


@dataclass(frozen=True)
class BlackoutWindow:
    name: str
    starts_at: datetime
    ends_at: datetime
    ci_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class RiskAssessment:
    score: int
    level: ChangeType
    blackout_conflicts: tuple[str, ...]
    factors: tuple[str, ...]


class CMDBCalendarAdapter(Protocol):
    async def get_cis(self, ci_ids: list[str]) -> list[ConfigurationItem]: ...
    async def get_blackouts(self, starts_at: datetime, ends_at: datetime, ci_ids: list[str]) -> list[BlackoutWindow]: ...


class MockCMDBCalendarAdapter:
    def __init__(self, cis: list[ConfigurationItem] | None = None, blackouts: list[BlackoutWindow] | None = None):
        self.cis = {ci.ci_id: ci for ci in cis or []}
        self.blackouts = blackouts or []

    async def get_cis(self, ci_ids: list[str]) -> list[ConfigurationItem]:
        return [self.cis[ci_id] for ci_id in ci_ids if ci_id in self.cis]

    async def get_blackouts(self, starts_at: datetime, ends_at: datetime, ci_ids: list[str]) -> list[BlackoutWindow]:
        return [
            window for window in self.blackouts
            if starts_at < window.ends_at and ends_at > window.starts_at
            and (not window.ci_ids or bool(set(ci_ids) & set(window.ci_ids)))
        ]


class RiskCalendarService:
    def __init__(self, adapter: CMDBCalendarAdapter):
        self.adapter = adapter

    async def assess(
        self,
        ci_ids: list[str],
        starts_at: datetime,
        ends_at: datetime,
        requested_type: ChangeType | None = None,
        has_backout_plan: bool = True,
    ) -> RiskAssessment:
        cis = await self.adapter.get_cis(ci_ids)
        blackouts = await self.adapter.get_blackouts(starts_at, ends_at, ci_ids)
        score = {ChangeType.LOW: 10, ChangeType.NORMAL: 35, ChangeType.EMERGENCY: 70}.get(requested_type or ChangeType.NORMAL, 35)
        factors = [f"Base risk for {(requested_type or ChangeType.NORMAL).value} change: {score}"]
        criticality_points = {"critical": 25, "high": 15, "medium": 8, "low": 3}
        for ci in cis:
            points = criticality_points.get(ci.criticality.lower(), 8)
            score += points
            factors.append(f"CI {ci.ci_id} criticality ({ci.criticality}) adds {points}")
        duration_minutes = (ends_at - starts_at).total_seconds() / 60
        if duration_minutes > 120:
            score += 10
            factors.append("Implementation window over 120 minutes adds 10")
        if blackouts:
            score += 35
            factors.append(f"Blackout conflict ({', '.join(window.name for window in blackouts)}) adds 35")
        if not has_backout_plan:
            score += 15
            factors.append("No declared backout plan adds 15")
        score = min(100, int(score))
        level = ChangeType.EMERGENCY if score >= 85 else ChangeType.NORMAL if score > 30 else ChangeType.LOW
        return RiskAssessment(score, level, tuple(window.name for window in blackouts), tuple(factors))
