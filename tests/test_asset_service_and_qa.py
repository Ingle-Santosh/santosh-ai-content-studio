import json

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from content_studio.config.settings import Settings
from content_studio.database.models.enums import ApprovalGate, ApprovalStatus
from content_studio.database.repositories import (
    AgentRunRepository,
    ApprovalRepository,
    ArtifactRepository,
    ProjectRepository,
    SceneRepository,
    UsageRepository,
)
from content_studio.providers.image import LocalSVGImageProvider
from content_studio.providers.llm import (
    BaseLLMProvider,
    LLMRequest,
    LLMResponse,
    ModelRouter,
    ProviderHealth,
)
from content_studio.services import (
    ApprovalService,
    ArtifactService,
    AssetGenerationService,
    AssetQAService,
)
from content_studio.storage.artifact_store import ArtifactStore


class _AssetStubLLM(BaseLLMProvider):
    provider_name = "ollama"
    is_cloud = False

    def __init__(self, *, fail_first_code_demo: bool = True) -> None:
        self._fail_first_code = fail_first_code_demo
        self.code_attempts = 0

    async def generate(self, request: LLMRequest) -> LLMResponse:
        prompt = request.messages[-1].content
        if "Mermaid diagram" in prompt:
            payload = {
                "title": "RAG Pipeline Flow",
                "diagram_type": "flowchart",
                "mermaid_code": (
                    'flowchart TD\n    A["User Prompt"] --> B["Retriever"]\n'
                    '    B --> C["Context + LLM"]\n'
                ),
                "caption": "Core RAG query execution flow.",
            }
        elif "interactive animation specification" in prompt:
            payload = {
                "title": "How Embeddings Work",
                "subtitle": "3-step visual intuition",
                "steps": [
                    {
                        "label": "Tokenize",
                        "description": "Split input text into tokens.",
                        "highlight_text": "['RAG', 'vs', 'CAG']",
                    },
                    {
                        "label": "Embed",
                        "description": "Project tokens into dense vector space.",
                        "highlight_text": "[0.12, -0.44, 0.89]",
                    },
                ],
            }
        else:
            self.code_attempts += 1
            if self._fail_first_code and self.code_attempts == 1:
                # First attempt intentionally fails sandbox safety check
                code = "import subprocess\nsubprocess.run(['echo', 'bad'])\n"
            else:
                code = "scores = [0.91, 0.84, 0.77]\nprint('Top similarity:', max(scores))\n"
            payload = {
                "title": "Cosine Similarity Demo",
                "language": "python",
                "filename": "cosine_demo.py",
                "code": code,
                "explanation": "Minimal similarity ranking demo.",
            }
        return LLMResponse(provider="ollama", model=request.model, content=json.dumps(payload))

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(provider="ollama", is_cloud=False, available=True)


@pytest.mark.asyncio
async def test_asset_planning_independent_retry_and_qa_gate(
    test_settings: Settings,
    db_session: AsyncSession,
    artifact_store: ArtifactStore,
) -> None:
    project_repo = ProjectRepository(db_session)
    scene_repo = SceneRepository(db_session)
    artifact_repo = ArtifactRepository(db_session)
    approval_repo = ApprovalRepository(db_session)
    usage_repo = UsageRepository(db_session)
    agent_run_repo = AgentRunRepository(db_session)

    artifact_service = ArtifactService(
        project_repo=project_repo,
        artifact_repo=artifact_repo,
        store=artifact_store,
    )
    approval_service = ApprovalService(
        project_repo=project_repo,
        approval_repo=approval_repo,
        artifact_repo=artifact_repo,
    )

    project = await project_repo.create(title="RAG Visuals", topic="RAG Architecture Explained")
    await artifact_store.ainit_project_dirs(project.id)

    await scene_repo.replace_for_project(
        project.id,
        script_version_id=None,
        run_id=None,
        scenes_data=[
            {
                "scene_number": 1,
                "title": "Architecture Overview",
                "estimated_duration_seconds": 60,
                "narration": "Let's inspect the RAG flowchart and concept visual.",
                "visual_type": "diagram",
                "asset_requirements": [
                    {
                        "asset_type": "diagram",
                        "title": "RAG Pipeline Flow",
                        "description": "Query to vector store to LLM.",
                    },
                    {
                        "asset_type": "image",
                        "title": "RAG Concept Slide",
                        "description": "Clean branded cover concept visual.",
                    },
                ],
                "related_script_section": "main_explanation",
            },
            {
                "scene_number": 2,
                "title": "Interactive Walkthrough & Python Demo",
                "estimated_duration_seconds": 90,
                "narration": "Walk through embeddings and run Python similarity code.",
                "visual_type": "code_demo",
                "asset_requirements": [
                    {
                        "asset_type": "animation",
                        "title": "Embeddings Walkthrough",
                        "description": "Step-by-step animation.",
                    },
                    {
                        "asset_type": "code_demo",
                        "title": "Cosine Similarity Demo",
                        "description": "Python snippet printing top similarity.",
                    },
                ],
                "related_script_section": "practical_demonstration",
            },
        ],
    )

    llm = _AssetStubLLM(fail_first_code_demo=True)
    router = ModelRouter(
        app_settings=test_settings,
        local_provider=llm,
        usage_repo=usage_repo,
        project_repo=project_repo,
    )
    asset_service = AssetGenerationService(
        app_settings=test_settings,
        project_repo=project_repo,
        scene_repo=scene_repo,
        artifact_service=artifact_service,
        model_router=router,
        image_provider=LocalSVGImageProvider(),
        agent_run_repo=agent_run_repo,
    )
    qa_service = AssetQAService(
        artifact_service=artifact_service,
        approval_service=approval_service,
    )

    # 1. Plan assets -> 4 items mapped to scenes
    plan = await asset_service.plan_assets(project.id)
    assert len(plan.items) == 4
    code_item = next(i for i in plan.items if i.category.value == "code_demo")

    # 2. Generate all -> 3 succeed, 1 code_demo fails isolated safety check
    batch1 = await asset_service.generate_assets(project.id)
    assert batch1.succeeded_count == 3
    assert batch1.failed_count == 1

    # 3. Asset QA fails because code_demo failed validation -> Gate 4 approval NOT created
    qa_fail = await qa_service.run_qa(project.id, request_assets_approval=True)
    assert qa_fail.passed is False
    assert qa_fail.failed_count == 1
    assert qa_fail.approval_id is None

    # 4. Retry ONLY the failed code_demo independently -> succeeds & supersedes failed attempt
    retry_batch = await asset_service.generate_assets(
        project.id,
        asset_keys=[code_item.asset_key],
    )
    assert retry_batch.total_planned == 1
    assert retry_batch.succeeded_count == 1
    assert retry_batch.failed_count == 0

    # 5. Asset QA now passes cleanly and creates Gate 4 (storyboard_assets) approval!
    qa_pass = await qa_service.run_qa(project.id, request_assets_approval=True)
    assert qa_pass.passed is True
    assert qa_pass.failed_count == 0
    assert qa_pass.approval_id is not None

    approvals = await approval_repo.list_approvals(
        project_id=project.id, gate=ApprovalGate.STORYBOARD_ASSETS
    )
    assert len(approvals) == 1
    assert approvals[0].status == ApprovalStatus.PENDING.value
