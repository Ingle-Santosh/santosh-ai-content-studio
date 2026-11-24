import logging
import time
from pathlib import Path

from content_studio.config.settings import Settings
from content_studio.contracts.competitor import (
    CompetitorGapLLMOutput,
    CompetitorReport,
    CompetitorVideoSummary,
)
from content_studio.database.models.competitor_video import CompetitorVideo
from content_studio.database.models.enums import AgentRunStatus, ArtifactType
from content_studio.database.models.project import Project
from content_studio.database.repositories import (
    AgentRunRepository,
    CompetitorRepository,
    ProjectRepository,
)
from content_studio.providers.llm import LLMMessage, ModelRouter, TaskType
from content_studio.providers.youtube import (
    BaseYouTubeProvider,
    YouTubeProviderError,
    YouTubeVideoMetadata,
)
from content_studio.services.artifact_service import ArtifactService, ProjectNotFoundError

logger = logging.getLogger(__name__)


def _load_prompt(base_dir: Path, relative_path: str) -> str:
    return (base_dir / relative_path).read_text(encoding="utf-8").strip()


def _render_competitor_markdown(report: CompetitorReport) -> str:
    lines: list[str] = [
        f"# Competitor Analysis Report: {report.topic}",
        "",
        f"- **Project ID**: `{report.project_id}`",
        f"- **Generated At**: {report.generated_at.isoformat()}",
        (
            f"- **Videos Analyzed**: {report.videos_analyzed} "
            f"({report.duplicates_skipped} duplicates skipped)"
        ),
        "",
    ]

    if report.gap_analysis is not None:
        lines.extend(
            [
                "## Executive Summary",
                "",
                report.gap_analysis.summary,
                "",
                "## Recommended Positioning",
                "",
                report.gap_analysis.recommended_positioning,
                "",
            ]
        )
        if report.gap_analysis.content_gaps:
            lines.append("## Content Gaps")
            lines.append("")
            for gap in report.gap_analysis.content_gaps:
                lines.append(f"- {gap}")
            lines.append("")

        if report.gap_analysis.differentiation_opportunities:
            lines.append("## Differentiation Opportunities")
            lines.append("")
            for opp in report.gap_analysis.differentiation_opportunities:
                lines.append(f"- {opp}")
            lines.append("")

    lines.append("## Competitor Videos")
    lines.append("")
    for video in report.videos:
        views_txt = f"{video.view_count:,} views" if video.view_count is not None else "views n/a"
        dur_txt = (
            f"{video.duration_seconds // 60}m {video.duration_seconds % 60}s"
            if video.duration_seconds is not None
            else "duration n/a"
        )
        lines.append(
            f"- [{video.title}]({video.url}) — **{video.channel_name or 'Unknown channel'}** "
            f"({views_txt}, {dur_txt}, provider: `{video.provider}`)"
        )
    lines.append("")
    return "\n".join(lines)


class CompetitorService:
    """Collects public YouTube competitor metadata and generates content-gap reports."""

    def __init__(
        self,
        *,
        app_settings: Settings,
        project_repo: ProjectRepository,
        competitor_repo: CompetitorRepository,
        artifact_service: ArtifactService,
        youtube_provider: BaseYouTubeProvider,
        model_router: ModelRouter,
        agent_run_repo: AgentRunRepository | None = None,
    ) -> None:
        self._settings = app_settings
        self._project_repo = project_repo
        self._competitor_repo = competitor_repo
        self._artifact_service = artifact_service
        self._youtube_provider = youtube_provider
        self._model_router = model_router
        self._agent_run_repo = agent_run_repo

    async def _require_project(self, project_id: str) -> Project:
        project = await self._project_repo.get_by_id(project_id)
        if project is None:
            raise ProjectNotFoundError(f"Project '{project_id}' not found.")
        return project

    async def run_analysis(
        self,
        project_id: str,
        *,
        queries: list[str] | None = None,
        video_urls: list[str] | None = None,
        max_results: int | None = None,
        analyze_with_llm: bool = True,
        run_id: str | None = None,
    ) -> CompetitorReport:
        project = await self._require_project(project_id)
        effective_queries = (
            [q.strip() for q in queries if q.strip()] if queries else [project.topic]
        )
        effective_urls = [u.strip() for u in (video_urls or []) if u.strip()]
        limit = max_results or self._settings.YOUTUBE_MAX_COMPETITORS
        start_ts = time.perf_counter()

        agent_run = None
        if self._agent_run_repo is not None:
            agent_run = await self._agent_run_repo.create(
                project_id=project_id,
                run_id=run_id,
                agent_name="competitor_analyst",
                stage="research",
                status=AgentRunStatus.RUNNING,
                input_summary_json={
                    "queries": effective_queries,
                    "video_urls": effective_urls,
                    "max_results": limit,
                },
            )

        try:
            report = await self._execute_analysis(
                project=project,
                queries=effective_queries,
                video_urls=effective_urls,
                max_results=limit,
                analyze_with_llm=analyze_with_llm,
                run_id=run_id,
            )
            if agent_run is not None and self._agent_run_repo is not None:
                await self._agent_run_repo.mark_finished(
                    agent_run,
                    status=AgentRunStatus.COMPLETED,
                    output_summary_json={
                        "videos_analyzed": report.videos_analyzed,
                        "duplicates_skipped": report.duplicates_skipped,
                        "content_gaps_count": len(report.gap_analysis.content_gaps)
                        if report.gap_analysis
                        else 0,
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

    async def _execute_analysis(
        self,
        *,
        project: Project,
        queries: list[str],
        video_urls: list[str],
        max_results: int,
        analyze_with_llm: bool,
        run_id: str | None,
    ) -> CompetitorReport:
        discovered: list[YouTubeVideoMetadata] = []

        for url in video_urls:
            try:
                meta = await self._youtube_provider.fetch_video_by_url(url)
                if meta is not None:
                    discovered.append(meta)
            except YouTubeProviderError as exc:
                logger.warning("Failed to fetch YouTube URL %s: %s", url, exc)

        for query in queries:
            try:
                items = await self._youtube_provider.search_videos(query, max_results=max_results)
                discovered.extend(items)
            except YouTubeProviderError as exc:
                logger.warning("YouTube search failed for %r: %s", query, exc)

        # Persist unique videos per project
        duplicates_skipped = 0
        seen_ids: set[str] = set()
        for meta in discovered:
            if meta.youtube_video_id in seen_ids:
                duplicates_skipped += 1
                continue
            seen_ids.add(meta.youtube_video_id)

            existing = await self._competitor_repo.get_by_youtube_id(
                project.id, meta.youtube_video_id
            )
            if existing is not None:
                duplicates_skipped += 1
                continue

            await self._competitor_repo.create(
                project_id=project.id,
                youtube_video_id=meta.youtube_video_id,
                url=meta.url,
                title=meta.title,
                channel_name=meta.channel_name,
                published_at=meta.published_at,
                duration_seconds=meta.duration_seconds,
                view_count=meta.view_count,
                like_count=meta.like_count,
                comment_count=meta.comment_count,
                description=meta.description,
                provider=meta.provider,
            )

        all_videos = list(await self._competitor_repo.list_for_project(project.id))
        gap_analysis: CompetitorGapLLMOutput | None = None

        if analyze_with_llm and all_videos:
            gap_analysis = await self._synthesize_gaps(
                project=project,
                videos=all_videos,
                run_id=run_id,
            )
            topic_map = {
                entry.youtube_video_id: entry.topics_covered for entry in gap_analysis.video_topics
            }
            for video in all_videos:
                mapped = topic_map.get(video.youtube_video_id)
                if mapped:
                    await self._competitor_repo.update_topics(video, mapped)

        summaries = [
            CompetitorVideoSummary(
                id=v.id,
                youtube_video_id=v.youtube_video_id,
                url=v.url,
                title=v.title,
                channel_name=v.channel_name,
                published_at=v.published_at,
                duration_seconds=v.duration_seconds,
                view_count=v.view_count,
                like_count=v.like_count,
                comment_count=v.comment_count,
                topics_covered=list(v.topics_covered_json or []),
                provider=v.provider,
            )
            for v in all_videos
        ]

        report = CompetitorReport(
            project_id=project.id,
            topic=project.topic,
            queries_executed=queries,
            videos_analyzed=len(summaries),
            duplicates_skipped=duplicates_skipped,
            videos=summaries,
            gap_analysis=gap_analysis,
        )

        json_art = await self._artifact_service.save_json(
            project_id=project.id,
            stage="research",
            artifact_type=ArtifactType.COMPETITOR_REPORT,
            name="competitor_report.json",
            relative_path=Path("01_research") / "competitors" / "competitor_report.json",
            payload=report,
            run_id=run_id,
            metadata_json={"videos_analyzed": report.videos_analyzed},
        )
        md_art = await self._artifact_service.save_text(
            project_id=project.id,
            stage="research",
            artifact_type=ArtifactType.COMPETITOR_REPORT,
            name="competitor_report.md",
            relative_path=Path("01_research") / "competitors" / "competitor_report.md",
            content=_render_competitor_markdown(report),
            run_id=run_id,
            metadata_json={"format": "markdown"},
            supersede_previous_drafts=False,
        )
        report.report_json_artifact_id = json_art.id
        report.report_markdown_artifact_id = md_art.id
        return report

    async def _synthesize_gaps(
        self,
        *,
        project: Project,
        videos: list[CompetitorVideo],
        run_id: str | None,
    ) -> CompetitorGapLLMOutput:
        system_prompt = _load_prompt(
            self._settings.BASE_DIR, "prompts/competitor_analyst/system.md"
        )
        user_template = _load_prompt(self._settings.BASE_DIR, "prompts/competitor_analyst/user.md")

        blocks: list[str] = []
        for idx, video in enumerate(videos, start=1):
            desc_excerpt = (video.description or "")[:600]
            blocks.append(
                f"{idx}. youtube_video_id={video.youtube_video_id} | title={video.title} | "
                f"channel={video.channel_name or 'Unknown'} | "
                f"published_at={video.published_at or 'unknown'} | "
                f"duration_seconds={video.duration_seconds} | "
                f"view_count={video.view_count}\n"
                f"   description: {desc_excerpt}"
            )

        user_prompt = user_template.format(
            topic=project.topic,
            audience_level=project.config.get("audience_level", "Intermediate"),
            language=project.config.get("language", "Hinglish"),
            videos_block="\n".join(blocks),
        )

        result = await self._model_router.generate_structured(
            task=TaskType.RESEARCH_SYNTHESIS,
            messages=[
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=user_prompt),
            ],
            response_model=CompetitorGapLLMOutput,
            project_id=project.id,
            run_id=run_id,
            node_name="competitor_analyst",
        )
        return result.data

    async def list_competitors(self, project_id: str) -> list[CompetitorVideo]:
        await self._require_project(project_id)
        return list(await self._competitor_repo.list_for_project(project_id))
