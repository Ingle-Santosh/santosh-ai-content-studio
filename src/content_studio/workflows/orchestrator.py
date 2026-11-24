import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command
from pydantic import BaseModel, Field

from content_studio.config.settings import Settings
from content_studio.database.models.enums import ApprovalStatus, ProjectStatus, RunStatus
from content_studio.database.models.workflow_run import WorkflowRun
from content_studio.database.repositories import (
    AgentRunRepository,
    ProjectRepository,
    RunRepository,
)
from content_studio.services import ProjectNotFoundError, ResourceNotFoundError
from content_studio.workflows.graphs.content_pipeline import (
    PipelineServices,
    build_content_pipeline_graph,
)


class WorkflowRunNotFoundError(ResourceNotFoundError):
    """Raised when a workflow run ID does not exist."""


class WorkflowStateError(RuntimeError):
    """Raised when an invalid transition is attempted on a workflow run."""


class PendingInterruptInfo(BaseModel):
    gate: str
    approval_id: str | None = None
    artifact_id: str | None = None
    summary: str = ""


class WorkflowRunSnapshot(BaseModel):
    run_id: str
    project_id: str
    thread_id: str
    status: str
    current_stage: str | None = None
    completed_steps: list[str] = Field(default_factory=list)
    pending_interrupt: PendingInterruptInfo | None = None
    artifact_refs: dict[str, str | int | None] = Field(default_factory=dict)
    error_message: str | None = None
    started_at: datetime
    completed_at: datetime | None = None


def _extract_interrupt(snapshot: Any) -> PendingInterruptInfo | None:
    tasks = getattr(snapshot, "tasks", None) or ()
    for task in tasks:
        interrupts = getattr(task, "interrupts", None) or ()
        for intr in interrupts:
            val = getattr(intr, "value", None)
            if isinstance(val, dict) and "gate" in val:
                return PendingInterruptInfo(
                    gate=str(val["gate"]),
                    approval_id=val.get("approval_id"),
                    artifact_id=val.get("artifact_id"),
                    summary=str(val.get("summary") or ""),
                )
    return None


def _artifact_refs_from_values(values: dict[str, Any]) -> dict[str, str | int | None]:
    return {
        "brief_artifact_id": values.get("brief_artifact_id"),
        "research_artifact_id": values.get("research_artifact_id"),
        "competitor_artifact_id": values.get("competitor_artifact_id"),
        "fact_check_artifact_id": values.get("fact_check_artifact_id"),
        "script_version_number": values.get("script_version_number"),
        "script_artifact_id": values.get("script_artifact_id"),
        "storyboard_artifact_id": values.get("storyboard_artifact_id"),
    }


class WorkflowOrchestrator:
    """Manages persistent, resumable LangGraph workflow executions via SQLite checkpoints."""

    def __init__(
        self,
        *,
        app_settings: Settings,
        project_repo: ProjectRepository,
        run_repo: RunRepository,
        services: PipelineServices,
        agent_run_repo: AgentRunRepository | None = None,
        checkpoints_db_path: Path | None = None,
    ) -> None:
        self._settings = app_settings
        self._project_repo = project_repo
        self._run_repo = run_repo
        self._services = services
        self._agent_run_repo = agent_run_repo
        self._checkpoints_path = checkpoints_db_path or app_settings.checkpoints_db_path

    def _checkpoint_conn_str(self) -> str:
        self._checkpoints_path.parent.mkdir(parents=True, exist_ok=True)
        return str(self._checkpoints_path)

    async def _sync_run_after_step(
        self,
        *,
        run: WorkflowRun,
        graph: Any,
        config: dict[str, Any],
    ) -> WorkflowRunSnapshot:
        state_snap = await graph.aget_state(config)
        values = dict(getattr(state_snap, "values", None) or {})
        pending = _extract_interrupt(state_snap)
        completed_steps = list(values.get("completed_steps") or [])
        stage = str(values.get("current_stage") or run.current_stage or "running")
        project = await self._project_repo.get_by_id(run.project_id)

        if pending is not None:
            updated_run = await self._run_repo.update_status(
                run,
                status=RunStatus.INTERRUPTED,
                current_stage=f"awaiting_{pending.gate}_approval",
            )
            if project is not None:
                await self._project_repo.update(
                    project,
                    status=ProjectStatus.AWAITING_REVIEW,
                    current_stage=updated_run.current_stage,
                )
        elif values.get("cancelled"):
            updated_run = await self._run_repo.update_status(
                run,
                status=RunStatus.CANCELLED,
                current_stage=stage,
                mark_completed=True,
            )
            if project is not None:
                await self._project_repo.update(
                    project,
                    status=ProjectStatus.IN_PROGRESS,
                    current_stage=stage,
                )
        else:
            updated_run = await self._run_repo.update_status(
                run,
                status=RunStatus.COMPLETED,
                current_stage=stage,
                mark_completed=True,
            )
            if project is not None:
                await self._project_repo.update(
                    project,
                    status=ProjectStatus.COMPLETED,
                    current_stage=stage,
                )

        return WorkflowRunSnapshot(
            run_id=updated_run.id,
            project_id=updated_run.project_id,
            thread_id=updated_run.thread_id,
            status=updated_run.status,
            current_stage=updated_run.current_stage,
            completed_steps=completed_steps,
            pending_interrupt=pending,
            artifact_refs=_artifact_refs_from_values(values),
            error_message=updated_run.error_message,
            started_at=updated_run.started_at,
            completed_at=updated_run.completed_at,
        )

    async def start_workflow(
        self,
        project_id: str,
        *,
        seed_urls: list[str] | None = None,
        max_results_per_query: int = 5,
        auto_approve: bool | None = None,
    ) -> WorkflowRunSnapshot:
        project = await self._project_repo.get_by_id(project_id)
        if project is None:
            raise ProjectNotFoundError(f"Project '{project_id}' not found.")

        effective_auto = (
            bool(auto_approve)
            if auto_approve is not None
            else bool(project.config.get("auto_approve", False))
        )
        thread_id = f"proj-{project.id[:8]}-{uuid.uuid4().hex[:8]}"
        run = await self._run_repo.create(
            project_id=project.id,
            thread_id=thread_id,
            status=RunStatus.RUNNING,
            current_stage="topic_strategist",
        )
        await self._project_repo.update(
            project,
            status=ProjectStatus.IN_PROGRESS,
            current_stage="topic_strategist",
            error_message=None,
        )

        initial_state = {
            "project_id": project.id,
            "run_id": run.id,
            "thread_id": thread_id,
            "topic": project.topic,
            "auto_approve": effective_auto,
            "seed_urls": list(seed_urls or []),
            "max_results_per_query": max_results_per_query,
            "completed_steps": [],
            "revision_count": 0,
            "cancelled": False,
        }
        config = {"configurable": {"thread_id": thread_id}}

        try:
            async with AsyncSqliteSaver.from_conn_string(self._checkpoint_conn_str()) as saver:
                graph = build_content_pipeline_graph(self._services, checkpointer=saver)
                await graph.ainvoke(initial_state, config=config)
                return await self._sync_run_after_step(run=run, graph=graph, config=config)
        except Exception as exc:  # noqa: BLE001
            await self._run_repo.update_status(
                run,
                status=RunStatus.FAILED,
                error_message=str(exc),
                mark_completed=True,
            )
            await self._project_repo.update(
                project,
                status=ProjectStatus.FAILED,
                error_message=str(exc),
            )
            raise

    async def resume_workflow(
        self,
        run_id: str,
        *,
        decision: ApprovalStatus,
        reviewer: str | None = "Creator",
        comments: str | None = None,
    ) -> WorkflowRunSnapshot:
        if decision == ApprovalStatus.PENDING:
            raise ValueError("Resume decision must be APPROVED, CHANGES_REQUESTED, or REJECTED.")

        run = await self._run_repo.get_by_id(run_id)
        if run is None:
            raise WorkflowRunNotFoundError(f"Workflow run '{run_id}' not found.")
        if run.status != RunStatus.INTERRUPTED.value:
            raise WorkflowStateError(
                f"Workflow run '{run_id}' is in status '{run.status}' and cannot be resumed."
            )

        config = {"configurable": {"thread_id": run.thread_id}}

        try:
            async with AsyncSqliteSaver.from_conn_string(self._checkpoint_conn_str()) as saver:
                graph = build_content_pipeline_graph(self._services, checkpointer=saver)
                pre_state = await graph.aget_state(config)
                pending = _extract_interrupt(pre_state)
                if pending is None:
                    raise WorkflowStateError(
                        f"Workflow run '{run_id}' has no pending interrupt checkpoint."
                    )

                # Record the creator's decision on the corresponding Approval DB row
                if pending.approval_id is not None:
                    await self._services.approval.decide_approval(
                        pending.approval_id,
                        status=decision,
                        reviewer=reviewer,
                        comments=comments,
                    )

                run = await self._run_repo.update_status(run, status=RunStatus.RUNNING)
                await graph.ainvoke(
                    Command(
                        resume={
                            "status": decision.value,
                            "reviewer": reviewer,
                            "comments": comments,
                        }
                    ),
                    config=config,
                )
                return await self._sync_run_after_step(run=run, graph=graph, config=config)
        except (WorkflowStateError, ValueError):
            raise
        except Exception as exc:  # noqa: BLE001
            await self._run_repo.update_status(
                run,
                status=RunStatus.FAILED,
                error_message=str(exc),
                mark_completed=True,
            )
            raise

    async def cancel_workflow(self, run_id: str) -> WorkflowRunSnapshot:
        run = await self._run_repo.get_by_id(run_id)
        if run is None:
            raise WorkflowRunNotFoundError(f"Workflow run '{run_id}' not found.")
        updated = await self._run_repo.update_status(
            run,
            status=RunStatus.CANCELLED,
            mark_completed=True,
        )
        return await self.get_workflow_status(updated.id)

    async def get_workflow_status(self, run_id: str) -> WorkflowRunSnapshot:
        run = await self._run_repo.get_by_id(run_id)
        if run is None:
            raise WorkflowRunNotFoundError(f"Workflow run '{run_id}' not found.")

        config = {"configurable": {"thread_id": run.thread_id}}
        values: dict[str, Any] = {}
        pending: PendingInterruptInfo | None = None

        if self._checkpoints_path.exists():
            async with AsyncSqliteSaver.from_conn_string(self._checkpoint_conn_str()) as saver:
                graph = build_content_pipeline_graph(self._services, checkpointer=saver)
                state_snap = await graph.aget_state(config)
                values = dict(getattr(state_snap, "values", None) or {})
                if run.status == RunStatus.INTERRUPTED.value:
                    pending = _extract_interrupt(state_snap)

        return WorkflowRunSnapshot(
            run_id=run.id,
            project_id=run.project_id,
            thread_id=run.thread_id,
            status=run.status,
            current_stage=run.current_stage,
            completed_steps=list(values.get("completed_steps") or []),
            pending_interrupt=pending,
            artifact_refs=_artifact_refs_from_values(values),
            error_message=run.error_message,
            started_at=run.started_at,
            completed_at=run.completed_at,
        )

    async def list_project_runs(self, project_id: str) -> list[WorkflowRun]:
        project = await self._project_repo.get_by_id(project_id)
        if project is None:
            raise ProjectNotFoundError(f"Project '{project_id}' not found.")
        return list(await self._run_repo.list_for_project(project_id))
