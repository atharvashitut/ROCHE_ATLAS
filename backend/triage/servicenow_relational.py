"""ServiceNow ticket search and relationship traversal adapters."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Protocol

import httpx


@dataclass(frozen=True)
class ServiceNowTicket:
    sys_id: str
    number: str
    short_description: str
    state: str
    parent: str | None = None
    problem_id: str | None = None


class TicketStore(Protocol):
    async def semantic_search(self, query: str, limit: int = 5) -> list[ServiceNowTicket]: ...
    async def get_ticket(self, sys_id: str) -> ServiceNowTicket | None: ...
    async def get_children(self, sys_id: str) -> list[ServiceNowTicket]: ...
    async def get_problem(self, sys_id: str) -> dict[str, str] | None: ...


class InMemoryServiceNowAdapter:
    """Mock-friendly ServiceNow adapter used for local development and tests."""

    def __init__(self, tickets: Iterable[ServiceNowTicket], problems: dict[str, dict[str, str]] | None = None):
        self.tickets = {ticket.sys_id: ticket for ticket in tickets}
        self.problems = problems or {}

    async def semantic_search(self, query: str, limit: int = 5) -> list[ServiceNowTicket]:
        query_terms = set(query.lower().split())
        ranked = sorted(
            self.tickets.values(),
            key=lambda ticket: len(query_terms & set(ticket.short_description.lower().split())),
            reverse=True,
        )
        return [ticket for ticket in ranked if query_terms & set(ticket.short_description.lower().split())][:limit]

    async def get_ticket(self, sys_id: str) -> ServiceNowTicket | None:
        return self.tickets.get(sys_id)

    async def get_children(self, sys_id: str) -> list[ServiceNowTicket]:
        return [ticket for ticket in self.tickets.values() if ticket.parent == sys_id]

    async def get_problem(self, sys_id: str) -> dict[str, str] | None:
        return self.problems.get(sys_id)


class ServiceNowRestAdapter:
    """REST adapter that maps ServiceNow incident/problem records to domain objects."""

    def __init__(self, instance_url: str, username: str, password: str, client: httpx.AsyncClient | None = None):
        self.instance_url = instance_url.rstrip("/")
        self.auth = (username, password)
        self.client = client

    async def _get(self, table: str, query: str) -> list[dict[str, Any]]:
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=20)
        try:
            response = await client.get(
                f"{self.instance_url}/api/now/table/{table}",
                auth=self.auth,
                params={"sysparm_query": query, "sysparm_limit": "50"},
            )
            response.raise_for_status()
            return response.json().get("result", [])
        except httpx.HTTPError as exc:
            raise RuntimeError("ServiceNow request failed") from exc
        finally:
            if owns_client:
                await client.aclose()

    async def semantic_search(self, query: str, limit: int = 5) -> list[ServiceNowTicket]:
        records = await self._get("incident", f"short_descriptionLIKE{query}")
        return [_ticket_from_record(record) for record in records[:limit]]

    async def get_ticket(self, sys_id: str) -> ServiceNowTicket | None:
        records = await self._get("incident", f"sys_id={sys_id}")
        return _ticket_from_record(records[0]) if records else None

    async def get_children(self, sys_id: str) -> list[ServiceNowTicket]:
        return [_ticket_from_record(record) for record in await self._get("incident", f"parent={sys_id}")]

    async def get_problem(self, sys_id: str) -> dict[str, str] | None:
        records = await self._get("problem", f"sys_id={sys_id}")
        return records[0] if records else None


class ServiceNowRelationshipService:
    def __init__(self, store: TicketStore):
        self.store = store

    async def search_past_tickets(self, query: str, limit: int = 5) -> list[ServiceNowTicket]:
        return await self.store.semantic_search(query, limit)

    async def traverse_relationships(self, ticket_id: str) -> dict[str, Any]:
        ticket = await self.store.get_ticket(ticket_id)
        if ticket is None:
            raise LookupError(f"ServiceNow ticket {ticket_id} was not found")
        parent = await self.store.get_ticket(ticket.parent) if ticket.parent else None
        children = await self.store.get_children(ticket.sys_id)
        problem = await self.store.get_problem(ticket.problem_id) if ticket.problem_id else None
        return {"ticket": ticket, "parent": parent, "children": children, "problem": problem}


def _ticket_from_record(record: dict[str, Any]) -> ServiceNowTicket:
    parent = _reference_id(record.get("parent"))
    problem = _reference_id(record.get("problem_id"))
    return ServiceNowTicket(
        sys_id=str(record["sys_id"]),
        number=str(record.get("number", "")),
        short_description=str(record.get("short_description", "")),
        state=str(record.get("state", "")),
        parent=parent,
        problem_id=problem,
    )


def _reference_id(reference: Any) -> str | None:
    value = reference.get("value") if isinstance(reference, dict) else reference
    return str(value) if value else None
