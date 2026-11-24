import time
from pathlib import Path

from content_studio.config.settings import Settings
from content_studio.contracts.production import (
    YouTubeMetadataLLMOutput,
    YouTubeMetadataReport,
)
from content_studio.database.models.enums import AgentRunStatus, ArtifactType
from content_studio.database.models.project import Project
from content_studio.database.repositories import (
    AgentRunRepository,
    CompetitorRepository,
    ProjectRepository,
    SceneRepository,
    ScriptRepository,
)
from content_studio.providers.llm import LLMMessage, ModelRouter, TaskType
from content_studio.services.artifact_service import ArtifactService, ProjectNotFoundError
from content_studio.services.guideline_service import ChannelGuidelineService


def format_timestamp(total_seconds: int) -> str:
    secs = max(0, int(total_seconds))
    hours, rem = divmod(secs, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _load_prompt(base_dir: Path, relative_path: str) -> str:
    return (base_dir / relative_path).read_text(encoding="utf-8").strip()


def _render_youtube_markdown(report: YouTubeMetadataReport) -> str:
    meta = report.metadata
    lines = [
        f"# YouTube Packaging & Metadata: {report.topic}",
        "",
        f"- **Project ID**: `{report.project_id}`",
        f"- **Publishing Mode**: `{report.publishing_mode}` (manual upload only)",
        f"- **Generated At**: {report.generated_at.isoformat()}",
        "",
        "## Recommended Title",
        "",
        f"**{meta.recommended_title}**",
        "",
        "## Alternative Title Options",
        "",
        *[f"- {title}" for title in meta.title_options],
        "",
        "## Video Description (Copy-Paste for YouTube Studio)",
        "",
        meta.description,
        "",
        "## Chapters",
        "",
        *[f"- `{ch.timestamp}` — {ch.title}" for ch in meta.chapters],
        "",
        "## Thumbnail Concepts",
        "",
    ]
    for idx, thumb in enumerate(meta.thumbnail_concepts, start=1):
        lines.extend(
            [
                f"### Concept {idx}: {thumb.concept_name}",
                f"- **Headline Text**: `{thumb.headline_text}`",
                f"- **Visual Composition**: {thumb.visual_composition}",
                f"- **Color Palette**: {thumb.color_palette}",
                "",
            ]
        )

    lines.extend(
        [
            "## Tags",
            "",
            ", ".join(meta.tags),
            "",
        ]
    )
    if meta.hashtags:
        lines.extend(["## Hashtags", "", " ".join(meta.hashtags), ""])
    if meta.pinned_comment:
        lines.extend(["## Pinned Comment Suggestion", "", meta.pinned_comment, ""])
    return "\n".join(lines)


class YouTubeStrategyService:
    """Generates honest YouTube titles, descriptions, chapters, tags, and thumbnail concepts."""

    def __init__(
        self,
        *,
        app_settings: Settings,
        project_repo: ProjectRepository,
        script_repo: ScriptRepository,
        scene_repo: SceneRepository,
        competitor_repo: CompetitorRepository,
        guideline_service: ChannelGuidelineService,
        artifact_service: ArtifactService,
        model_router: ModelRouter,
        agent_run_repo: AgentRunRepository | None = None,
    ) -> None:
        self._settings = app_settings
        self._project_repo = project_repo
        self._script_repo = script_repo
        self._scene_repo = scene_repo
        self._competitor_repo = competitor_repo
        self._guideline_service = guideline_service
        self._artifact_service = artifact_service
        self._model_router = model_router
        self._agent_run_repo = agent_run_repo

    async def _require_project(self, project_id: str) -> Project:
        project = await self._project_repo.get_by_id(project_id)
        if project is None:
            raise ProjectNotFoundError(f"Project '{project_id}' not found.")
        return project

    async def generate_metadata(
        self,
        project_id: str,
        *,
        run_id: str | None = None,
    ) -> YouTubeMetadataReport:
        project = await self._require_project(project_id)
        start_ts = time.perf_counter()

        agent_run = None
        if self._agent_run_repo is not None:
            agent_run = await self._agent_run_repo.create(
                project_id=project_id,
                run_id=run_id,
                agent_name="youtube_strategist",
                stage="export",
                status=AgentRunStatus.RUNNING,
                input_summary_json={"topic": project.topic},
            )

        try:
            guideline_row = await self._guideline_service.get_or_create_active()
            guidelines = await self._guideline_service.get_active_config()
            scenes = list(await self._scene_repo.list_for_project(project_id))
            script = await self._script_repo.get_for_project(project_id)
            competitors = list(await self._competitor_repo.list_for_project(project_id))

            timeline_lines: list[str] = []
            elapsed = 0
            if scenes:
                for scene in scenes:
                    timeline_lines.append(
                        f"- {format_timestamp(elapsed)} — Scene {scene.scene_number}: "
                        f"{scene.title} ({scene.related_script_section})"
                    )
                    elapsed += scene.estimated_duration_seconds
            elif script and script.versions:
                for sec in script.versions[0].sections_json:
                    timeline_lines.append(
                        f"- {format_timestamp(elapsed)} — {sec.get('title', 'Section')}"
                    )
                    elapsed += int(sec.get("estimated_duration_seconds", 60))
            else:
                timeline_lines.append(f"- 00:00 — {project.title}")

            competitor_lines = [
                f"- {v.title} ({v.channel_name or 'Unknown'})" for v in competitors[:5]
            ]

            system_prompt = _load_prompt(
                self._settings.BASE_DIR, "prompts/youtube_strategist/system.md"
            )
            user_template = _load_prompt(
                self._settings.BASE_DIR, "prompts/youtube_strategist/user.md"
            )
            user_prompt = user_template.format(
                topic=project.topic,
                title=project.title,
                channel_name=guideline_row.channel_name,
                creator_bio_note=guidelines.creator_bio_note,
                audience=project.config.get("audience_level", guidelines.audience),
                language=project.config.get("language", guidelines.narration_language),
                timeline_block="\n".join(timeline_lines),
                competitor_block="\n".join(competitor_lines) or "(No competitor notes)",
            )

            llm_result = await self._model_router.generate_structured(
                task=TaskType.METADATA,
                messages=[
                    LLMMessage(role="system", content=system_prompt),
                    LLMMessage(role="user", content=user_prompt),
                ],
                response_model=YouTubeMetadataLLMOutput,
                project_id=project.id,
                run_id=run_id,
                node_name="youtube_strategist",
            )
            meta = llm_result.data

            # Deterministic guardrail: ensure creator experience bio note is present in description
            bio_note = guidelines.creator_bio_note.strip()
            if bio_note and "8+ years" not in meta.description.lower():
                updated_desc = (
                    f"{meta.description.rstrip()}\n\n"
                    f"About {guideline_row.channel_name}: {bio_note}."
                )
                meta = meta.model_copy(update={"description": updated_desc})

            report = YouTubeMetadataReport(
                project_id=project.id,
                topic=project.topic,
                publishing_mode="MANUAL_ONLY",
                metadata=meta,
            )

            json_art = await self._artifact_service.save_json(
                project_id=project.id,
                stage="export",
                artifact_type=ArtifactType.YOUTUBE_METADATA,
                name="youtube_metadata.json",
                relative_path=Path("06_export") / "youtube_metadata.json",
                payload=report,
                run_id=run_id,
                metadata_json={"format": "json", "publishing_mode": "MANUAL_ONLY"},
            )
            md_art = await self._artifact_service.save_text(
                project_id=project.id,
                stage="export",
                artifact_type=ArtifactType.YOUTUBE_METADATA,
                name="youtube_metadata.md",
                relative_path=Path("06_export") / "youtube_metadata.md",
                content=_render_youtube_markdown(report),
                run_id=run_id,
                metadata_json={"format": "markdown", "publishing_mode": "MANUAL_ONLY"},
                supersede_previous_drafts=False,
            )
            report.metadata_json_artifact_id = json_art.id
            report.metadata_markdown_artifact_id = md_art.id

            if agent_run is not None and self._agent_run_repo is not None:
                await self._agent_run_repo.mark_finished(
                    agent_run,
                    status=AgentRunStatus.COMPLETED,
                    output_summary_json={
                        "title_options_count": len(meta.title_options),
                        "chapters_count": len(meta.chapters),
                        "thumbnails_count": len(meta.thumbnail_concepts),
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
