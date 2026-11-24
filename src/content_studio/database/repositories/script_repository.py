from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from content_studio.database.models.enums import ArtifactStatus, ScriptStatus
from content_studio.database.models.script import Script, ScriptVersion


class ScriptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_project(self, project_id: str) -> Script | None:
        stmt = (
            select(Script)
            .options(selectinload(Script.versions))
            .where(Script.project_id == project_id)
            .order_by(Script.created_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create_script(self, *, project_id: str, title: str) -> Script:
        existing = await self.get_for_project(project_id)
        if existing is not None:
            return existing
        script = Script(
            project_id=project_id,
            title=title[:300],
            current_version=0,
            status=ScriptStatus.DRAFT.value,
        )
        self._session.add(script)
        await self._session.commit()
        await self._session.refresh(script)
        return script

    async def create_version(
        self,
        script: Script,
        *,
        project_id: str,
        language: str,
        total_estimated_duration_seconds: int,
        word_count: int,
        sections_json: list[dict[str, Any]],
        validation_report_json: dict[str, Any],
        artifact_id: str | None = None,
        run_id: str | None = None,
        revision_notes: str | None = None,
        title: str | None = None,
    ) -> ScriptVersion:
        next_version = script.current_version + 1

        # Supersede prior DRAFT versions without altering APPROVED versions
        await self._session.execute(
            update(ScriptVersion)
            .where(
                ScriptVersion.script_id == script.id,
                ScriptVersion.status == ArtifactStatus.DRAFT.value,
            )
            .values(status=ArtifactStatus.SUPERSEDED.value)
        )

        version = ScriptVersion(
            script_id=script.id,
            project_id=project_id,
            run_id=run_id,
            artifact_id=artifact_id,
            version_number=next_version,
            status=ArtifactStatus.DRAFT.value,
            language=language,
            total_estimated_duration_seconds=total_estimated_duration_seconds,
            word_count=word_count,
            sections_json=sections_json,
            validation_report_json=validation_report_json,
            revision_notes=revision_notes,
        )
        self._session.add(version)

        script.current_version = next_version
        if title:
            script.title = title[:300]
        script.status = ScriptStatus.IN_REVIEW.value
        script.updated_at = datetime.now(UTC)

        await self._session.commit()
        await self._session.refresh(version)
        await self._session.refresh(script)
        return version

    async def get_version(
        self,
        project_id: str,
        version_number: int,
    ) -> ScriptVersion | None:
        stmt = select(ScriptVersion).where(
            ScriptVersion.project_id == project_id,
            ScriptVersion.version_number == version_number,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_version_by_id(self, version_id: str) -> ScriptVersion | None:
        return await self._session.get(ScriptVersion, version_id)

    async def get_latest_approved_version(self, project_id: str) -> ScriptVersion | None:
        stmt = (
            select(ScriptVersion)
            .where(
                ScriptVersion.project_id == project_id,
                ScriptVersion.status == ArtifactStatus.APPROVED.value,
            )
            .order_by(ScriptVersion.version_number.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_versions(self, project_id: str) -> Sequence[ScriptVersion]:
        stmt = (
            select(ScriptVersion)
            .where(ScriptVersion.project_id == project_id)
            .order_by(ScriptVersion.version_number.desc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def approve_version(
        self,
        script: Script,
        version: ScriptVersion,
    ) -> ScriptVersion:
        version.status = ArtifactStatus.APPROVED.value
        script.approved_version = version.version_number
        script.status = ScriptStatus.APPROVED.value
        script.updated_at = datetime.now(UTC)
        await self._session.commit()
        await self._session.refresh(version)
        await self._session.refresh(script)
        return version
