import time
from pathlib import Path

from content_studio.config.settings import Settings
from content_studio.contracts.fact_check import (
    FactCheckLLMOutput,
    FactCheckReport,
    VerifiedClaimSummary,
)
from content_studio.database.models.claim import Claim
from content_studio.database.models.enums import (
    AgentRunStatus,
    ApprovalGate,
    ArtifactType,
    ClaimVerdict,
    EvidenceStance,
    RiskLevel,
    SourceStatus,
)
from content_studio.database.models.project import Project
from content_studio.database.models.source import Source
from content_studio.database.repositories import (
    AgentRunRepository,
    FactCheckRepository,
    ProjectRepository,
    ResearchRepository,
)
from content_studio.providers.llm import LLMMessage, ModelRouter, TaskType
from content_studio.services.approval_service import ApprovalService
from content_studio.services.artifact_service import ArtifactService, ProjectNotFoundError
from content_studio.services.web_extractor import normalize_url

_MAX_SOURCE_TEXT_IN_PROMPT = 3000


def _load_prompt(base_dir: Path, relative_path: str) -> str:
    return (base_dir / relative_path).read_text(encoding="utf-8").strip()


def _render_fact_check_markdown(report: FactCheckReport) -> str:
    lines: list[str] = [
        f"# Fact-Check Report: {report.topic}",
        "",
        f"- **Project ID**: `{report.project_id}`",
        f"- **Generated At**: {report.generated_at.isoformat()}",
        (
            f"- **Claims**: {report.total_claims} total | "
            f"{report.verified_count} verified | {report.unsupported_count} unsupported | "
            f"{report.conflicting_count} conflicting | {report.uncertain_count} uncertain"
        ),
        "",
        "## Overall Assessment",
        "",
        report.overall_assessment,
        "",
    ]

    if report.high_risk_warnings:
        lines.append("## High-Risk Warnings")
        lines.append("")
        for warn in report.high_risk_warnings:
            lines.append(f"- ⚠️ {warn}")
        lines.append("")

    if report.claims:
        lines.append("## Audited Claims")
        lines.append("")
        for idx, claim in enumerate(report.claims, start=1):
            lines.append(
                f"### {idx}. [{claim.verdict.value}] (risk: `{claim.risk_level.value}`, "
                f"confidence: {claim.confidence:.2f})"
            )
            lines.append("")
            lines.append(f"> {claim.statement}")
            lines.append("")
            lines.append(f"**Rationale**: {claim.rationale}")
            if claim.downgraded_reason:
                lines.append(f"**Guardrail Override**: {claim.downgraded_reason}")
            if claim.supporting_urls:
                lines.append("**Supporting Sources**: " + ", ".join(claim.supporting_urls))
            if claim.contradicting_urls:
                lines.append("**Contradicting Sources**: " + ", ".join(claim.contradicting_urls))
            lines.append("")

    return "\n".join(lines)


class FactCheckService:
    """Extracts factual claims, maps them to evidence, and guards against unverified claims."""

    def __init__(
        self,
        *,
        app_settings: Settings,
        project_repo: ProjectRepository,
        research_repo: ResearchRepository,
        fact_check_repo: FactCheckRepository,
        artifact_service: ArtifactService,
        model_router: ModelRouter,
        approval_service: ApprovalService | None = None,
        agent_run_repo: AgentRunRepository | None = None,
    ) -> None:
        self._settings = app_settings
        self._project_repo = project_repo
        self._research_repo = research_repo
        self._fact_check_repo = fact_check_repo
        self._artifact_service = artifact_service
        self._model_router = model_router
        self._approval_service = approval_service
        self._agent_run_repo = agent_run_repo

    async def _require_project(self, project_id: str) -> Project:
        project = await self._project_repo.get_by_id(project_id)
        if project is None:
            raise ProjectNotFoundError(f"Project '{project_id}' not found.")
        return project

    async def run_fact_check(
        self,
        project_id: str,
        *,
        custom_claims: list[str] | None = None,
        request_research_approval: bool = True,
        run_id: str | None = None,
    ) -> FactCheckReport:
        project = await self._require_project(project_id)
        start_ts = time.perf_counter()

        agent_run = None
        if self._agent_run_repo is not None:
            agent_run = await self._agent_run_repo.create(
                project_id=project_id,
                run_id=run_id,
                agent_name="fact_checker",
                stage="research",
                status=AgentRunStatus.RUNNING,
                input_summary_json={"custom_claims_count": len(custom_claims or [])},
            )

        try:
            report = await self._execute_fact_check(
                project=project,
                custom_claims=custom_claims or [],
                request_research_approval=request_research_approval,
                run_id=run_id,
            )
            if agent_run is not None and self._agent_run_repo is not None:
                await self._agent_run_repo.mark_finished(
                    agent_run,
                    status=AgentRunStatus.COMPLETED,
                    output_summary_json={
                        "total_claims": report.total_claims,
                        "verified": report.verified_count,
                        "unsupported": report.unsupported_count,
                        "conflicting": report.conflicting_count,
                        "uncertain": report.uncertain_count,
                        "downgraded": report.downgraded_claims_count,
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

    async def _load_source_texts(
        self,
        project_id: str,
        sources: list[Source],
    ) -> list[tuple[Source, str]]:
        docs = await self._research_repo.list_documents(project_id)
        doc_by_source = {doc.source_id: doc for doc in docs}
        pairs: list[tuple[Source, str]] = []

        for src in sources:
            doc = doc_by_source.get(src.id)
            text = ""
            if doc is not None and doc.artifact_id is not None:
                try:
                    _art, full_text = await self._artifact_service.read_artifact_text(
                        project_id, doc.artifact_id
                    )
                    text = full_text
                except (LookupError, FileNotFoundError, UnicodeDecodeError):
                    text = doc.excerpt or ""
            elif doc is not None and doc.excerpt:
                text = doc.excerpt
            elif src.snippet:
                text = src.snippet
            if text.strip():
                pairs.append((src, text.strip()))
        return pairs

    async def _execute_fact_check(
        self,
        *,
        project: Project,
        custom_claims: list[str],
        request_research_approval: bool,
        run_id: str | None,
    ) -> FactCheckReport:
        extracted_sources = list(
            await self._research_repo.list_sources(project.id, status=SourceStatus.EXTRACTED)
        )
        findings = list(await self._research_repo.list_findings(project.id))
        source_texts = await self._load_source_texts(project.id, extracted_sources)

        if not source_texts and not findings and not custom_claims:
            return FactCheckReport(
                project_id=project.id,
                topic=project.topic,
                overall_assessment=(
                    "No extracted sources or research findings are available to fact-check yet."
                ),
            )

        # Build prompt context
        findings_lines: list[str] = []
        for idx, finding in enumerate(findings, start=1):
            findings_lines.append(
                f"{idx}. [{finding.category}] {finding.title}: {finding.summary} "
                f"(cited: {', '.join(finding.source_urls_json)})"
            )
        for claim_text in custom_claims:
            cleaned = claim_text.strip()
            if cleaned:
                findings_lines.append(f"- [custom_claim] {cleaned}")

        source_blocks: list[str] = []
        for idx, (src, text) in enumerate(source_texts, start=1):
            source_blocks.append(
                f'<untrusted_source id="{idx}" url="{src.normalized_url}" title="{src.title}">\n'
                f"{text[:_MAX_SOURCE_TEXT_IN_PROMPT]}\n"
                "</untrusted_source>"
            )

        system_prompt = _load_prompt(self._settings.BASE_DIR, "prompts/fact_checker/system.md")
        user_template = _load_prompt(self._settings.BASE_DIR, "prompts/fact_checker/user.md")
        user_prompt = user_template.format(
            topic=project.topic,
            findings_block="\n".join(findings_lines) or "(No findings yet — inspect sources)",
            sources_block="\n\n".join(source_blocks) or "(No extracted source texts available)",
        )

        llm_result = await self._model_router.generate_structured(
            task=TaskType.FACT_CHECK,
            messages=[
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=user_prompt),
            ],
            response_model=FactCheckLLMOutput,
            project_id=project.id,
            run_id=run_id,
            node_name="fact_checker",
        )
        raw_output = llm_result.data

        source_lookup: dict[str, Source] = {}
        for src in extracted_sources:
            source_lookup[src.normalized_url] = src
            source_lookup[src.url] = src

        claim_summaries: list[VerifiedClaimSummary] = []
        warnings = list(raw_output.high_risk_warnings)
        counts = {
            ClaimVerdict.VERIFIED: 0,
            ClaimVerdict.UNSUPPORTED: 0,
            ClaimVerdict.CONFLICTING: 0,
            ClaimVerdict.UNCERTAIN: 0,
        }
        downgraded_count = 0

        for item in raw_output.claims:
            valid_links: list[tuple[Source, EvidenceStance, str | None]] = []
            seen_source_ids: set[str] = set()

            for ref in item.evidence:
                matched = source_lookup.get(ref.source_url.strip())
                if matched is None:
                    try:
                        matched = source_lookup.get(normalize_url(ref.source_url))
                    except ValueError:
                        matched = None
                if matched is not None and matched.id not in seen_source_ids:
                    seen_source_ids.add(matched.id)
                    valid_links.append((matched, ref.stance, ref.excerpt))

            supporting_urls = [
                s.normalized_url
                for s, stance, _ in valid_links
                if stance == EvidenceStance.SUPPORTS
            ]
            contradicting_urls = [
                s.normalized_url
                for s, stance, _ in valid_links
                if stance == EvidenceStance.CONTRADICTS
            ]

            verdict = item.verdict
            risk_level = item.risk_level
            downgraded_reason: str | None = None

            # Hard guardrail: never allow VERIFIED without at least one real supporting source
            if verdict == ClaimVerdict.VERIFIED and not supporting_urls:
                verdict = ClaimVerdict.UNSUPPORTED
                risk_level = RiskLevel.HIGH
                downgraded_count += 1
                downgraded_reason = (
                    "Downgraded from VERIFIED to UNSUPPORTED: no valid supporting source URL "
                    "matched project evidence."
                )
                warnings.append(f"Unsupported claim flagged: {item.statement}")

            # If both supporting and contradicting evidence exist, mark CONFLICTING
            if supporting_urls and contradicting_urls and verdict != ClaimVerdict.CONFLICTING:
                verdict = ClaimVerdict.CONFLICTING
                risk_level = RiskLevel.HIGH

            counts[verdict] += 1

            claim_row = await self._fact_check_repo.create_claim(
                project_id=project.id,
                run_id=run_id,
                statement=item.statement,
                verdict=verdict,
                confidence=item.confidence,
                risk_level=risk_level,
                rationale=item.rationale,
                evidence_summary=downgraded_reason,
            )
            for src, stance, excerpt in valid_links:
                await self._fact_check_repo.link_claim_source(
                    claim_id=claim_row.id,
                    source_id=src.id,
                    stance=stance,
                    excerpt=excerpt,
                )

            claim_summaries.append(
                VerifiedClaimSummary(
                    claim_id=claim_row.id,
                    statement=item.statement,
                    verdict=verdict,
                    confidence=item.confidence,
                    risk_level=risk_level,
                    rationale=item.rationale,
                    supporting_urls=supporting_urls,
                    contradicting_urls=contradicting_urls,
                    downgraded_reason=downgraded_reason,
                )
            )

        report = FactCheckReport(
            project_id=project.id,
            topic=project.topic,
            overall_assessment=raw_output.overall_assessment,
            total_claims=len(claim_summaries),
            verified_count=counts[ClaimVerdict.VERIFIED],
            unsupported_count=counts[ClaimVerdict.UNSUPPORTED],
            conflicting_count=counts[ClaimVerdict.CONFLICTING],
            uncertain_count=counts[ClaimVerdict.UNCERTAIN],
            downgraded_claims_count=downgraded_count,
            high_risk_warnings=warnings,
            claims=claim_summaries,
        )

        json_art = await self._artifact_service.save_json(
            project_id=project.id,
            stage="research",
            artifact_type=ArtifactType.FACT_CHECK_REPORT,
            name="fact_check_report.json",
            relative_path=Path("01_research") / "fact_check" / "fact_check_report.json",
            payload=report,
            run_id=run_id,
            metadata_json={
                "total_claims": report.total_claims,
                "unsupported_count": report.unsupported_count,
            },
        )
        md_art = await self._artifact_service.save_text(
            project_id=project.id,
            stage="research",
            artifact_type=ArtifactType.FACT_CHECK_REPORT,
            name="fact_check_report.md",
            relative_path=Path("01_research") / "fact_check" / "fact_check_report.md",
            content=_render_fact_check_markdown(report),
            run_id=run_id,
            metadata_json={"format": "markdown"},
            supersede_previous_drafts=False,
        )
        report.report_json_artifact_id = json_art.id
        report.report_markdown_artifact_id = md_art.id

        if request_research_approval and self._approval_service is not None:
            approval = await self._approval_service.request_approval(
                project_id=project.id,
                gate=ApprovalGate.RESEARCH,
                run_id=run_id,
                artifact_id=md_art.id,
                comments=(
                    f"Fact-check finished: {report.verified_count} verified, "
                    f"{report.unsupported_count} unsupported, "
                    f"{report.conflicting_count} conflicting."
                ),
            )
            report.approval_id = approval.id

        return report

    async def list_claims(
        self,
        project_id: str,
        *,
        verdict: ClaimVerdict | str | None = None,
    ) -> list[Claim]:
        await self._require_project(project_id)
        return list(await self._fact_check_repo.list_claims(project_id, verdict=verdict))
