from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from content_studio.database.models.registered_model import RegisteredModel


class ModelRegistryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        name: str,
        provider: str,
        model_id: str,
        base_url: str,
        tier: str = "local_small",
        is_cloud: bool = True,
        input_cost_per_1m: float = 0.0,
        output_cost_per_1m: float = 0.0,
        notes: str | None = None,
    ) -> RegisteredModel:
        row = RegisteredModel(
            name=name.strip(),
            provider=provider.strip().lower(),
            model_id=model_id.strip(),
            base_url=base_url.strip().rstrip("/"),
            tier=tier.strip().lower(),
            is_cloud=is_cloud,
            input_cost_per_1m=float(input_cost_per_1m),
            output_cost_per_1m=float(output_cost_per_1m),
            is_active=True,
            notes=notes.strip() if notes and notes.strip() else None,
        )
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return row

    async def get_by_id(self, registry_id: str) -> RegisteredModel | None:
        return await self._session.get(RegisteredModel, registry_id)

    async def get_by_name(self, name: str) -> RegisteredModel | None:
        stmt = select(RegisteredModel).where(RegisteredModel.name == name.strip())
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self, *, active_only: bool = False) -> Sequence[RegisteredModel]:
        stmt = select(RegisteredModel).order_by(
            RegisteredModel.is_cloud.asc(),
            RegisteredModel.created_at.desc(),
        )
        if active_only:
            stmt = stmt.where(RegisteredModel.is_active.is_(True))
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def update(
        self,
        entry: RegisteredModel,
        *,
        name: str | None = None,
        provider: str | None = None,
        model_id: str | None = None,
        base_url: str | None = None,
        tier: str | None = None,
        is_cloud: bool | None = None,
        input_cost_per_1m: float | None = None,
        output_cost_per_1m: float | None = None,
        is_active: bool | None = None,
        notes: str | None = None,
    ) -> RegisteredModel:
        if name is not None:
            entry.name = name.strip()
        if provider is not None:
            entry.provider = provider.strip().lower()
        if model_id is not None:
            entry.model_id = model_id.strip()
        if base_url is not None:
            entry.base_url = base_url.strip().rstrip("/")
        if tier is not None:
            entry.tier = tier.strip().lower()
        if is_cloud is not None:
            entry.is_cloud = is_cloud
        if input_cost_per_1m is not None:
            entry.input_cost_per_1m = float(input_cost_per_1m)
        if output_cost_per_1m is not None:
            entry.output_cost_per_1m = float(output_cost_per_1m)
        if is_active is not None:
            entry.is_active = is_active
        if notes is not None:
            entry.notes = notes.strip() or None
        entry.updated_at = datetime.now(UTC)
        await self._session.commit()
        await self._session.refresh(entry)
        return entry

    async def delete(self, entry: RegisteredModel) -> None:
        await self._session.delete(entry)
        await self._session.commit()
