import pytest

from triage.servicenow_relational import InMemoryServiceNowAdapter, ServiceNowRelationshipService


@pytest.mark.asyncio
async def test_semantic_search_returns_relevant_past_ticket(servicenow_tickets):
    service = ServiceNowRelationshipService(InMemoryServiceNowAdapter(servicenow_tickets))

    results = await service.search_past_tickets("Veeva login timeout")

    assert [ticket.number for ticket in results] == ["INC0010001", "INC0010002"]


@pytest.mark.asyncio
async def test_traverse_returns_parent_children_and_problem(servicenow_tickets):
    store = InMemoryServiceNowAdapter(
        servicenow_tickets,
        problems={"prb-7": {"number": "PRB0000007", "short_description": "Vault authentication latency"}},
    )
    relationships = await ServiceNowRelationshipService(store).traverse_relationships("parent-1")

    assert relationships["parent"] is None
    assert [child.number for child in relationships["children"]] == ["INC0010002"]
    assert relationships["problem"]["number"] == "PRB0000007"


@pytest.mark.asyncio
async def test_traverse_raises_for_missing_ticket():
    service = ServiceNowRelationshipService(InMemoryServiceNowAdapter([]))

    with pytest.raises(LookupError, match="was not found"):
        await service.traverse_relationships("missing")
