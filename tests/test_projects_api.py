import pytest
from httpx import AsyncClient

from content_studio.storage.artifact_store import PROJECT_STAGE_DIRS, ArtifactStore


@pytest.mark.asyncio
async def test_project_crud_lifecycle(
    api_client: AsyncClient,
    artifact_store: ArtifactStore,
) -> None:
    # Create project
    create_resp = await api_client.post(
        "/api/projects",
        json={
            "topic": "RAG vs CAG vs MAG: Architectural Trade-offs",
            "config": {
                "duration_minutes": 18,
                "language": "Hinglish",
                "audience_level": "Intermediate (Data/AI Engineers)",
            },
        },
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    project_id = created["id"]
    assert created["title"] == "RAG vs CAG vs MAG: Architectural Trade-offs"
    assert created["status"] == "CREATED"
    assert created["config"]["duration_minutes"] == 18

    # Filesystem stage directories were scaffolded
    project_root = artifact_store.project_dir(project_id)
    assert project_root.is_dir()
    for stage in PROJECT_STAGE_DIRS:
        assert (project_root / stage).is_dir()

    # List projects
    list_resp = await api_client.get("/api/projects")
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] == 1

    # Get project by ID
    get_resp = await api_client.get(f"/api/projects/{project_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == project_id

    # Patch project
    patch_resp = await api_client.patch(
        f"/api/projects/{project_id}",
        json={"title": "RAG vs CAG Deep Dive", "status": "IN_PROGRESS"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["title"] == "RAG vs CAG Deep Dive"
    assert patch_resp.json()["status"] == "IN_PROGRESS"

    # Delete project
    del_resp = await api_client.delete(f"/api/projects/{project_id}")
    assert del_resp.status_code == 204
    assert not project_root.exists()

    # Confirm 404 after delete
    missing_resp = await api_client.get(f"/api/projects/{project_id}")
    assert missing_resp.status_code == 404


@pytest.mark.asyncio
async def test_create_project_rejects_blank_topic(api_client: AsyncClient) -> None:
    resp = await api_client.post("/api/projects", json={"topic": "   "})
    assert resp.status_code == 422
