import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from content_studio.contracts.guidelines import ChannelGuidelinesConfig
from content_studio.database.models.enums import (
    AgentRunStatus,
    ApprovalGate,
    ApprovalStatus,
    RunStatus,
)
from content_studio.database.repositories import (
    AgentRunRepository,
    ApprovalRepository,
    ChannelGuidelineRepository,
    ProjectRepository,
    RunRepository,
)


@pytest.mark.asyncio
async def test_approvals_and_agent_runs_cascade_on_project_delete(
    db_session: AsyncSession,
) -> None:
    project_repo = ProjectRepository(db_session)
    run_repo = RunRepository(db_session)
    approval_repo = ApprovalRepository(db_session)
    agent_run_repo = AgentRunRepository(db_session)

    project = await project_repo.create(
        title="Agentic Workflows",
        topic="LangGraph Checkpointing Deep Dive",
    )
    wf_run = await run_repo.create(
        project_id=project.id,
        thread_id=f"thread-{project.id}",
        status=RunStatus.RUNNING,
        current_stage="research",
    )

    approval = await approval_repo.create(
        project_id=project.id,
        run_id=wf_run.id,
        gate=ApprovalGate.RESEARCH,
        comments="Ready for review",
    )
    assert approval.status == ApprovalStatus.PENDING.value

    decided = await approval_repo.decide(
        approval,
        status=ApprovalStatus.APPROVED,
        reviewer="Santosh",
        comments="Looks accurate",
    )
    assert decided.status == ApprovalStatus.APPROVED.value
    assert decided.decided_at is not None

    agent_run = await agent_run_repo.create(
        project_id=project.id,
        run_id=wf_run.id,
        agent_name="research_agent",
        stage="research",
        input_summary_json={"topic": project.topic},
    )
    finished = await agent_run_repo.mark_finished(
        agent_run,
        status=AgentRunStatus.COMPLETED,
        output_summary_json={"sources": 5},
        duration_ms=840,
    )
    assert finished.status == AgentRunStatus.COMPLETED.value
    assert finished.duration_ms == 840
    assert finished.completed_at is not None

    await project_repo.delete(project)
    assert await approval_repo.list_approvals(project_id=project.id) == []
    assert await agent_run_repo.list_for_project(project.id) == []


@pytest.mark.asyncio
async def test_channel_guideline_upsert_switches_active_profile(
    db_session: AsyncSession,
) -> None:
    repo = ChannelGuidelineRepository(db_session)

    first = await repo.upsert_by_slug(
        slug="santosh-analytics",
        channel_name="Santosh Analytics",
        guidelines_json=ChannelGuidelinesConfig().model_dump(),
        is_active=True,
    )
    assert first.is_active is True

    second = await repo.upsert_by_slug(
        slug="english-deep-dive",
        channel_name="Santosh Analytics English",
        guidelines_json=ChannelGuidelinesConfig(narration_language="English").model_dump(),
        is_active=True,
    )
    assert second.is_active is True

    active = await repo.get_active()
    assert active is not None
    assert active.slug == "english-deep-dive"

    refreshed_first = await repo.get_by_slug("santosh-analytics")
    assert refreshed_first is not None
    assert refreshed_first.is_active is False
