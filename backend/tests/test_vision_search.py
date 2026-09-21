import pytest

from triage.vision_search import VisionSearchService


@pytest.mark.asyncio
async def test_search_returns_top_knowledge_match(base64_image, vector_hit):
    from conftest import StubVectorStore, StubVisionClient

    store = StubVectorStore([vector_hit])
    result = await VisionSearchService(StubVisionClient(), store).search(base64_image)

    assert result.document_id == "445"
    assert result.document_title == "Resolve Veeva Vault Login Timeouts"
    assert result.document_reference == "Veeva Doc #445"
    assert result.confidence == pytest.approx(0.91)
    assert store.last_embedding == [0.12, 0.34]


@pytest.mark.asyncio
async def test_search_handles_no_vector_match(base64_image):
    from conftest import StubVectorStore, StubVisionClient

    result = await VisionSearchService(StubVisionClient(), StubVectorStore([])).search(base64_image)

    assert result.document_id == "UNMATCHED"
    assert result.confidence == 0.0


@pytest.mark.asyncio
async def test_search_rejects_invalid_image():
    from conftest import StubVectorStore, StubVisionClient

    with pytest.raises(ValueError, match="valid base64"):
        await VisionSearchService(StubVisionClient(), StubVectorStore([])).search("not base64!")
