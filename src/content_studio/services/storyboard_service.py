import time
from pathlib import Path

from content_studio.config.settings import Settings
from content_studio.contracts.storyboard import (
    GeneratedStoryboardReport,
    StoryboardLLMOutput,
    StoryboardSceneItem,
)
from content_studio.database.models.enums import AgentRunStatus, ArtifactStatus, ArtifactType
from content_studio.database.models.project import Project
from content_studio.database.models.scene import Scene
from content_studio.database.models.script import ScriptVersion
from content_studio.database.repositories import (
    AgentRunRepository,
    ProjectRepository,
    SceneRepository,
    ScriptRepository,
)
from content_studio.providers.llm import LLMMessage, ModelRouter, TaskType
from content_studio.services.artifact_service import ArtifactService, ProjectNotFoundError
from content_studio.services.guideline_service import ChannelGuidelineService
from content_studio.services.script_service import ScriptNotFoundError, WorkflowGateError


class ScriptNotApprovedError(WorkflowGateError):
    """Raised when storyboarding is attempted before a script version is approved."""


def _load_prompt(base_dir: Path, relative_path: str) -> str:
    return (base_dir / relative_path).read_text(encoding="utf-8").strip()


def _render_storyboard_markdown(report: GeneratedStoryboardReport) -> str:
    mins = report.total_estimated_duration_seconds // 60
    secs = report.total_estimated_duration_seconds % 60
    lines: list[str] = [
        f"# Storyboard (Script v{report.script_version_number})",
        "",
        f"- **Project ID**: `{report.project_id}`",
        f"- **Total Scenes**: {report.total_scenes}",
        f"- **Estimated Duration**: {mins}m {secs}s",
        f"- **Asset Requirements**: {report.total_asset_requirements}",
        "",
        "## Overview",
        "",
        report.summary,
        "",
        "## Scene Breakdown",
        "",
    ]

    for scene in report.scenes:
        lines.extend(
            [
                f"### Scene {scene.scene_number}: {scene.title} "
                f"(`{scene.visual_type.value}`, ~{scene.estimated_duration_seconds}s)",
                "",
                f"**Script Section**: `{scene.related_script_section}`",
                "",
                f"> {scene.narration}",
                "",
            ]
        )
        if scene.on_screen_text:
            lines.append(f"**On-Screen Text**: {scene.on_screen_text}")
        if scene.camera_or_screen_instructions:
            lines.append(f"**Camera / Screen**: {scene.camera_or_screen_instructions}")
        if scene.transition_instructions:
            lines.append(f"**Transition**: {scene.transition_instructions}")
        if scene.asset_requirements:
            lines.append("**Assets Needed**:")
            for asset in scene.asset_requirements:
                lines.append(f"- `[{asset.asset_type}]` **{asset.title}**: {asset.description}")
        lines.append("")

    return "\n".join(lines)


class StoryboardService:
    """Converts an approved script into scene-by-scene visual instructions & asset specs."""

    def __init__(
        self,
        *,
        app_settings: Settings,
        project_repo: ProjectRepository,
        script_repo: ScriptRepository,
        scene_repo: SceneRepository,
        guideline_service: ChannelGuidelineService,
        artifact_service: ArtifactService,
        model_router: ModelRouter,
        agent_run_repo: AgentRunRepository | None = None,
    ) -> None:
        self._settings = app_settings
        self._project_repo = project_repo
        self._script_repo = script_repo
        self._scene_repo = scene_repo
        self._guideline_service = guideline_service
        self._artifact_service = artifact_service
        self._model_router = model_router
        self._agent_run_repo = agent_run_repo

    async def _require_project(self, project_id: str) -> Project:
        project = await self._project_repo.get_by_id(project_id)
        if project is None:
            raise ProjectNotFoundError(f"Project '{project_id}' not found.")
        return project

    async def _resolve_target_script_version(
        self,
        project_id: str,
        *,
        script_version_number: int | None,
        require_approved_script: bool,
    ) -> tuple[str, ScriptVersion]:
        script = await self._script_repo.get_for_project(project_id)
        if script is None or not script.versions:
            raise ScriptNotFoundError(
                f"No script versions exist for project '{project_id}'. Generate a script first."
            )

        if script_version_number is not None:
            version = await self._script_repo.get_version(project_id, script_version_number)
            if version is None:
                raise ScriptNotFoundError(
                    f"Script version v{script_version_number} not found for project '{project_id}'."
                )
            if require_approved_script and version.status != ArtifactStatus.APPROVED.value:
                raise ScriptNotApprovedError(
                    f"Script v{version.version_number} must be APPROVED before storyboarding."
                )
            return script.title, version

        if require_approved_script:
            approved = await self._script_repo.get_latest_approved_version(project_id)
            if approved is None:
                raise ScriptNotApprovedError(
                    "An approved script version (Gate 3) is required before generating a "
                    "storyboard."
                )
            return script.title, approved

        return script.title, script.versions[0]

    async def generate_storyboard(
        self,
        project_id: str,
        *,
        script_version_number: int | None = None,
        require_approved_script: bool = True,
        run_id: str | None = None,
    ) -> GeneratedStoryboardReport:
        project = await self._require_project(project_id)
        script_title, version = await self._resolve_target_script_version(
            project_id,
            script_version_number=script_version_number,
            require_approved_script=require_approved_script,
        )

        start_ts = time.perf_counter()
        agent_run = None
        if self._agent_run_repo is not None:
            agent_run = await self._agent_run_repo.create(
                project_id=project_id,
                run_id=run_id,
                agent_name="storyboard_agent",
                stage="outline",
                status=AgentRunStatus.RUNNING,
                input_summary_json={"script_version_number": version.version_number},
            )

        try:
            guidelines = await self._guideline_service.get_active_config()

            section_blocks: list[str] = []
            for idx, sec in enumerate(version.sections_json, start=1):
                section_blocks.append(
                    f"{idx}. [{sec.get('section_type', 'section')}] {sec.get('title', '')} "
                    f"(~{sec.get('estimated_duration_seconds', 60)}s)\n"
                    f"Narration: {sec.get('narration', '')}\n"
                    f"Visual hints: {sec.get('visual_instructions', '')}\n"
                    f"Code/Screen hints: {sec.get('screen_recording_requirements') or ''} "
                    f"{', '.join(sec.get('code_demo_references', []))}"
                )

            system_prompt = _load_prompt(self._settings.BASE_DIR, "prompts/storyboard/system.md")
            user_template = _load_prompt(self._settings.BASE_DIR, "prompts/storyboard/user.md")
            user_prompt = user_template.format(
                topic=project.topic,
                title=script_title,
                language=version.language,
                visual_standards=guidelines.visual_standards,
                presentation_style=guidelines.presentation_style,
                sections_block="\n\n".join(section_blocks),
            )

            llm_result = await self._model_router.generate_structured(
                task=TaskType.STORYBOARD,
                messages=[
                    LLMMessage(role="system", content=system_prompt),
                    LLMMessage(role="user", content=user_prompt),
                ],
                response_model=StoryboardLLMOutput,
                project_id=project.id,
                run_id=run_id,
                node_name="storyboard_agent",
            )
            generated = llm_result.data

            # Normalize sequential scene numbers 1..N
            normalized_scenes: list[StoryboardSceneItem] = [
                scene.model_copy(update={"scene_number": idx})
                for idx, scene in enumerate(generated.scenes, start=1)
            ]

            await self._scene_repo.replace_for_project(
                project.id,
                script_version_id=version.id,
                run_id=run_id,
                scenes_data=[scene.model_dump() for scene in normalized_scenes],
            )

            total_duration = sum(s.estimated_duration_seconds for s in normalized_scenes)
            total_assets = sum(len(s.asset_requirements) for s in normalized_scenes)

            report = GeneratedStoryboardReport(
                project_id=project.id,
                script_version_id=version.id,
                script_version_number=version.version_number,
                summary=generated.summary,
                total_scenes=len(normalized_scenes),
                total_estimated_duration_seconds=total_duration,
                total_asset_requirements=total_assets,
                scenes=normalized_scenes,
            )

            json_art = await self._artifact_service.save_json(
                project_id=project.id,
                stage="outline",
                artifact_type=ArtifactType.STORYBOARD,
                name="storyboard.json",
                payload=report,
                run_id=run_id,
                metadata_json={
                    "script_version_number": version.version_number,
                    "total_scenes": report.total_scenes,
                },
            )
            md_art = await self._artifact_service.save_text(
                project_id=project.id,
                stage="outline",
                artifact_type=ArtifactType.STORYBOARD,
                name="storyboard.md",
                content=_render_storyboard_markdown(report),
                run_id=run_id,
                metadata_json={"format": "markdown", "total_scenes": report.total_scenes},
                supersede_previous_drafts=False,
            )
            report.storyboard_json_artifact_id = json_art.id
            report.storyboard_markdown_artifact_id = md_art.id

            if agent_run is not None and self._agent_run_repo is not None:
                await self._agent_run_repo.mark_finished(
                    agent_run,
                    status=AgentRunStatus.COMPLETED,
                    output_summary_json={
                        "total_scenes": report.total_scenes,
                        "total_asset_requirements": report.total_asset_requirements,
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

    async def list_scenes(self, project_id: str) -> list[Scene]:
        await self._require_project(project_id)
        return list(await self._scene_repo.list_for_project(project_id))
