import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_artifacts_api_lifecycle_and_isolation(api_client: AsyncClient) -> None:
    p1 = (
        await api_client.post("/api/projects", json={"topic": "SQL Window Functions Explained"})
    ).json()
    p2 = (await api_client.post("/api/projects", json={"topic": "MLOps Pipeline Basics"})).json()

    # Save v1 artifact
    resp1 = await api_client.post(
        f"/api/projects/{p1['id']}/artifacts",
        json={
            "stage": "research",
            "artifact_type": "research_brief",
            "name": "research_brief.md",
            "content": "# Research Brief\nWindow functions partition data.",
            "metadata_json": {"generator": "manual"},
        },
    )
    assert resp1.status_code == 201
    art1 = resp1.json()
    assert art1["version"] == 1
    assert art1["relative_path"] == "01_research/research_brief_v1.md"
    assert len(art1["checksum_sha256"]) == 64

    # Read content
    content_resp = await api_client.get(f"/api/projects/{p1['id']}/artifacts/{art1['id']}/content")
    assert content_resp.status_code == 200
    assert "Window functions partition data." in content_resp.json()["content"]

    # Verify integrity
    verify_resp = await api_client.get(f"/api/projects/{p1['id']}/artifacts/{art1['id']}/verify")
    assert verify_resp.status_code == 200
    assert verify_resp.json()["is_valid"] is True

    # Cross-project isolation returns 404
    cross_resp = await api_client.get(f"/api/projects/{p2['id']}/artifacts/{art1['id']}")
    assert cross_resp.status_code == 404

    # Path traversal in explicit relative_path returns 400
    bad_path = await api_client.post(
        f"/api/projects/{p1['id']}/artifacts",
        json={
            "stage": "research",
            "artifact_type": "research_brief",
            "name": "evil.md",
            "relative_path": "../escape.md",
            "content": "nope",
        },
    )
    assert bad_path.status_code == 400

    # Filter list
    list_resp = await api_client.get(
        f"/api/projects/{p1['id']}/artifacts",
        params={"stage": "research", "artifact_type": "research_brief"},
    )
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_guidelines_api_autoseed_and_update(api_client: AsyncClient) -> None:
    active_resp = await api_client.get("/api/guidelines/active")
    assert active_resp.status_code == 200
    active = active_resp.json()
    assert active["slug"] == "santosh-analytics"
    assert active["guidelines_json"]["narration_language"] == "Hinglish"

    put_resp = await api_client.put(
        "/api/guidelines/santosh-analytics",
        json={
            "channel_name": "Santosh Analytics",
            "is_active": True,
            "guidelines": {
                "narration_language": "Hinglish",
                "extra_rules": ["Always include a real-world architecture diagram."],
            },
        },
    )
    assert put_resp.status_code == 200
    updated = put_resp.json()
    assert updated["guidelines_json"]["extra_rules"] == [
        "Always include a real-world architecture diagram."
    ]

    list_resp = await api_client.get("/api/guidelines")
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_approvals_api_promotes_linked_artifact(api_client: AsyncClient) -> None:
    project = (
        await api_client.post("/api/projects", json={"topic": "Agentic AI Design Patterns"})
    ).json()
    artifact = (
        await api_client.post(
            f"/api/projects/{project['id']}/artifacts",
            json={
                "stage": "script",
                "artifact_type": "script",
                "name": "script.md",
                "content": "# Hook\nLet's build agentic workflows!",
            },
        )
    ).json()
    assert artifact["status"] == "DRAFT"

    # Request approval linked to artifact
    req_resp = await api_client.post(
        f"/api/projects/{project['id']}/approvals",
        json={
            "gate": "script",
            "artifact_id": artifact["id"],
            "comments": "Please review Hinglish tone.",
        },
    )
    assert req_resp.status_code == 201
    approval = req_resp.json()
    assert approval["status"] == "PENDING"

    # Reject PENDING as a decision
    bad_decision = await api_client.patch(
        f"/api/approvals/{approval['id']}",
        json={"status": "PENDING"},
    )
    assert bad_decision.status_code == 400

    # Approve -> linked artifact becomes APPROVED
    ok_decision = await api_client.patch(
        f"/api/approvals/{approval['id']}",
        json={
            "status": "APPROVED",
            "reviewer": "Santosh",
            "comments": "Great pacing!",
        },
    )
    assert ok_decision.status_code == 200
    decided = ok_decision.json()
    assert decided["status"] == "APPROVED"
    assert decided["decided_at"] is not None

    refreshed_art = (
        await api_client.get(f"/api/projects/{project['id']}/artifacts/{artifact['id']}")
    ).json()
    assert refreshed_art["status"] == "APPROVED"
