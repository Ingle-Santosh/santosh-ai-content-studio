import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from content_studio.database.models.enums import (
    ArtifactStatus,
    ArtifactType,
    ProjectStatus,
    RunStatus,
)
from content_studio.database.repositories import (
    ArtifactRepository,
    ProjectRepository,
    RunRepository,
    UsageRepository,
)


@pytest.mark.asyncio
async def test_repositories_crud_and_cascade(db_session: AsyncSession) -> None:
    project_repo = ProjectRepository(db_session)
    run_repo = RunRepository(db_session)
    artifact_repo = ArtifactRepository(db_session)
    usage_repo = UsageRepository(db_session)

    project = await project_repo.create(
        title="RAG vs CAG",
        topic="RAG vs CAG vs MAG: Architectural Trade-offs",
        config={"duration_minutes": 15, "language": "Hinglish"},
        budget_usd=2.0,
    )
    assert project.status == ProjectStatus.CREATED.value

    run = await run_repo.create(
        project_id=project.id,
        thread_id=f"thread-{project.id}-1",
        status=RunStatus.RUNNING,
        current_stage="research",
    )
    fetched_run = await run_repo.get_by_thread_id(run.thread_id)
    assert fetched_run is not None
    assert fetched_run.id == run.id

    art_v1 = await artifact_repo.create(
        project_id=project.id,
        run_id=run.id,
        stage="research",
        artifact_type=ArtifactType.RESEARCH_BRIEF,
        name="brief.md",
        relative_path="01_research/brief_v1.md",
        size_bytes=120,
    )
    art_v2 = await artifact_repo.create(
        project_id=project.id,
        run_id=run.id,
        stage="research",
        artifact_type=ArtifactType.RESEARCH_BRIEF,
        name="brief.md",
        relative_path="01_research/brief_v2.md",
        size_bytes=240,
    )
    assert art_v1.version == 1
    assert art_v2.version == 2

    await artifact_repo.update_status(art_v2, ArtifactStatus.APPROVED)
    listed = await artifact_repo.list_for_project(project.id, stage="research")
    assert len(listed) == 2

    await usage_repo.create(
        project_id=project.id,
        run_id=run.id,
        provider="ollama",
        model="qwen2.5-coder:14b",
        node_name="research_node",
        prompt_tokens=500,
        completion_tokens=300,
        estimated_cost_usd=0.0,
        latency_ms=1200,
    )
    await usage_repo.create(
        project_id=project.id,
        run_id=run.id,
        provider="gemini",
        model="gemini-2.5-flash",
        node_name="script_node",
        prompt_tokens=800,
        completion_tokens=600,
        estimated_cost_usd=0.05,
        latency_ms=900,
    )
    assert await usage_repo.total_spend_for_project(project.id) == pytest.approx(0.05)
    assert await usage_repo.total_spend_all() == pytest.approx(0.05)

    # Deleting project should cascade to runs, artifacts, and usage logs
    await project_repo.delete(project)
    assert await project_repo.get_by_id(project.id) is None
    assert await run_repo.list_for_project(project.id) == []
    assert await artifact_repo.list_for_project(project.id) == []
    assert await usage_repo.list_for_project(project.id) == []
