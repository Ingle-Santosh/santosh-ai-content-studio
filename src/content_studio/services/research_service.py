import asyncio
import logging
import time
from pathlib import Path

from content_studio.config.settings import Settings
from content_studio.contracts.research import (
    ResearchFindingItem,
    ResearchReport,
    ResearchSynthesisOutput,
    SourceSummary,
)
from content_studio.database.models.enums import (
    AgentRunStatus,
    ArtifactType,
    SourceStatus,
)
from content_studio.database.models.project import Project
from content_studio.database.models.source import Source
from content_studio.database.repositories import (
    AgentRunRepository,
    ProjectRepository,
    ResearchRepository,
)
from content_studio.providers.llm import LLMMessage, ModelRouter, TaskType
from content_studio.providers.search import (
    BaseSearchProvider,
    SearchProviderError,
    SearchResult,
)
from content_studio.services.artifact_service import ArtifactService, ProjectNotFoundError
from content_studio.services.web_extractor import (
    ExtractedPage,
    WebExtractor,
    compute_url_hash,
    extract_domain,
    normalize_url,
)

logger = logging.getLogger(__name__)

_MAX_CHARS_PER_SOURCE_IN_PROMPT = 3500
_MAX_EXCERPT_CHARS = 600


def _load_prompt_template(base_dir: Path, relative_path: str) -> str:
    prompt_path = base_dir / relative_path
    return prompt_path.read_text(encoding="utf-8").strip()


def _render_report_markdown(report: ResearchReport) -> str:
    lines: list[str] = [
        f"# Research Report: {report.topic}",
        "",
        f"- **Project ID**: `{report.project_id}`",
        f"- **Generated At**: {report.generated_at.isoformat()}",
        f"- **Queries Executed**: {', '.join(report.queries_executed) or 'None'}",
        (
            f"- **Sources**: {report.sources_discovered} discovered | "
            f"{report.sources_extracted} extracted | {report.sources_failed} failed | "
            f"{report.duplicates_skipped} duplicates skipped"
        ),
        "",
    ]

    if report.synthesis is not None:
        lines.extend(
            [
                "## Executive Summary",
                "",
                report.synthesis.executive_summary,
                "",
            ]
        )
        if report.synthesis.key_definitions:
            lines.append("## Key Definitions")
            lines.append("")
            for item in report.synthesis.key_definitions:
                lines.append(f"- {item}")
            lines.append("")

        if report.synthesis.findings:
            lines.append("## Grounded Research Findings")
            lines.append("")
            for idx, finding in enumerate(report.synthesis.findings, start=1):
                badge = " [CONTRADICTION]" if finding.is_contradiction else ""
                lines.append(
                    f"### {idx}. {finding.title} (`{finding.category.value}`, "
                    f"confidence {finding.confidence:.2f}){badge}"
                )
                lines.append("")
                lines.append(finding.summary)
                lines.append("")
                lines.append("Sources:")
                for url in finding.source_urls:
                    lines.append(f"- {url}")
                lines.append("")

        if report.synthesis.contradictions:
            lines.append("## Contradictions & Caveats")
            lines.append("")
            for item in report.synthesis.contradictions:
                lines.append(f"- {item}")
            lines.append("")

        if report.synthesis.recommended_angles:
            lines.append("## Recommended Video Angles")
            lines.append("")
            for item in report.synthesis.recommended_angles:
                lines.append(f"- {item}")
            lines.append("")

        if report.synthesis.open_questions:
            lines.append("## Open Questions")
            lines.append("")
            for item in report.synthesis.open_questions:
                lines.append(f"- {item}")
            lines.append("")

    lines.append("## Source Index")
    lines.append("")
    for src in report.source_index:
        err_suffix = f" — Error: {src.error_message}" if src.error_message else ""
        label = src.title or src.url
        lines.append(f"- [{label}]({src.url}) (`{src.status}`, {src.word_count} words){err_suffix}")
    lines.append("")
    return "\n".join(lines)


class ResearchService:
    """Orchestrates web discovery, deduplication, extraction, and grounded synthesis."""

    def __init__(
        self,
        *,
        app_settings: Settings,
        project_repo: ProjectRepository,
        research_repo: ResearchRepository,
        artifact_service: ArtifactService,
        search_provider: BaseSearchProvider,
        extractor: WebExtractor,
        model_router: ModelRouter,
        agent_run_repo: AgentRunRepository | None = None,
    ) -> None:
        self._settings = app_settings
        self._project_repo = project_repo
        self._research_repo = research_repo
        self._artifact_service = artifact_service
        self._search_provider = search_provider
        self._extractor = extractor
        self._model_router = model_router
        self._agent_run_repo = agent_run_repo

    async def _require_project(self, project_id: str) -> Project:
        project = await self._project_repo.get_by_id(project_id)
        if project is None:
            raise ProjectNotFoundError(f"Project '{project_id}' not found.")
        return project

    def _default_queries(self, topic: str) -> list[str]:
        cleaned = topic.strip()
        return [
            f"{cleaned} architecture concepts explained",
            f"{cleaned} practical tutorial examples best practices",
        ]

    async def _discover_candidates(
        self,
        *,
        queries: list[str],
        seed_urls: list[str],
        max_results_per_query: int,
    ) -> tuple[list[SearchResult], list[str]]:
        candidates: list[SearchResult] = []
        search_errors: list[str] = []

        for url in seed_urls:
            cleaned = url.strip()
            if cleaned:
                candidates.append(
                    SearchResult(title=cleaned, url=cleaned, snippet="", provider="manual")
                )

        for query in queries:
            try:
                found = await self._search_provider.search(query, max_results=max_results_per_query)
                candidates.extend(found)
            except SearchProviderError as exc:
                logger.warning("Search query failed (%r): %s", query, exc)
                search_errors.append(str(exc))

        return candidates, search_errors

    async def run_research(
        self,
        project_id: str,
        *,
        queries: list[str] | None = None,
        seed_urls: list[str] | None = None,
        max_results_per_query: int | None = None,
        synthesize_with_llm: bool = True,
        run_id: str | None = None,
    ) -> ResearchReport:
        project = await self._require_project(project_id)
        effective_queries = (
            [q.strip() for q in queries if q.strip()]
            if queries
            else self._default_queries(project.topic)
        )
        effective_seeds = [u.strip() for u in (seed_urls or []) if u.strip()]
        per_query_limit = max_results_per_query or self._settings.RESEARCH_MAX_RESULTS_PER_QUERY

        start_ts = time.perf_counter()
        agent_run = None
        if self._agent_run_repo is not None:
            agent_run = await self._agent_run_repo.create(
                project_id=project_id,
                run_id=run_id,
                agent_name="research_agent",
                stage="research",
                status=AgentRunStatus.RUNNING,
                input_summary_json={
                    "queries": effective_queries,
                    "seed_urls": effective_seeds,
                    "max_results_per_query": per_query_limit,
                },
            )

        try:
            report = await self._execute_pipeline(
                project=project,
                queries=effective_queries,
                seed_urls=effective_seeds,
                max_results_per_query=per_query_limit,
                synthesize_with_llm=synthesize_with_llm,
                run_id=run_id,
            )
            if agent_run is not None and self._agent_run_repo is not None:
                await self._agent_run_repo.mark_finished(
                    agent_run,
                    status=AgentRunStatus.COMPLETED,
                    output_summary_json={
                        "sources_discovered": report.sources_discovered,
                        "sources_extracted": report.sources_extracted,
                        "sources_failed": report.sources_failed,
                        "duplicates_skipped": report.duplicates_skipped,
                        "findings_count": len(report.synthesis.findings) if report.synthesis else 0,
                    },
                    duration_ms=int((time.perf_counter() - start_ts) * 1000),
                )
            return report
        except Exception as exc:
            if agent_run is not None and self._agent_run_repo is not None:
                await self._agent_run_repo.mark_finished(
                    agent_run,
                    status=AgentRunStatus.FAILED,
                    error_message=str(exc),
                    duration_ms=int((time.perf_counter() - start_ts) * 1000),
                )
            raise

    async def _execute_pipeline(
        self,
        *,
        project: Project,
        queries: list[str],
        seed_urls: list[str],
        max_results_per_query: int,
        synthesize_with_llm: bool,
        run_id: str | None,
    ) -> ResearchReport:
        candidates, _search_errors = await self._discover_candidates(
            queries=queries,
            seed_urls=seed_urls,
            max_results_per_query=max_results_per_query,
        )

        # 1. URL-level deduplication (within batch & against existing DB sources)
        new_sources: list[Source] = []
        seen_hashes: set[str] = set()
        duplicates_skipped = 0

        for cand in candidates:
            try:
                norm_url = normalize_url(cand.url)
            except ValueError:
                continue
            url_hash = compute_url_hash(norm_url)
            if url_hash in seen_hashes:
                duplicates_skipped += 1
                continue
            seen_hashes.add(url_hash)

            existing = await self._research_repo.get_source_by_url_hash(project.id, url_hash)
            if existing is not None:
                duplicates_skipped += 1
                continue

            source = await self._research_repo.create_source(
                project_id=project.id,
                url=cand.url,
                normalized_url=norm_url,
                url_hash=url_hash,
                title=cand.title or norm_url,
                domain=extract_domain(norm_url),
                provider=cand.provider,
                snippet=cand.snippet or None,
                status=SourceStatus.DISCOVERED,
            )
            new_sources.append(source)

        # 2. Bounded concurrent fetching & extraction
        semaphore = asyncio.Semaphore(4)

        async def _fetch_one(src: Source) -> tuple[Source, ExtractedPage]:
            async with semaphore:
                page = await self._extractor.fetch_and_extract(src.url)
                return src, page

        fetched_pairs = await asyncio.gather(*(_fetch_one(src) for src in new_sources))

        extracted_texts: list[tuple[Source, str]] = []
        source_summaries: list[SourceSummary] = []
        sources_extracted = 0
        sources_failed = 0

        for src, page in fetched_pairs:
            if not page.succeeded:
                sources_failed += 1
                updated = await self._research_repo.update_source(
                    src,
                    status=SourceStatus.FAILED,
                    http_status=page.http_status,
                    error_message=page.error or "Extraction failed",
                )
                await self._research_repo.create_document(
                    project_id=project.id,
                    source_id=updated.id,
                    title=page.title or updated.title,
                    word_count=0,
                    extraction_method=page.extraction_method,
                    extraction_error=page.error or "Extraction failed",
                )
                source_summaries.append(
                    SourceSummary(
                        source_id=updated.id,
                        url=updated.url,
                        normalized_url=updated.normalized_url,
                        title=updated.title,
                        domain=updated.domain,
                        provider=updated.provider,
                        status=updated.status,
                        word_count=0,
                        error_message=updated.error_message,
                    )
                )
                continue

            # Content-level deduplication across mirrors/redirects
            if page.checksum_sha256:
                dup_doc = await self._research_repo.get_document_by_checksum(
                    project.id, page.checksum_sha256
                )
                if dup_doc is not None:
                    duplicates_skipped += 1
                    updated = await self._research_repo.update_source(
                        src,
                        status=SourceStatus.DUPLICATE,
                        title=page.title or src.title,
                        http_status=page.http_status,
                        error_message="Duplicate content checksum already captured.",
                    )
                    source_summaries.append(
                        SourceSummary(
                            source_id=updated.id,
                            url=updated.url,
                            normalized_url=updated.normalized_url,
                            title=updated.title,
                            domain=updated.domain,
                            provider=updated.provider,
                            status=updated.status,
                            word_count=page.word_count,
                            error_message=updated.error_message,
                        )
                    )
                    continue

            # Persist full extracted text outside DB in 01_research/sources/
            artifact = await self._artifact_service.save_text(
                project_id=project.id,
                stage="research",
                artifact_type=ArtifactType.OTHER,
                name=f"source_{src.url_hash[:12]}.txt",
                relative_path=Path("01_research") / "sources" / f"{src.url_hash[:16]}.txt",
                content=page.text,
                run_id=run_id,
                metadata_json={"source_id": src.id, "url": src.normalized_url},
                supersede_previous_drafts=False,
            )

            updated = await self._research_repo.update_source(
                src,
                status=SourceStatus.EXTRACTED,
                title=page.title or src.title,
                http_status=page.http_status,
            )
            await self._research_repo.create_document(
                project_id=project.id,
                source_id=updated.id,
                artifact_id=artifact.id,
                title=page.title or updated.title,
                author=page.author,
                published_date=page.published_date,
                language=page.language,
                word_count=page.word_count,
                content_checksum_sha256=page.checksum_sha256,
                excerpt=page.text[:_MAX_EXCERPT_CHARS],
                extraction_method=page.extraction_method,
            )
            sources_extracted += 1
            extracted_texts.append((updated, page.text))
            source_summaries.append(
                SourceSummary(
                    source_id=updated.id,
                    url=updated.url,
                    normalized_url=updated.normalized_url,
                    title=updated.title,
                    domain=updated.domain,
                    provider=updated.provider,
                    status=updated.status,
                    word_count=page.word_count,
                )
            )

        # 3. Synthesize findings with strict source-URL grounding
        synthesis: ResearchSynthesisOutput | None = None
        ungrounded_dropped = 0

        if synthesize_with_llm and extracted_texts:
            raw_synthesis = await self._synthesize_sources(
                project=project,
                extracted_texts=extracted_texts,
                run_id=run_id,
            )
            grounded_findings, ungrounded_dropped = self._enforce_source_traceability(
                raw_synthesis.findings,
                extracted_texts,
            )
            synthesis = raw_synthesis.model_copy(update={"findings": grounded_findings})

            url_to_source = self._build_source_lookup(extracted_texts)
            for item in grounded_findings:
                primary_source = url_to_source.get(item.source_urls[0])
                await self._research_repo.create_finding(
                    project_id=project.id,
                    source_id=primary_source.id if primary_source else None,
                    run_id=run_id,
                    category=item.category,
                    title=item.title,
                    summary=item.summary,
                    source_urls=item.source_urls,
                    confidence=item.confidence,
                    is_contradiction=item.is_contradiction,
                )

        report = ResearchReport(
            project_id=project.id,
            topic=project.topic,
            queries_executed=queries,
            sources_discovered=len(new_sources),
            sources_extracted=sources_extracted,
            sources_failed=sources_failed,
            duplicates_skipped=duplicates_skipped,
            ungrounded_findings_dropped=ungrounded_dropped,
            synthesis=synthesis,
            source_index=source_summaries,
        )

        # 4. Save report artifacts (Markdown & JSON) via ArtifactService
        json_artifact = await self._artifact_service.save_json(
            project_id=project.id,
            stage="research",
            artifact_type=ArtifactType.RESEARCH_BRIEF,
            name="research_report.json",
            payload=report,
            run_id=run_id,
            metadata_json={"format": "json", "sources_extracted": sources_extracted},
        )
        md_artifact = await self._artifact_service.save_text(
            project_id=project.id,
            stage="research",
            artifact_type=ArtifactType.RESEARCH_BRIEF,
            name="research_report.md",
            content=_render_report_markdown(report),
            run_id=run_id,
            metadata_json={"format": "markdown", "sources_extracted": sources_extracted},
            supersede_previous_drafts=False,
        )
        report.report_json_artifact_id = json_artifact.id
        report.report_markdown_artifact_id = md_artifact.id
        return report

    async def _synthesize_sources(
        self,
        *,
        project: Project,
        extracted_texts: list[tuple[Source, str]],
        run_id: str | None,
    ) -> ResearchSynthesisOutput:
        system_prompt = _load_prompt_template(self._settings.BASE_DIR, "prompts/research/system.md")
        user_template = _load_prompt_template(self._settings.BASE_DIR, "prompts/research/user.md")

        source_blocks: list[str] = []
        for idx, (src, text) in enumerate(extracted_texts, start=1):
            clipped = text[:_MAX_CHARS_PER_SOURCE_IN_PROMPT]
            source_blocks.append(
                f'<untrusted_source id="{idx}" url="{src.normalized_url}" title="{src.title}">\n'
                f"{clipped}\n"
                "</untrusted_source>"
            )

        user_prompt = user_template.format(
            topic=project.topic,
            audience_level=project.config.get("audience_level", "Intermediate"),
            language=project.config.get("language", "Hinglish"),
            sources_block="\n\n".join(source_blocks),
        )

        result = await self._model_router.generate_structured(
            task=TaskType.RESEARCH_SYNTHESIS,
            messages=[
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=user_prompt),
            ],
            response_model=ResearchSynthesisOutput,
            project_id=project.id,
            run_id=run_id,
            node_name="research_agent",
        )
        return result.data

    @staticmethod
    def _build_source_lookup(extracted_texts: list[tuple[Source, str]]) -> dict[str, Source]:
        lookup: dict[str, Source] = {}
        for src, _text in extracted_texts:
            lookup[src.normalized_url] = src
            lookup[src.url] = src
        return lookup

    def _enforce_source_traceability(
        self,
        findings: list[ResearchFindingItem],
        extracted_texts: list[tuple[Source, str]],
    ) -> tuple[list[ResearchFindingItem], int]:
        """Strip fabricated URLs and drop findings that lack any real fetched source."""
        lookup = self._build_source_lookup(extracted_texts)
        grounded: list[ResearchFindingItem] = []
        dropped = 0

        for item in findings:
            valid_urls: list[str] = []
            seen: set[str] = set()
            for raw_url in item.source_urls:
                matched = lookup.get(raw_url.strip())
                if matched is None:
                    try:
                        matched = lookup.get(normalize_url(raw_url))
                    except ValueError:
                        matched = None
                if matched is not None and matched.normalized_url not in seen:
                    seen.add(matched.normalized_url)
                    valid_urls.append(matched.normalized_url)

            if not valid_urls:
                dropped += 1
                continue

            grounded.append(item.model_copy(update={"source_urls": valid_urls}))

        return grounded, dropped

    async def list_sources(
        self,
        project_id: str,
        *,
        status: SourceStatus | str | None = None,
    ) -> list[Source]:
        await self._require_project(project_id)
        return list(await self._research_repo.list_sources(project_id, status=status))

    async def list_findings(self, project_id: str):
        await self._require_project(project_id)
        return list(await self._research_repo.list_findings(project_id))
