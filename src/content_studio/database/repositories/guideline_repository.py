from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from content_studio.database.models.channel_guideline import ChannelGuideline


class ChannelGuidelineRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        slug: str,
        channel_name: str,
        guidelines_json: dict[str, Any],
        is_active: bool = True,
    ) -> ChannelGuideline:
        if is_active:
            await self._deactivate_all()
        record = ChannelGuideline(
            slug=slug,
            channel_name=channel_name,
            guidelines_json=guidelines_json,
            is_active=is_active,
        )
        self._session.add(record)
        await self._session.commit()
        await self._session.refresh(record)
        return record

    async def get_by_id(self, guideline_id: str) -> ChannelGuideline | None:
        return await self._session.get(ChannelGuideline, guideline_id)

    async def get_by_slug(self, slug: str) -> ChannelGuideline | None:
        stmt = select(ChannelGuideline).where(ChannelGuideline.slug == slug)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active(self) -> ChannelGuideline | None:
        stmt = (
            select(ChannelGuideline)
            .where(ChannelGuideline.is_active.is_(True))
            .order_by(ChannelGuideline.updated_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self) -> Sequence[ChannelGuideline]:
        stmt = select(ChannelGuideline).order_by(ChannelGuideline.updated_at.desc())
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def upsert_by_slug(
        self,
        *,
        slug: str,
        channel_name: str,
        guidelines_json: dict[str, Any],
        is_active: bool = True,
    ) -> ChannelGuideline:
        existing = await self.get_by_slug(slug)
        if existing is None:
            return await self.create(
                slug=slug,
                channel_name=channel_name,
                guidelines_json=guidelines_json,
                is_active=is_active,
            )

        if is_active:
            await self._deactivate_all(exclude_id=existing.id)
        existing.channel_name = channel_name
        existing.guidelines_json = guidelines_json
        existing.is_active = is_active
        existing.updated_at = datetime.now(UTC)
        await self._session.commit()
        await self._session.refresh(existing)
        return existing

    async def delete(self, record: ChannelGuideline) -> None:
        await self._session.delete(record)
        await self._session.commit()

    async def _deactivate_all(self, *, exclude_id: str | None = None) -> None:
        stmt = update(ChannelGuideline).values(is_active=False)
        if exclude_id is not None:
            stmt = stmt.where(ChannelGuideline.id != exclude_id)
        await self._session.execute(stmt)
