import io
import json
import re
import time
import zipfile
from pathlib import Path

from content_studio.config.settings import Settings
from content_studio.contracts.production import (
    AssetManifestEntry,
    ProductionEditingNotesLLMOutput,
    ProductionPackageReport,
    SceneSequenceEntry,
    YouTubeMetadataLLMOutput,
)
from content_studio.database.models.artifact import Artifact
from content_studio.database.models.enums import (
    AgentRunStatus,
    ApprovalGate,
    ArtifactStatus,
    ArtifactType,
)
from content_studio.database.models.project import Project
from content_studio.database.repositories import (
    AgentRunRepository,
    ProjectRepository,
    SceneRepository,
    ScriptRepository,
)
from content_studio.providers.llm import LLMMessage, ModelRouter, TaskType
from content_studio.services.approval_service import ApprovalService
from content_studio.services.artifact_service import ArtifactService, ProjectNotFoundError
from content_studio.services.youtube_strategy_service import (
    YouTubeStrategyService,
    format_timestamp,
)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: str) -> str:
    return _SLUG_RE.sub("_", text.strip().lower()).strip("_")[:48] or "project"


def _load_prompt(base_dir: Path, relative_path: str) -> str:
    return (base_dir / relative_path).read_text(encoding="utf-8").strip()


def _render_production_notes_markdown(report: ProductionPackageReport) -> str:
    duration_str = format_timestamp(report.total_estimated_duration_seconds)
    lines = [
        f"# Production Package & Editing Guide: {report.topic}",
        "",
        f"- **Project ID**: `{report.project_id}`",
        f"- **Publishing Mode**: `{report.publishing_mode}` — {report.manual_publishing_notice}",
        f"- **Total Estimated Duration**: `{duration_str}`",
        f"- **Total Assets in Manifest**: {len(report.asset_manifest)}",
        "",
        "## Editing Summary",
        "",
        report.editing_notes.editing_summary,
        "",
    ]
    if report.editing_notes.pacing_and_audio_notes:
        lines.extend(
            [
                "## Pacing & Audio Notes",
                "",
                *[f"- {n}" for n in report.editing_notes.pacing_and_audio_notes],
                "",
            ]
        )
    if report.editing_notes.b_roll_and_overlay_cues:
        lines.extend(
            [
                "## B-Roll & Overlay Cues",
                "",
                *[f"- {c}" for c in report.editing_notes.b_roll_and_overlay_cues],
                "",
            ]
        )
    if report.editing_notes.recording_checklist:
        lines.extend(
            [
                "## Pre-Recording Checklist",
                "",
                *[f"- [ ] {item}" for item in report.editing_notes.recording_checklist],
                "",
            ]
        )
    if report.editing_notes.post_production_checklist:
        lines.extend(
            [
                "## Post-Production & Manual Publishing Checklist",
                "",
                *[f"- [ ] {item}" for item in report.editing_notes.post_production_checklist],
                (
                    "- [ ] Upload video, thumbnail, title, description, and chapters "
                    "manually in YouTube Studio."
                ),
                "",
            ]
        )

    lines.extend(["## Scene Sequence Timeline", ""])
    for entry in report.scene_sequence:
        lines.append(
            f"### {entry.start_timestamp}–{entry.end_timestamp} | Scene {entry.scene_number}: "
            f"{entry.title} (`{entry.visual_type}`)"
        )
        if entry.camera_or_screen_instructions:
            lines.append(f"- **Camera / Screen**: {entry.camera_or_screen_instructions}")
        if entry.transition_instructions:
            lines.append(f"- **Transition**: {entry.transition_instructions}")
        if entry.linked_asset_paths:
            lines.append("- **Assets**: " + ", ".join(f"`{p}`" for p in entry.linked_asset_paths))
        lines.append("")

    return "\n".join(lines)


def _zip_folder_for_artifact(art: Artifact) -> str:
    t = art.artifact_type
    if t == ArtifactType.SCRIPT.value:
        return "script"
    if t == ArtifactType.STORYBOARD.value:
        return "storyboard"
    if t in {
        ArtifactType.RESEARCH_BRIEF.value,
        ArtifactType.FACT_CHECK_REPORT.value,
        ArtifactType.COMPETITOR_REPORT.value,
        ArtifactType.CONTENT_BRIEF.value,
    }:
        return "research"
    if t == ArtifactType.YOUTUBE_METADATA.value:
        return "youtube"
    if t in {
        ArtifactType.DIAGRAM_MMD.value,
        ArtifactType.DIAGRAM_SVG.value,
        ArtifactType.DIAGRAM_PNG.value,
        ArtifactType.HTML_ANIMATION.value,
        ArtifactType.IMAGE.value,
        ArtifactType.SCREENSHOT.value,
        ArtifactType.CODE_DEMO.value,
        ArtifactType.QA_REVIEW.value,
    }:
        return "assets"
    return "production"


class ProductionService:
    """Assembles editing notes, scene sequence, asset manifest, YouTube metadata, and ZIP export."""

    def __init__(
        self,
        *,
        app_settings: Settings,
        project_repo: ProjectRepository,
        script_repo: ScriptRepository,
        scene_repo: SceneRepository,
        artifact_service: ArtifactService,
        youtube_strategy_service: YouTubeStrategyService,
        model_router: ModelRouter,
        approval_service: ApprovalService | None = None,
        agent_run_repo: AgentRunRepository | None = None,
    ) -> None:
        self._settings = app_settings
        self._project_repo = project_repo
        self._script_repo = script_repo
        self._scene_repo = scene_repo
        self._artifact_service = artifact_service
        self._youtube_strategy = youtube_strategy_service
        self._model_router = model_router
        self._approval_service = approval_service
        self._agent_run_repo = agent_run_repo

    async def _require_project(self, project_id: str) -> Project:
        project = await self._project_repo.get_by_id(project_id)
        if project is None:
            raise ProjectNotFoundError(f"Project '{project_id}' not found.")
        return project

    async def build_production_package(
        self,
        project_id: str,
        *,
        include_youtube_metadata: bool = True,
        request_final_approval: bool = True,
        run_id: str | None = None,
    ) -> ProductionPackageReport:
        project = await self._require_project(project_id)
        start_ts = time.perf_counter()

        agent_run = None
        if self._agent_run_repo is not None:
            agent_run = await self._agent_run_repo.create(
                project_id=project_id,
                run_id=run_id,
                agent_name="production_agent",
                stage="export",
                status=AgentRunStatus.RUNNING,
                input_summary_json={"include_youtube_metadata": include_youtube_metadata},
            )

        try:
            # 1. Generate YouTube packaging metadata if requested
            yt_meta: YouTubeMetadataLLMOutput | None = None
            if include_youtube_metadata:
                yt_report = await self._youtube_strategy.generate_metadata(
                    project.id, run_id=run_id
                )
                yt_meta = yt_report.metadata

            # 2. Collect active project artifacts & build manifest
            all_artifacts = await self._artifact_service.list_artifacts(project.id)
            active_artifacts = [
                art
                for art in all_artifacts
                if art.status not in {ArtifactStatus.SUPERSEDED.value, ArtifactStatus.FAILED.value}
                and art.artifact_type != ArtifactType.EXPORT_BUNDLE.value
            ]

            assets_by_scene: dict[int, list[str]] = {}
            manifest_entries: list[AssetManifestEntry] = []
            for art in active_artifacts:
                scene_num = (art.metadata_json or {}).get("scene_number")
                if isinstance(scene_num, int):
                    assets_by_scene.setdefault(scene_num, []).append(art.relative_path)
                manifest_entries.append(
                    AssetManifestEntry(
                        artifact_id=art.id,
                        stage=art.stage,
                        artifact_type=art.artifact_type,
                        name=art.name,
                        relative_path=art.relative_path,
                        version=art.version,
                        status=art.status,
                        size_bytes=art.size_bytes,
                        checksum_sha256=art.checksum_sha256,
                        scene_number=scene_num if isinstance(scene_num, int) else None,
                    )
                )

            # 3. Build timed scene sequence
            scenes = list(await self._scene_repo.list_for_project(project.id))
            sequence: list[SceneSequenceEntry] = []
            elapsed = 0
            for scene in scenes:
                start_ts_str = format_timestamp(elapsed)
                end_ts_str = format_timestamp(elapsed + scene.estimated_duration_seconds)
                sequence.append(
                    SceneSequenceEntry(
                        scene_number=scene.scene_number,
                        title=scene.title,
                        start_timestamp=start_ts_str,
                        end_timestamp=end_ts_str,
                        duration_seconds=scene.estimated_duration_seconds,
                        visual_type=scene.visual_type,
                        related_script_section=scene.related_script_section,
                        on_screen_text=scene.on_screen_text,
                        camera_or_screen_instructions=scene.camera_or_screen_instructions,
                        transition_instructions=scene.transition_instructions,
                        linked_asset_paths=assets_by_scene.get(scene.scene_number, []),
                    )
                )
                elapsed += scene.estimated_duration_seconds

            # 4. Generate editing notes via ModelRouter
            scene_block = (
                "\n".join(
                    f"- {s.start_timestamp}–{s.end_timestamp} Scene {s.scene_number}: "
                    f"{s.title} ({s.visual_type}, assets={s.linked_asset_paths})"
                    for s in sequence
                )
                or "(No storyboard scenes yet)"
            )
            assets_block = (
                "\n".join(
                    f"- [{m.artifact_type}] {m.relative_path} (scene={m.scene_number})"
                    for m in manifest_entries
                )
                or "(No visual/code assets yet)"
            )
            system_prompt = _load_prompt(self._settings.BASE_DIR, "prompts/production/system.md")
            user_template = _load_prompt(self._settings.BASE_DIR, "prompts/production/user.md")
            user_prompt = user_template.format(
                topic=project.topic,
                title=project.title,
                duration_display=format_timestamp(elapsed),
                scene_block=scene_block,
                assets_block=assets_block,
            )

            editing_res = await self._model_router.generate_structured(
                task=TaskType.METADATA,
                messages=[
                    LLMMessage(role="system", content=system_prompt),
                    LLMMessage(role="user", content=user_prompt),
                ],
                response_model=ProductionEditingNotesLLMOutput,
                project_id=project.id,
                run_id=run_id,
                node_name="production_agent",
            )

            report = ProductionPackageReport(
                project_id=project.id,
                topic=project.topic,
                publishing_mode="MANUAL_ONLY",
                total_estimated_duration_seconds=elapsed,
                scene_sequence=sequence,
                asset_manifest=manifest_entries,
                editing_notes=editing_res.data,
                youtube_metadata=yt_meta,
            )

            # 5. Persist production notes & asset manifest artifacts
            notes_md = _render_production_notes_markdown(report)
            notes_art = await self._artifact_service.save_text(
                project_id=project.id,
                stage="export",
                artifact_type=ArtifactType.OTHER,
                name="production_notes.md",
                relative_path=Path("06_export") / "production_notes.md",
                content=notes_md,
                run_id=run_id,
                metadata_json={"kind": "production_notes", "publishing_mode": "MANUAL_ONLY"},
            )
            manifest_art = await self._artifact_service.save_json(
                project_id=project.id,
                stage="export",
                artifact_type=ArtifactType.OTHER,
                name="asset_manifest.json",
                relative_path=Path("06_export") / "asset_manifest.json",
                payload=[m.model_dump() for m in manifest_entries],
                run_id=run_id,
                metadata_json={"kind": "asset_manifest", "count": len(manifest_entries)},
                supersede_previous_drafts=False,
            )
            report.production_notes_artifact_id = notes_art.id
            report.manifest_artifact_id = manifest_art.id

            # 6. Build deterministic ZIP export bundle containing all active project outputs
            zip_bytes, included_files = await self._build_zip_bundle(
                project=project,
                report=report,
                notes_md=notes_md,
                artifacts=active_artifacts,
            )
            slug = _slugify(project.title)
            zip_art = await self._artifact_service.save_bytes(
                project_id=project.id,
                stage="export",
                artifact_type=ArtifactType.EXPORT_BUNDLE,
                name=f"{slug}_production_package.zip",
                content=zip_bytes,
                run_id=run_id,
                metadata_json={
                    "mime_type": "application/zip",
                    "publishing_mode": "MANUAL_ONLY",
                    "included_files": included_files,
                    "file_count": len(included_files),
                    "production_report": report.model_dump(mode="json"),
                },
            )
            report.export_zip_artifact_id = zip_art.id
            report.export_zip_relative_path = zip_art.relative_path
            report.export_zip_file_count = len(included_files)

            # 7. Create Gate 5 (production_package) human approval
            if request_final_approval and self._approval_service is not None:
                approval = await self._approval_service.request_approval(
                    project_id=project.id,
                    gate=ApprovalGate.PRODUCTION_PACKAGE,
                    run_id=run_id,
                    artifact_id=zip_art.id,
                    comments=(
                        f"Production package ZIP ready ({len(included_files)} files). "
                        "Approve for manual YouTube upload."
                    ),
                )
                report.approval_id = approval.id

            if agent_run is not None and self._agent_run_repo is not None:
                await self._agent_run_repo.mark_finished(
                    agent_run,
                    status=AgentRunStatus.COMPLETED,
                    output_summary_json={
                        "export_zip_artifact_id": zip_art.id,
                        "file_count": len(included_files),
                        "publishing_mode": "MANUAL_ONLY",
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

    async def _build_zip_bundle(
        self,
        *,
        project: Project,
        report: ProductionPackageReport,
        notes_md: str,
        artifacts: list[Artifact],
    ) -> tuple[bytes, list[str]]:
        buffer = io.BytesIO()
        included: list[str] = []
        used_arcnames: set[str] = set()

        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            # Always include top-level README_PRODUCTION.md and manifest.json
            zf.writestr("README_PRODUCTION.md", notes_md.encode("utf-8"))
            included.append("README_PRODUCTION.md")
            used_arcnames.add("README_PRODUCTION.md")

            manifest_payload = {
                "project_id": project.id,
                "title": project.title,
                "topic": project.topic,
                "publishing_mode": "MANUAL_ONLY",
                "manual_publishing_only": True,
                "total_estimated_duration_seconds": report.total_estimated_duration_seconds,
                "scene_sequence": [s.model_dump() for s in report.scene_sequence],
                "assets": [m.model_dump() for m in report.asset_manifest],
            }
            zf.writestr(
                "manifest.json",
                json.dumps(manifest_payload, indent=2, ensure_ascii=False).encode("utf-8"),
            )
            included.append("manifest.json")
            used_arcnames.add("manifest.json")

            for art in sorted(artifacts, key=lambda a: (a.stage, a.relative_path)):
                try:
                    _, raw_bytes = await self._artifact_service.read_artifact_bytes(
                        project.id, art.id
                    )
                except (LookupError, FileNotFoundError):
                    continue

                folder = _zip_folder_for_artifact(art)
                arcname = f"{folder}/{art.name}"
                if arcname in used_arcnames:
                    stem = Path(art.name).stem
                    suffix = "".join(Path(art.name).suffixes)
                    arcname = f"{folder}/{stem}_v{art.version}_{art.id[:6]}{suffix}"
                used_arcnames.add(arcname)
                zf.writestr(arcname, raw_bytes)
                included.append(arcname)

        return buffer.getvalue(), included

    async def get_latest_export(self, project_id: str) -> Artifact | None:
        await self._require_project(project_id)
        exports = await self._artifact_service.list_artifacts(
            project_id, artifact_type=ArtifactType.EXPORT_BUNDLE
        )
        return exports[0] if exports else None
