import time
from pathlib import Path

from content_studio.config.settings import Settings
from content_studio.contracts.brief import ContentBriefLLMOutput, ContentBriefReport
from content_studio.database.models.enums import AgentRunStatus, ApprovalGate, ArtifactType
from content_studio.database.models.project import Project
from content_studio.database.repositories import AgentRunRepository, ProjectRepository
from content_studio.providers.llm import LLMMessage, ModelRouter, TaskType
from content_studio.services.approval_service import ApprovalService
from content_studio.services.artifact_service import ArtifactService, ProjectNotFoundError
from content_studio.services.guideline_service import ChannelGuidelineService


def _load_prompt(base_dir: Path, relative_path: str) -> str:
    return (base_dir / relative_path).read_text(encoding="utf-8").strip()


def _render_brief_markdown(report: ContentBriefReport) -> str:
    b = report.brief
    lines = [
        f"# Content Brief: {report.topic}",
        "",
        f"- **Project ID**: `{report.project_id}`",
        f"- **Generated At**: {report.generated_at.isoformat()}",
        f"- **Target Audience**: {b.target_audience}",
        "",
        "## Content Angle",
        "",
        b.content_angle,
        "",
        "## Problem Hook",
        "",
        b.problem_hook,
        "",
        "## Differentiation Hook",
        "",
        b.differentiation_hook,
        "",
        "## Key Takeaways",
        "",
        *[f"- {item}" for item in b.key_takeaways],
        "",
        "## Proposed Outline",
        "",
        *[f"{idx}. {item}" for idx, item in enumerate(b.proposed_outline, start=1)],
        "",
        "## Planned Search Queries",
        "",
        *[f"- `{q}`" for q in b.search_queries],
        "",
        "## Planned Competitor Queries",
        "",
        *[f"- `{q}`" for q in b.competitor_queries],
        "",
    ]
    return "\n".join(lines)


class TopicStrategistService:
    """Produces a structured ContentBrief to kick off the content workflow (Gate 1)."""

    def __init__(
        self,
        *,
        app_settings: Settings,
        project_repo: ProjectRepository,
        guideline_service: ChannelGuidelineService,
        artifact_service: ArtifactService,
        model_router: ModelRouter,
        approval_service: ApprovalService | None = None,
        agent_run_repo: AgentRunRepository | None = None,
    ) -> None:
        self._settings = app_settings
        self._project_repo = project_repo
        self._guideline_service = guideline_service
        self._artifact_service = artifact_service
        self._model_router = model_router
        self._approval_service = approval_service
        self._agent_run_repo = agent_run_repo

    async def _require_project(self, project_id: str) -> Project:
        project = await self._project_repo.get_by_id(project_id)
        if project is None:
            raise ProjectNotFoundError(f"Project '{project_id}' not found.")
        return project

    async def generate_brief(
        self,
        project_id: str,
        *,
        revision_notes: str | None = None,
        request_brief_approval: bool = False,
        run_id: str | None = None,
    ) -> ContentBriefReport:
        project = await self._require_project(project_id)
        start_ts = time.perf_counter()

        agent_run = None
        if self._agent_run_repo is not None:
            agent_run = await self._agent_run_repo.create(
                project_id=project_id,
                run_id=run_id,
                agent_name="topic_strategist",
                stage="outline",
                status=AgentRunStatus.RUNNING,
                input_summary_json={"has_revision_notes": bool(revision_notes)},
            )

        try:
            guidelines = await self._guideline_service.get_active_config()
            guidelines_block = (
                f"- Audience: {guidelines.audience}\n"
                f"- Narration: {guidelines.narration_language} "
                f"(tech terms: {guidelines.technical_terminology})\n"
                f"- Style: {guidelines.explanation_style}\n"
                f"- Approach: {guidelines.tutorial_approach}"
            )
            system_prompt = _load_prompt(
                self._settings.BASE_DIR, "prompts/topic_strategist/system.md"
            )
            user_template = _load_prompt(
                self._settings.BASE_DIR, "prompts/topic_strategist/user.md"
            )
            user_prompt = user_template.format(
                topic=project.topic,
                title=project.title,
                duration_minutes=int(project.config.get("duration_minutes", 15)),
                audience_level=project.config.get("audience_level", guidelines.audience),
                language=project.config.get("language", guidelines.narration_language),
                guidelines_block=guidelines_block,
                revision_notes=revision_notes or "None (initial brief).",
            )

            llm_result = await self._model_router.generate_structured(
                task=TaskType.TOPIC_STRATEGY,
                messages=[
                    LLMMessage(role="system", content=system_prompt),
                    LLMMessage(role="user", content=user_prompt),
                ],
                response_model=ContentBriefLLMOutput,
                project_id=project.id,
                run_id=run_id,
                node_name="topic_strategist",
            )

            report = ContentBriefReport(
                project_id=project.id,
                topic=project.topic,
                brief=llm_result.data,
            )

            json_art = await self._artifact_service.save_json(
                project_id=project.id,
                stage="outline",
                artifact_type=ArtifactType.CONTENT_BRIEF,
                name="content_brief.json",
                payload=report,
                run_id=run_id,
                metadata_json={"format": "json"},
            )
            md_art = await self._artifact_service.save_text(
                project_id=project.id,
                stage="outline",
                artifact_type=ArtifactType.CONTENT_BRIEF,
                name="content_brief.md",
                content=_render_brief_markdown(report),
                run_id=run_id,
                metadata_json={"format": "markdown"},
                supersede_previous_drafts=False,
            )
            report.brief_json_artifact_id = json_art.id
            report.brief_markdown_artifact_id = md_art.id

            if request_brief_approval and self._approval_service is not None:
                approval = await self._approval_service.request_approval(
                    project_id=project.id,
                    gate=ApprovalGate.BRIEF,
                    run_id=run_id,
                    artifact_id=md_art.id,
                    comments="Content brief ready for Gate 1 review.",
                )
                report.approval_id = approval.id

            if agent_run is not None and self._agent_run_repo is not None:
                await self._agent_run_repo.mark_finished(
                    agent_run,
                    status=AgentRunStatus.COMPLETED,
                    output_summary_json={
                        "search_queries": report.brief.search_queries,
                        "competitor_queries": report.brief.competitor_queries,
                    },
                    duration_ms=int((time.perf_counter() - start_ts) * 1000),
                )
            return report
        except Exception as exc:  # noqa: BLE001
            if agent_run is not None and self._agent_run_repo is not None:
                await self._agent_run_repo.mark_finished(
                    agent_run,
                    status=AgentRunStatus.FAILED,
                    error_message=str(exc),
                    duration_ms=int((time.perf_counter() - start_ts) * 1000),
                )
            raise
