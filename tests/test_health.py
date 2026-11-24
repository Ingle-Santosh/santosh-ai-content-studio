import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_endpoint(api_client: AsyncClient) -> None:
    response = await api_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["local_only"] is True
    assert data["env"] == "test"
    assert "ollama_base_url" in data
    assert "default_model" in data
