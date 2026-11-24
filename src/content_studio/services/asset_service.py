import re
import time
from pathlib import Path

from content_studio.config.settings import Settings
from content_studio.contracts.assets import (
    AnimationSpecLLMOutput,
    AssetCategory,
    AssetGenerationBatchReport,
    AssetPlan,
    CodeDemoLLMOutput,
    DiagramLLMOutput,
    GeneratedAssetOutcome,
    PlannedAssetItem,
    ScreenshotAnnotation,
    ScreenshotProvenance,
)
from content_studio.database.models.artifact import Artifact
from content_studio.database.models.enums import (
    AgentRunStatus,
    ArtifactStatus,
    ArtifactType,
    SceneVisualType,
)
from content_studio.database.models.project import Project
from content_studio.database.repositories import (
    AgentRunRepository,
    ProjectRepository,
    SceneRepository,
)
from content_studio.providers.image import BaseImageProvider
from content_studio.providers.llm import LLMMessage, ModelRouter, TaskType
from content_studio.services.animation_renderer import (
    render_animation_html,
    validate_sanitized_html,
)
from content_studio.services.artifact_service import ArtifactService, ProjectNotFoundError
from content_studio.services.code_sandbox import run_python_isolated, run_sql_isolated
from content_studio.services.diagram_renderer import (
    render_mermaid_to_svg,
    validate_mermaid_syntax,
)
from content_studio.services.screenshot_utils import (
    render_annotation_overlay_svg,
    validate_uploaded_screenshot,
)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: str) -> str:
    return _SLUG_RE.sub("_", text.strip().lower()).strip("_")[:48] or "asset"


def _normalize_category(raw: str) -> AssetCategory | None:
    cleaned = raw.strip().lower()
    mapping = {
        "diagram": AssetCategory.DIAGRAM,
        "flowchart": AssetCategory.DIAGRAM,
        "architecture": AssetCategory.DIAGRAM,
        "animation": AssetCategory.ANIMATION,
        "html_animation": AssetCategory.ANIMATION,
        "image": AssetCategory.IMAGE,
        "illustration": AssetCategory.IMAGE,
        "screenshot": AssetCategory.SCREENSHOT,
        "code": AssetCategory.CODE_DEMO,
        "code_demo": AssetCategory.CODE_DEMO,
        "demo": AssetCategory.CODE_DEMO,
    }
    return mapping.get(cleaned)


def _default_extension(category: AssetCategory) -> str:
    return {
        AssetCategory.DIAGRAM: ".mmd",
        AssetCategory.ANIMATION: ".html",
        AssetCategory.IMAGE: ".svg",
        AssetCategory.SCREENSHOT: ".png",
        AssetCategory.CODE_DEMO: ".py",
    }[category]


def _load_prompt(base_dir: Path, relative_path: str) -> str:
    return (base_dir / relative_path).read_text(encoding="utf-8").strip()


class AssetGenerationService:
    """Plans and generates versioned visual & code assets linked to storyboard scenes."""

    def __init__(
        self,
        *,
        app_settings: Settings,
        project_repo: ProjectRepository,
        scene_repo: SceneRepository,
        artifact_service: ArtifactService,
        model_router: ModelRouter,
        image_provider: BaseImageProvider,
        agent_run_repo: AgentRunRepository | None = None,
    ) -> None:
        self._settings = app_settings
        self._project_repo = project_repo
        self._scene_repo = scene_repo
        self._artifact_service = artifact_service
        self._model_router = model_router
        self._image_provider = image_provider
        self._agent_run_repo = agent_run_repo

    async def _require_project(self, project_id: str) -> Project:
        project = await self._project_repo.get_by_id(project_id)
        if project is None:
            raise ProjectNotFoundError(f"Project '{project_id}' not found.")
        return project

    async def plan_assets(
        self,
        project_id: str,
        *,
        run_id: str | None = None,
    ) -> AssetPlan:
        await self._require_project(project_id)
        scenes = list(await self._scene_repo.list_for_project(project_id))

        items: list[PlannedAssetItem] = []
        used_keys: set[str] = set()

        for scene in scenes:
            reqs = list(scene.asset_requirements_json or [])
            if not reqs:
                # Derive asset item from scene visual_type when explicit requirements are absent
                inferred = _normalize_category(scene.visual_type)
                if inferred is not None and scene.visual_type != SceneVisualType.FACE_CAM.value:
                    reqs = [
                        {
                            "asset_type": inferred.value,
                            "title": scene.title,
                            "description": scene.narration[:240],
                        }
                    ]

            for idx, req in enumerate(reqs, start=1):
                cat = _normalize_category(str(req.get("asset_type", "")))
                if cat is None:
                    continue
                title = str(req.get("title") or scene.title).strip()
                desc = str(req.get("description") or scene.narration[:240]).strip()
                base_key = f"s{scene.scene_number:02d}_{cat.value}_{idx}"
                key = base_key
                while key in used_keys:
                    key = f"{key}_x"
                used_keys.add(key)

                filename = f"{key}_{_slugify(title)}{_default_extension(cat)}"
                items.append(
                    PlannedAssetItem(
                        asset_key=key,
                        scene_id=scene.id,
                        scene_number=scene.scene_number,
                        category=cat,
                        title=title,
                        description=desc,
                        filename=filename,
                        priority=1
                        if cat in {AssetCategory.DIAGRAM, AssetCategory.CODE_DEMO}
                        else 2,
                    )
                )

        plan = AssetPlan(
            project_id=project_id,
            total_scenes=len(scenes),
            items=items,
        )
        plan_art = await self._artifact_service.save_json(
            project_id=project_id,
            stage="visuals",
            artifact_type=ArtifactType.OTHER,
            name="asset_plan.json",
            relative_path=Path("04_visuals") / "asset_plan.json",
            payload=plan,
            run_id=run_id,
            metadata_json={"kind": "asset_plan", "total_items": len(items)},
        )
        plan.plan_artifact_id = plan_art.id
        return plan

    async def _generate_diagram(
        self,
        project: Project,
        item: PlannedAssetItem,
        *,
        run_id: str | None,
    ) -> GeneratedAssetOutcome:
        system_prompt = _load_prompt(
            self._settings.BASE_DIR, "prompts/asset_generation/diagram_system.md"
        )
        user_prompt = (
            f"Video Topic: {project.topic}\n"
            f"Scene #{item.scene_number}\n"
            f"Diagram Title: {item.title}\n"
            f"Requirements: {item.description}\n"
            "Generate a clean Mermaid diagram."
        )
        result = await self._model_router.generate_structured(
            task=TaskType.ASSET_PLANNING,
            messages=[
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=user_prompt),
            ],
            response_model=DiagramLLMOutput,
            project_id=project.id,
            run_id=run_id,
            node_name="diagram_generator",
        )
        diagram = result.data
        syntax_issues = validate_mermaid_syntax(diagram.mermaid_code)
        if syntax_issues:
            return GeneratedAssetOutcome(
                asset_key=item.asset_key,
                scene_number=item.scene_number,
                category=item.category,
                title=item.title,
                status="FAILED",
                error="; ".join(syntax_issues),
                validation_passed=False,
            )

        stem = Path(item.filename).stem
        mmd_art = await self._artifact_service.save_text(
            project_id=project.id,
            stage="visuals",
            artifact_type=ArtifactType.DIAGRAM_MMD,
            name=f"{stem}.mmd",
            relative_path=Path("04_visuals") / "diagrams" / f"{stem}.mmd",
            content=diagram.mermaid_code.strip() + "\n",
            run_id=run_id,
            metadata_json={
                "asset_key": item.asset_key,
                "scene_id": item.scene_id,
                "scene_number": item.scene_number,
                "diagram_type": diagram.diagram_type,
                "caption": diagram.caption,
                "validation_passed": True,
            },
            supersede_previous_drafts=False,
        )

        svg_content, renderer_name = await render_mermaid_to_svg(
            diagram.mermaid_code,
            title=diagram.title,
        )
        svg_art = await self._artifact_service.save_text(
            project_id=project.id,
            stage="visuals",
            artifact_type=ArtifactType.DIAGRAM_SVG,
            name=f"{stem}.svg",
            relative_path=Path("04_visuals") / "diagrams" / f"{stem}.svg",
            content=svg_content,
            run_id=run_id,
            metadata_json={
                "asset_key": item.asset_key,
                "scene_id": item.scene_id,
                "scene_number": item.scene_number,
                "source_mmd_artifact_id": mmd_art.id,
                "renderer": renderer_name,
                "validation_passed": True,
            },
            supersede_previous_drafts=False,
        )

        return GeneratedAssetOutcome(
            asset_key=item.asset_key,
            scene_number=item.scene_number,
            category=item.category,
            title=item.title,
            status="SUCCEEDED",
            artifact_ids=[mmd_art.id, svg_art.id],
            validation_passed=True,
        )

    async def _generate_animation(
        self,
        project: Project,
        item: PlannedAssetItem,
        *,
        run_id: str | None,
    ) -> GeneratedAssetOutcome:
        system_prompt = _load_prompt(
            self._settings.BASE_DIR, "prompts/asset_generation/animation_system.md"
        )
        user_prompt = (
            f"Video Topic: {project.topic}\n"
            f"Scene #{item.scene_number}\n"
            f"Animation Title: {item.title}\n"
            f"Requirements: {item.description}\n"
            "Generate a step-by-step interactive animation specification."
        )
        result = await self._model_router.generate_structured(
            task=TaskType.ASSET_PLANNING,
            messages=[
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=user_prompt),
            ],
            response_model=AnimationSpecLLMOutput,
            project_id=project.id,
            run_id=run_id,
            node_name="animation_generator",
        )
        html_doc = render_animation_html(self._settings.BASE_DIR, result.data)
        html_issues = validate_sanitized_html(html_doc)
        if html_issues:
            return GeneratedAssetOutcome(
                asset_key=item.asset_key,
                scene_number=item.scene_number,
                category=item.category,
                title=item.title,
                status="FAILED",
                error="; ".join(html_issues),
                validation_passed=False,
            )

        stem = Path(item.filename).stem
        art = await self._artifact_service.save_text(
            project_id=project.id,
            stage="visuals",
            artifact_type=ArtifactType.HTML_ANIMATION,
            name=f"{stem}.html",
            relative_path=Path("04_visuals") / "animations" / f"{stem}.html",
            content=html_doc,
            run_id=run_id,
            metadata_json={
                "asset_key": item.asset_key,
                "scene_id": item.scene_id,
                "scene_number": item.scene_number,
                "steps_count": len(result.data.steps),
                "validation_passed": True,
            },
            supersede_previous_drafts=False,
        )
        return GeneratedAssetOutcome(
            asset_key=item.asset_key,
            scene_number=item.scene_number,
            category=item.category,
            title=item.title,
            status="SUCCEEDED",
            artifact_ids=[art.id],
            validation_passed=True,
        )

    async def _generate_image(
        self,
        project: Project,
        item: PlannedAssetItem,
        *,
        run_id: str | None,
    ) -> GeneratedAssetOutcome:
        img = await self._image_provider.generate_image(
            title=item.title,
            prompt=item.description or project.topic,
        )
        stem = Path(item.filename).stem
        art = await self._artifact_service.save_bytes(
            project_id=project.id,
            stage="visuals",
            artifact_type=ArtifactType.IMAGE,
            name=f"{stem}{img.extension}",
            relative_path=Path("04_visuals") / "images" / f"{stem}{img.extension}",
            content=img.content,
            run_id=run_id,
            metadata_json={
                "asset_key": item.asset_key,
                "scene_id": item.scene_id,
                "scene_number": item.scene_number,
                "mime_type": img.mime_type,
                "provider": img.provider,
                "validation_passed": True,
            },
            supersede_previous_drafts=False,
        )
        return GeneratedAssetOutcome(
            asset_key=item.asset_key,
            scene_number=item.scene_number,
            category=item.category,
            title=item.title,
            status="SUCCEEDED",
            artifact_ids=[art.id],
            validation_passed=True,
        )

    async def _generate_code_demo(
        self,
        project: Project,
        item: PlannedAssetItem,
        *,
        run_id: str | None,
    ) -> GeneratedAssetOutcome:
        system_prompt = _load_prompt(
            self._settings.BASE_DIR, "prompts/asset_generation/code_demo_system.md"
        )
        user_prompt = (
            f"Video Topic: {project.topic}\n"
            f"Scene #{item.scene_number}\n"
            f"Code Demo Title: {item.title}\n"
            f"Requirements: {item.description}\n"
            "Generate a self-contained runnable Python or SQLite SQL demo."
        )
        result = await self._model_router.generate_structured(
            task=TaskType.CODE_GENERATION,
            messages=[
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=user_prompt),
            ],
            response_model=CodeDemoLLMOutput,
            project_id=project.id,
            run_id=run_id,
            node_name="code_demo_generator",
        )
        demo = result.data

        if demo.language == "sql":
            exec_res = await run_sql_isolated(demo.code)
            ext = ".sql"
        else:
            exec_res = await run_python_isolated(demo.code)
            ext = ".py"

        stem = Path(item.filename).stem
        status = ArtifactStatus.DRAFT if exec_res.passed else ArtifactStatus.FAILED
        art = await self._artifact_service.save_text(
            project_id=project.id,
            stage="demos",
            artifact_type=ArtifactType.CODE_DEMO,
            name=f"{stem}{ext}",
            relative_path=Path("05_demos") / f"{stem}{ext}",
            content=demo.code.rstrip() + "\n",
            run_id=run_id,
            status=status,
            metadata_json={
                "asset_key": item.asset_key,
                "scene_id": item.scene_id,
                "scene_number": item.scene_number,
                "language": demo.language,
                "explanation": demo.explanation,
                "validation_passed": exec_res.passed,
                "execution": exec_res.model_dump(),
            },
            supersede_previous_drafts=False,
        )

        if not exec_res.passed:
            reason = "; ".join(exec_res.blocked_reasons) or exec_res.stderr or "Execution failed"
            return GeneratedAssetOutcome(
                asset_key=item.asset_key,
                scene_number=item.scene_number,
                category=item.category,
                title=item.title,
                status="FAILED",
                artifact_ids=[art.id],
                error=reason,
                validation_passed=False,
            )

        # Supersede any prior FAILED attempts for the same asset_key on successful retry
        existing_arts = await self._artifact_service.list_artifacts(
            project.id, artifact_type=ArtifactType.CODE_DEMO
        )
        for prev in existing_arts:
            if (
                prev.id != art.id
                and prev.status == ArtifactStatus.FAILED.value
                and (prev.metadata_json or {}).get("asset_key") == item.asset_key
            ):
                await self._artifact_service.update_status(
                    project.id, prev.id, ArtifactStatus.SUPERSEDED
                )

        return GeneratedAssetOutcome(
            asset_key=item.asset_key,
            scene_number=item.scene_number,
            category=item.category,
            title=item.title,
            status="SUCCEEDED",
            artifact_ids=[art.id],
            validation_passed=True,
        )

    async def generate_assets(
        self,
        project_id: str,
        *,
        asset_keys: list[str] | None = None,
        run_id: str | None = None,
    ) -> AssetGenerationBatchReport:
        project = await self._require_project(project_id)
        start_ts = time.perf_counter()

        plan = await self.plan_assets(project_id, run_id=run_id)
        target_items = (
            [item for item in plan.items if item.asset_key in set(asset_keys)]
            if asset_keys
            else list(plan.items)
        )

        agent_run = None
        if self._agent_run_repo is not None:
            agent_run = await self._agent_run_repo.create(
                project_id=project_id,
                run_id=run_id,
                agent_name="asset_generator",
                stage="visuals",
                status=AgentRunStatus.RUNNING,
                input_summary_json={"target_assets": [i.asset_key for i in target_items]},
            )

        outcomes: list[GeneratedAssetOutcome] = []
        for item in target_items:
            try:
                if item.category == AssetCategory.DIAGRAM:
                    outcome = await self._generate_diagram(project, item, run_id=run_id)
                elif item.category == AssetCategory.ANIMATION:
                    outcome = await self._generate_animation(project, item, run_id=run_id)
                elif item.category == AssetCategory.IMAGE:
                    outcome = await self._generate_image(project, item, run_id=run_id)
                elif item.category == AssetCategory.CODE_DEMO:
                    outcome = await self._generate_code_demo(project, item, run_id=run_id)
                else:
                    # Screenshots require explicit upload or authorized capture (never fabricated)
                    outcome = GeneratedAssetOutcome(
                        asset_key=item.asset_key,
                        scene_number=item.scene_number,
                        category=item.category,
                        title=item.title,
                        status="SKIPPED",
                        error=(
                            "Screenshots require user upload or authorized capture with provenance "
                            "(never fabricated automatically)."
                        ),
                        validation_passed=True,
                    )
            except Exception as exc:  # noqa: BLE001
                outcome = GeneratedAssetOutcome(
                    asset_key=item.asset_key,
                    scene_number=item.scene_number,
                    category=item.category,
                    title=item.title,
                    status="FAILED",
                    error=str(exc),
                    validation_passed=False,
                )
            outcomes.append(outcome)

        succeeded = sum(1 for o in outcomes if o.status == "SUCCEEDED")
        failed = sum(1 for o in outcomes if o.status == "FAILED")
        skipped = sum(1 for o in outcomes if o.status == "SKIPPED")

        if agent_run is not None and self._agent_run_repo is not None:
            await self._agent_run_repo.mark_finished(
                agent_run,
                status=AgentRunStatus.COMPLETED if failed == 0 else AgentRunStatus.FAILED,
                output_summary_json={
                    "succeeded": succeeded,
                    "failed": failed,
                    "skipped": skipped,
                },
                error_message=f"{failed} asset(s) failed generation." if failed else None,
                duration_ms=int((time.perf_counter() - start_ts) * 1000),
            )

        return AssetGenerationBatchReport(
            project_id=project_id,
            total_planned=len(target_items),
            succeeded_count=succeeded,
            failed_count=failed,
            skipped_count=skipped,
            outcomes=outcomes,
        )

    async def register_screenshot(
        self,
        project_id: str,
        *,
        filename: str,
        content: bytes,
        provenance: ScreenshotProvenance,
        scene_number: int | None = None,
        annotations: list[ScreenshotAnnotation] | None = None,
        run_id: str | None = None,
    ) -> tuple[Artifact, Artifact | None]:
        """Validate and store a real screenshot with mandatory provenance & annotations."""
        await self._require_project(project_id)
        ext, mime_type = validate_uploaded_screenshot(content)
        stem = _slugify(Path(filename).stem)

        screenshot_art = await self._artifact_service.save_bytes(
            project_id=project_id,
            stage="visuals",
            artifact_type=ArtifactType.SCREENSHOT,
            name=f"{stem}{ext}",
            relative_path=Path("04_visuals") / "screenshots" / f"{stem}{ext}",
            content=content,
            run_id=run_id,
            metadata_json={
                "mime_type": mime_type,
                "scene_number": scene_number,
                "provenance": provenance.model_dump(mode="json"),
                "annotations": [ann.model_dump() for ann in (annotations or [])],
                "validation_passed": True,
            },
            supersede_previous_drafts=False,
        )

        overlay_art: Artifact | None = None
        if annotations:
            overlay_svg = render_annotation_overlay_svg(annotations)
            overlay_art = await self._artifact_service.save_text(
                project_id=project_id,
                stage="visuals",
                artifact_type=ArtifactType.DIAGRAM_SVG,
                name=f"{stem}_annotations.svg",
                relative_path=Path("04_visuals") / "screenshots" / f"{stem}_annotations.svg",
                content=overlay_svg,
                run_id=run_id,
                metadata_json={
                    "parent_screenshot_id": screenshot_art.id,
                    "scene_number": scene_number,
                    "annotations_count": len(annotations),
                    "validation_passed": True,
                },
                supersede_previous_drafts=False,
            )

        return screenshot_art, overlay_art
