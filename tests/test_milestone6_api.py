import json

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_artifact_store, get_model_router, get_settings
from app.main import create_app
from content_studio.config.settings import Settings
from content_studio.database.models.enums import ScriptSectionType
from content_studio.database.repositories import ProjectRepository, UsageRepository
from content_studio.database.session import get_db_session
from content_studio.providers.llm import (
    BaseLLMProvider,
    LLMRequest,
    LLMResponse,
    ModelRouter,
    ProviderHealth,
)
from content_studio.services.script_validator import REQUIRED_SECTIONS
from content_studio.storage.artifact_store import ArtifactStore


class _MockM6LLM(BaseLLMProvider):
    provider_name = "ollama"
    is_cloud = False

    async def generate(self, request: LLMRequest) -> LLMResponse:
        prompt = request.messages[-1].content
        if "Approved Script Sections" in prompt:
            payload = {
                "summary": "Two clean scenes covering intro and live SQL demo.",
                "scenes": [
                    {
                        "scene_number": 1,
                        "title": "Intro Scene",
                        "estimated_duration_seconds": 45,
                        "narration": "Namaste devs, aaj SQL window functions seekhenge.",
                        "on_screen_text": "SQL Window Functions",
                        "visual_type": "face_cam",
                        "asset_requirements": [],
                        "related_script_section": "hook",
                    },
                    {
                        "scene_number": 2,
                        "title": "Live Query Demo",
                        "estimated_duration_seconds": 120,
                        "narration": "OVER() clause kaise rows preserve karta hai dekhiye.",
                        "on_screen_text": "SELECT ..., ROW_NUMBER() OVER(...)",
                        "visual_type": "code_demo",
                        "asset_requirements": [
                            {
                                "asset_type": "code_demo",
                                "title": "window_functions.sql",
                                "description": "Runnable SQLite query demo.",
                            }
                        ],
                        "related_script_section": "practical_demonstration",
                    },
                ],
            }
        else:
            payload = {
                "title": "SQL Window Functions Masterclass",
                "language": "Hinglish",
                "sections": [
                    {
                        "section_type": sec.value,
                        "title": sec.value.replace("_", " ").title(),
                        "narration": (
                            "Namaste dosto, is section mein hum practical SQL window functions "
                            "ko real data analytics examples ke saath samjhenge."
                        ),
                        "visual_instructions": "Diagram + screen recording.",
                        "screen_recording_requirements": (
                            "SQLite console"
                            if sec == ScriptSectionType.PRACTICAL_DEMONSTRATION
                            else None
                        ),
                        "code_demo_references": (
                            ["window_functions.sql"]
                            if sec == ScriptSectionType.PRACTICAL_DEMONSTRATION
                            else []
                        ),
                        "estimated_duration_seconds": 100,
                        "source_urls": [],
                    }
                    for sec in REQUIRED_SECTIONS
                ],
            }
        return LLMResponse(provider="ollama", model=request.model, content=json.dumps(payload))

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(provider="ollama", is_cloud=False, available=True)


@pytest.mark.asyncio
async def test_scripts_and_storyboard_api_end_to_end(
    test_settings: Settings,
    db_session: AsyncSession,
    artifact_store: ArtifactStore,
) -> None:
    router = ModelRouter(
        app_settings=test_settings,
        local_provider=_MockM6LLM(),
        usage_repo=UsageRepository(db_session),
        project_repo=ProjectRepository(db_session),
    )

    app = create_app()

    async def _override_db():
        yield db_session

    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_db_session] = _override_db
    app.dependency_overrides[get_artifact_store] = lambda: artifact_store
    app.dependency_overrides[get_model_router] = lambda: router

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        project = (
            await client.post("/api/projects", json={"topic": "SQL Window Functions Masterclass"})
        ).json()

        # Generate Script v1
        gen_resp = await client.post(
            f"/api/projects/{project['id']}/scripts/generate",
            json={"request_script_approval": True},
        )
        assert gen_resp.status_code == 200
        v1 = gen_resp.json()
        assert v1["version_number"] == 1
        assert v1["validation"]["passed"] is True

        # Save manual edited revision v2
        edited_sections = v1["sections"]
        edited_sections[0]["title"] = "Custom Creator Hook"
        rev_resp = await client.post(
            f"/api/projects/{project['id']}/scripts/revisions",
            json={
                "title": "SQL Window Functions (Creator Cut)",
                "sections": edited_sections,
                "revision_notes": "Tightened intro hook",
            },
        )
        assert rev_resp.status_code == 201
        assert rev_resp.json()["version_number"] == 2

        # Storyboarding blocked with 409 before script approval
        blocked_sb = await client.post(
            f"/api/projects/{project['id']}/storyboard/generate",
            json={"require_approved_script": True},
        )
        assert blocked_sb.status_code == 409

        # Approve v2
        approve_resp = await client.post(
            f"/api/projects/{project['id']}/scripts/versions/2/approve",
            json={"reviewer": "Santosh", "comments": "Ready for storyboard"},
        )
        assert approve_resp.status_code == 200
        assert approve_resp.json()["status"] == "APPROVED"

        # Fetch full script with both preserved versions
        get_script = await client.get(f"/api/projects/{project['id']}/scripts")
        assert get_script.status_code == 200
        assert get_script.json()["approved_version"] == 2
        assert len(get_script.json()["versions"]) == 2

        # Storyboarding succeeds now
        sb_resp = await client.post(
            f"/api/projects/{project['id']}/storyboard/generate",
            json={"require_approved_script": True},
        )
        assert sb_resp.status_code == 200
        assert sb_resp.json()["total_scenes"] == 2

        scenes_resp = await client.get(f"/api/projects/{project['id']}/storyboard/scenes")
        assert scenes_resp.status_code == 200
        assert scenes_resp.json()["total"] == 2
        assert scenes_resp.json()["items"][1]["visual_type"] == "code_demo"
