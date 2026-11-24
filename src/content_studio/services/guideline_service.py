from collections.abc import Sequence

from content_studio.contracts.guidelines import ChannelGuidelinesConfig
from content_studio.database.models.channel_guideline import ChannelGuideline
from content_studio.database.repositories.guideline_repository import ChannelGuidelineRepository

DEFAULT_GUIDELINE_SLUG = "santosh-analytics"
DEFAULT_CHANNEL_NAME = "Santosh Analytics"


class ChannelGuidelineService:
    """Manages reusable channel guidelines persisted in the database."""

    def __init__(self, repo: ChannelGuidelineRepository) -> None:
        self._repo = repo

    async def get_or_create_active(self) -> ChannelGuideline:
        active = await self._repo.get_active()
        if active is not None:
            return active

        default_existing = await self._repo.get_by_slug(DEFAULT_GUIDELINE_SLUG)
        if default_existing is not None:
            return await self._repo.upsert_by_slug(
                slug=default_existing.slug,
                channel_name=default_existing.channel_name,
                guidelines_json=default_existing.guidelines_json,
                is_active=True,
            )

        return await self._repo.create(
            slug=DEFAULT_GUIDELINE_SLUG,
            channel_name=DEFAULT_CHANNEL_NAME,
            guidelines_json=ChannelGuidelinesConfig().model_dump(),
            is_active=True,
        )

    async def get_active_config(self) -> ChannelGuidelinesConfig:
        record = await self.get_or_create_active()
        return ChannelGuidelinesConfig.model_validate(record.guidelines_json)

    async def list_guidelines(self) -> Sequence[ChannelGuideline]:
        records = await self._repo.list_all()
        if not records:
            seeded = await self.get_or_create_active()
            return [seeded]
        return records

    async def get_by_slug(self, slug: str) -> ChannelGuideline | None:
        return await self._repo.get_by_slug(slug)

    async def upsert_guideline(
        self,
        *,
        slug: str,
        channel_name: str,
        guidelines: ChannelGuidelinesConfig,
        is_active: bool = True,
    ) -> ChannelGuideline:
        cleaned_slug = slug.strip().lower()
        if not cleaned_slug:
            raise ValueError("Guideline slug must not be empty.")
        return await self._repo.upsert_by_slug(
            slug=cleaned_slug,
            channel_name=channel_name.strip() or DEFAULT_CHANNEL_NAME,
            guidelines_json=guidelines.model_dump(),
            is_active=is_active,
        )
