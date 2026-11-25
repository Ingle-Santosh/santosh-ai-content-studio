import time
from pathlib import Path

from content_studio.config.settings import Settings
from content_studio.contracts.guidelines import ChannelGuidelinesConfig
from content_studio.contracts.script import (
    GeneratedScriptReport,
    ScriptLLMOutput,
    ScriptSectionItem,
    ScriptValidationReport,
)
from content_studio.database.models.enums import (
    AgentRunStatus,
    ApprovalGate,
    ApprovalStatus,
    ArtifactStatus,
    ArtifactType,
    ClaimVerdict,
    SourceStatus,
)
from content_studio.database.models.project import Project
from content_studio.database.models.script import Script, ScriptVersion
from content_studio.database.repositories import (
    AgentRunRepository,
    CompetitorRepository,
    FactCheckRepository,
    ProjectRepository,
    ResearchRepository,
    ScriptRepository,
)
from content_studio.providers.llm import LLMMessage, ModelRouter, TaskType
from content_studio.services.approval_service import ApprovalService
from content_studio.services.artifact_service import (
    ArtifactService,
    ProjectNotFoundError,
    ResourceNotFoundError,
)
from content_studio.services.guideline_service import ChannelGuidelineService
from content_studio.services.script_validator import (
    count_hinglish_markers,
    validate_script_sections,
)


class WorkflowGateError(RuntimeError):
    """Raised when a required human approval gate has not been satisfied."""


class ResearchNotApprovedError(WorkflowGateError):
    """Raised when script generation requires an approved Gate 2 research report."""


class ScriptNotFoundError(ResourceNotFoundError):
    """Raised when a requested script or script version does not exist."""


def _load_prompt(base_dir: Path, relative_path: str) -> str:
    return (base_dir / relative_path).read_text(encoding="utf-8").strip()


def _format_guidelines(cfg: ChannelGuidelinesConfig) -> str:
    lines = [
        f"- Audience: {cfg.audience}",
        f"- Narration language: {cfg.narration_language}",
        f"- Technical terminology: {cfg.technical_terminology}",
        f"- Explanation style: {cfg.explanation_style}",
        f"- Presentation style: {cfg.presentation_style}",
        f"- Visual standards: {cfg.visual_standards}",
        f"- Tutorial approach: {cfg.tutorial_approach}",
        f"- Creator bio note: {cfg.creator_bio_note}",
        f"- Publishing mode: {cfg.publishing_mode}",
    ]
    for rule in cfg.extra_rules:
        lines.append(f"- Extra rule: {rule}")
    return "\n".join(lines)


def _render_script_markdown(
    *,
    title: str,
    version_number: int,
    language: str,
    sections: list[ScriptSectionItem],
    validation: ScriptValidationReport,
) -> str:
    mins = validation.total_duration_seconds // 60
    secs = validation.total_duration_seconds % 60
    lines: list[str] = [
        f"# {title} (v{version_number})",
        "",
        f"- **Language**: {language}",
        f"- **Estimated Duration**: {mins}m {secs}s ({validation.total_words} words)",
        f"- **Validation**: {'PASSED' if validation.passed else 'FAILED'} "
        f"(score {validation.score:.1f}/100)",
        "",
    ]
    for idx, section in enumerate(sections, start=1):
        lines.extend(
            [
                f"## {idx}. {section.title} (`{section.section_type.value}`, "
                f"~{section.estimated_duration_seconds}s)",
                "",
                section.narration,
                "",
            ]
        )
        if section.visual_instructions:
            lines.append(f"**Visuals**: {section.visual_instructions}")
        if section.screen_recording_requirements:
            lines.append(f"**Screen Recording**: {section.screen_recording_requirements}")
        if section.code_demo_references:
            lines.append("**Code Demos**: " + ", ".join(section.code_demo_references))
        if section.source_urls:
            lines.append("**Sources**: " + ", ".join(section.source_urls))
        lines.append("")
    return "\n".join(lines)


class ScriptwriterService:
    """Generates, validates, versions, and approves structured channel-aligned video scripts."""

    def __init__(
        self,
        *,
        app_settings: Settings,
        project_repo: ProjectRepository,
        script_repo: ScriptRepository,
        research_repo: ResearchRepository,
        fact_check_repo: FactCheckRepository,
        competitor_repo: CompetitorRepository,
        guideline_service: ChannelGuidelineService,
        artifact_service: ArtifactService,
        model_router: ModelRouter,
        approval_service: ApprovalService | None = None,
        agent_run_repo: AgentRunRepository | None = None,
    ) -> None:
        self._settings = app_settings
        self._project_repo = project_repo
        self._script_repo = script_repo
        self._research_repo = research_repo
        self._fact_check_repo = fact_check_repo
        self._competitor_repo = competitor_repo
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

    async def _check_research_approval(self, project_id: str) -> None:
        if self._approval_service is None:
            return
        approvals = await self._approval_service.list_approvals(
            project_id=project_id,
            gate=ApprovalGate.RESEARCH,
            status=ApprovalStatus.APPROVED,
        )
        if not approvals:
            raise ResearchNotApprovedError(
                "Research approval gate (Gate 2) must be APPROVED before generating the script."
            )

    async def _persist_version(
        self,
        *,
        project: Project,
        title: str,
        language: str,
        sections: list[ScriptSectionItem],
        revision_notes: str | None,
        request_script_approval: bool,
        run_id: str | None,
    ) -> GeneratedScriptReport:
        sources = await self._research_repo.list_sources(project.id, status=SourceStatus.EXTRACTED)
        known_urls = {src.normalized_url for src in sources}

        claims = await self._fact_check_repo.list_claims(project.id)
        risky_claims = [
            c
            for c in claims
            if c.verdict in {ClaimVerdict.UNSUPPORTED.value, ClaimVerdict.CONFLICTING.value}
        ]

        validation = validate_script_sections(
            sections,
            target_duration_minutes=int(project.config.get("duration_minutes", 15)),
            include_code_demo=bool(project.config.get("include_code_demo", True)),
            language=language,
            known_source_urls=known_urls,
            unsupported_claim_count=len(risky_claims),
        )

        script = await self._script_repo.get_or_create_script(
            project_id=project.id,
            title=title,
        )
        next_version = script.current_version + 1

        md_content = _render_script_markdown(
            title=title,
            version_number=next_version,
            language=language,
            sections=sections,
            validation=validation,
        )
        md_artifact = await self._artifact_service.save_text(
            project_id=project.id,
            stage="script",
            artifact_type=ArtifactType.SCRIPT,
            name=f"script_v{next_version}.md",
            relative_path=Path("03_script") / f"script_v{next_version}.md",
            content=md_content,
            run_id=run_id,
            metadata_json={
                "format": "markdown",
                "script_version": next_version,
                "validation_score": validation.score,
            },
        )
        json_artifact = await self._artifact_service.save_json(
            project_id=project.id,
            stage="script",
            artifact_type=ArtifactType.SCRIPT,
            name=f"script_v{next_version}.json",
            relative_path=Path("03_script") / f"script_v{next_version}.json",
            payload={
                "title": title,
                "version_number": next_version,
                "language": language,
                "sections": [sec.model_dump() for sec in sections],
                "validation": validation.model_dump(),
            },
            run_id=run_id,
            metadata_json={"format": "json", "script_version": next_version},
            supersede_previous_drafts=False,
        )

        version_row = await self._script_repo.create_version(
            script,
            project_id=project.id,
            language=language,
            total_estimated_duration_seconds=validation.total_duration_seconds,
            word_count=validation.total_words,
            sections_json=[sec.model_dump() for sec in sections],
            validation_report_json=validation.model_dump(),
            artifact_id=md_artifact.id,
            run_id=run_id,
            revision_notes=revision_notes,
            title=title,
        )

        approval_id: str | None = None
        if request_script_approval and self._approval_service is not None:
            approval = await self._approval_service.request_approval(
                project_id=project.id,
                gate=ApprovalGate.SCRIPT,
                run_id=run_id,
                artifact_id=md_artifact.id,
                comments=(
                    f"Script v{version_row.version_number} ready for review "
                    f"(validation score {validation.score:.1f}/100)."
                ),
            )
            approval_id = approval.id

        return GeneratedScriptReport(
            script_id=script.id,
            script_version_id=version_row.id,
            project_id=project.id,
            title=script.title,
            version_number=version_row.version_number,
            language=version_row.language,
            status=version_row.status,
            total_estimated_duration_seconds=version_row.total_estimated_duration_seconds,
            word_count=version_row.word_count,
            sections=sections,
            validation=validation,
            approval_id=approval_id,
            script_markdown_artifact_id=md_artifact.id,
            script_json_artifact_id=json_artifact.id,
            created_at=version_row.created_at,
        )

    async def generate_script(
        self,
        project_id: str,
        *,
        revision_notes: str | None = None,
        require_approved_research: bool = False,
        request_script_approval: bool = True,
        run_id: str | None = None,
    ) -> GeneratedScriptReport:
        project = await self._require_project(project_id)
        if require_approved_research:
            await self._check_research_approval(project_id)

        start_ts = time.perf_counter()
        agent_run = None
        if self._agent_run_repo is not None:
            agent_run = await self._agent_run_repo.create(
                project_id=project_id,
                run_id=run_id,
                agent_name="scriptwriter",
                stage="script",
                status=AgentRunStatus.RUNNING,
                input_summary_json={"has_revision_notes": bool(revision_notes)},
            )

        try:
            guidelines = await self._guideline_service.get_active_config()
            findings = await self._research_repo.list_findings(project_id)
            claims = await self._fact_check_repo.list_claims(project_id)
            competitors = await self._competitor_repo.list_for_project(project_id)
            existing_script = await self._script_repo.get_for_project(project_id)

            research_lines = [
                f"- [{f.category}] {f.title}: {f.summary} "
                f"(sources: {', '.join(f.source_urls_json)})"
                for f in findings
            ]
            verified_claims = [c for c in claims if c.verdict == ClaimVerdict.VERIFIED.value]
            for claim in verified_claims:
                research_lines.append(f"- [VERIFIED CLAIM] {claim.statement}")

            warning_lines = [
                f"- [{c.verdict} / risk={c.risk_level}] {c.statement} ({c.rationale})"
                for c in claims
                if c.verdict in {ClaimVerdict.UNSUPPORTED.value, ClaimVerdict.CONFLICTING.value}
            ]

            competitor_lines = [
                f"- {v.title} ({v.channel_name or 'Unknown'}): "
                f"topics={', '.join(v.topics_covered_json)}"
                for v in competitors[:5]
            ]

            revision_block = "Initial draft (no prior script)."
            if revision_notes or (existing_script and existing_script.versions):
                parts: list[str] = []
                if existing_script and existing_script.versions:
                    latest = existing_script.versions[0]
                    prev_titles = [s.get("title", "") for s in latest.sections_json]
                    parts.append(
                        f"Revising previous script v{latest.version_number} "
                        f"(sections: {', '.join(prev_titles)})."
                    )
                if revision_notes:
                    parts.append(f"Creator feedback: {revision_notes}")
                revision_block = "\n".join(parts)

            duration_minutes = int(project.config.get("duration_minutes", 15))
            language = str(project.config.get("language", guidelines.narration_language))

            system_prompt = _load_prompt(self._settings.BASE_DIR, "prompts/scriptwriter/system.md")
            user_template = _load_prompt(self._settings.BASE_DIR, "prompts/scriptwriter/user.md")
            user_prompt = user_template.format(
                topic=project.topic,
                title=project.title,
                duration_minutes=duration_minutes,
                duration_seconds=duration_minutes * 60,
                audience_level=project.config.get("audience_level", guidelines.audience),
                language=language,
                include_code_demo=project.config.get("include_code_demo", True),
                include_animations=project.config.get("include_animations", True),
                guidelines_block=_format_guidelines(guidelines),
                research_block="\n".join(research_lines) or "(No research findings captured yet)",
                warnings_block="\n".join(warning_lines) or "(No unsupported claims flagged)",
                competitor_block="\n".join(competitor_lines) or "(No competitor notes yet)",
                revision_block=revision_block,
            )

            llm_result = await self._model_router.generate_structured(
                task=TaskType.SCRIPTWRITING,
                messages=[
                    LLMMessage(role="system", content=system_prompt),
                    LLMMessage(role="user", content=user_prompt),
                ],
                response_model=ScriptLLMOutput,
                project_id=project.id,
                run_id=run_id,
                node_name="scriptwriter",
            )
            generated = llm_result.data

            # Safeguard: if Hinglish was requested but model produced pure English, run 1 rewrite
            effective_lang = (generated.language or language).strip()
            if effective_lang.lower() == "hinglish":
                combined = " ".join(sec.narration for sec in generated.sections)
                if count_hinglish_markers(combined) < 4:
                    try:
                        rewrite_result = await self._model_router.generate_structured(
                            task=TaskType.SCRIPTWRITING,
                            messages=[
                                LLMMessage(role="system", content=system_prompt),
                                LLMMessage(
                                    role="user",
                                    content=(
                                        "Your previous draft was written in pure English, NOT "
                                        "Hinglish. Rewrite ALL 9 sections so every `narration` is "
                                        "natural conversational Hinglish (Romanized Hindi sentence "
                                        "structure like 'Namaste dosto! Aaj hum... samjhenge, "
                                        "kyunki... dekhte hain') while keeping technical terms in "
                                        "exact English. Keep the same 9 section types and return "
                                        "valid JSON.\n\n"
                                        f"Previous draft JSON:\n{generated.model_dump_json()}"
                                    ),
                                ),
                            ],
                            response_model=ScriptLLMOutput,
                            project_id=project.id,
                            run_id=run_id,
                            node_name="scriptwriter_hinglish_rewrite",
                        )
                        rewritten_text = " ".join(
                            sec.narration for sec in rewrite_result.data.sections
                        )
                        if count_hinglish_markers(rewritten_text) >= count_hinglish_markers(
                            combined
                        ):
                            generated = rewrite_result.data
                    except Exception:  # noqa: BLE001
                        pass

            report = await self._persist_version(
                project=project,
                title=generated.title,
                language=generated.language or language,
                sections=generated.sections,
                revision_notes=revision_notes,
                request_script_approval=request_script_approval,
                run_id=run_id,
            )

            if agent_run is not None and self._agent_run_repo is not None:
                await self._agent_run_repo.mark_finished(
                    agent_run,
                    status=AgentRunStatus.COMPLETED,
                    output_summary_json={
                        "version_number": report.version_number,
                        "word_count": report.word_count,
                        "validation_passed": report.validation.passed,
                        "validation_score": report.validation.score,
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

    async def save_manual_revision(
        self,
        project_id: str,
        *,
        sections: list[ScriptSectionItem],
        title: str | None = None,
        language: str | None = None,
        revision_notes: str | None = None,
        request_script_approval: bool = True,
    ) -> GeneratedScriptReport:
        project = await self._require_project(project_id)
        effective_title = (title or project.title).strip()
        effective_language = language or str(project.config.get("language", "Hinglish"))
        return await self._persist_version(
            project=project,
            title=effective_title,
            language=effective_language,
            sections=sections,
            revision_notes=revision_notes or "Manual creator edit",
            request_script_approval=request_script_approval,
            run_id=None,
        )

    async def approve_version(
        self,
        project_id: str,
        version_number: int,
        *,
        reviewer: str | None = "Creator",
        comments: str | None = None,
    ) -> ScriptVersion:
        await self._require_project(project_id)
        script = await self._script_repo.get_for_project(project_id)
        if script is None:
            raise ScriptNotFoundError(f"No script exists for project '{project_id}'.")

        version = await self._script_repo.get_version(project_id, version_number)
        if version is None:
            raise ScriptNotFoundError(
                f"Script version v{version_number} not found for project '{project_id}'."
            )

        approved = await self._script_repo.approve_version(script, version)

        if approved.artifact_id is not None:
            await self._artifact_service.update_status(
                project_id, approved.artifact_id, ArtifactStatus.APPROVED
            )

        if self._approval_service is not None:
            pending = await self._approval_service.list_approvals(
                project_id=project_id,
                gate=ApprovalGate.SCRIPT,
                status=ApprovalStatus.PENDING,
            )
            for item in pending:
                await self._approval_service.decide_approval(
                    item.id,
                    status=ApprovalStatus.APPROVED,
                    reviewer=reviewer,
                    comments=comments or f"Approved script v{version_number}.",
                )

        return approved

    async def get_script(self, project_id: str) -> Script | None:
        await self._require_project(project_id)
        return await self._script_repo.get_for_project(project_id)
