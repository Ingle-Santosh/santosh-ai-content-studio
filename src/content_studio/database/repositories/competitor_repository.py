from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from content_studio.database.models.competitor_video import CompetitorVideo


class CompetitorRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_youtube_id(
        self,
        project_id: str,
        youtube_video_id: str,
    ) -> CompetitorVideo | None:
        stmt = select(CompetitorVideo).where(
            CompetitorVideo.project_id == project_id,
            CompetitorVideo.youtube_video_id == youtube_video_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        project_id: str,
        youtube_video_id: str,
        url: str,
        title: str,
        channel_name: str = "",
        published_at: str | None = None,
        duration_seconds: int | None = None,
        view_count: int | None = None,
        like_count: int | None = None,
        comment_count: int | None = None,
        description: str | None = None,
        topics_covered_json: list[str] | None = None,
        provider: str = "public_search",
    ) -> CompetitorVideo:
        record = CompetitorVideo(
            project_id=project_id,
            youtube_video_id=youtube_video_id,
            url=url[:500],
            title=title[:500],
            channel_name=channel_name[:255],
            published_at=published_at[:50] if published_at else None,
            duration_seconds=duration_seconds,
            view_count=view_count,
            like_count=like_count,
            comment_count=comment_count,
            description=description,
            topics_covered_json=topics_covered_json or [],
            provider=provider,
        )
        self._session.add(record)
        await self._session.commit()
        await self._session.refresh(record)
        return record

    async def update_topics(
        self,
        video: CompetitorVideo,
        topics_covered: list[str],
    ) -> CompetitorVideo:
        video.topics_covered_json = topics_covered
        video.updated_at = datetime.now(UTC)
        await self._session.commit()
        await self._session.refresh(video)
        return video

    async def list_for_project(self, project_id: str) -> Sequence[CompetitorVideo]:
        stmt = (
            select(CompetitorVideo)
            .where(CompetitorVideo.project_id == project_id)
            .order_by(CompetitorVideo.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()
