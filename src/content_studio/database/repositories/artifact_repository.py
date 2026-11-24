from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from content_studio.database.models.artifact import Artifact
from content_studio.database.models.enums import ArtifactStatus, ArtifactType


class ArtifactRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        project_id: str,
        stage: str,
        artifact_type: ArtifactType | str,
        name: str,
        relative_path: str,
        run_id: str | None = None,
        version: int | None = None,
        status: ArtifactStatus | str = ArtifactStatus.DRAFT,
        checksum_sha256: str | None = None,
        size_bytes: int = 0,
        metadata_json: dict[str, Any] | None = None,
    ) -> Artifact:
        type_val = artifact_type.value if isinstance(artifact_type, ArtifactType) else artifact_type
        status_val = status.value if isinstance(status, ArtifactStatus) else status

        if version is None:
            latest = await self.get_latest_version(project_id, stage, type_val)
            version = latest + 1

        artifact = Artifact(
            project_id=project_id,
            run_id=run_id,
            stage=stage,
            artifact_type=type_val,
            name=name,
            relative_path=relative_path,
            version=version,
            status=status_val,
            checksum_sha256=checksum_sha256,
            size_bytes=size_bytes,
            metadata_json=metadata_json or {},
        )
        self._session.add(artifact)
        await self._session.commit()
        await self._session.refresh(artifact)
        return artifact

    async def get_by_id(self, artifact_id: str) -> Artifact | None:
        return await self._session.get(Artifact, artifact_id)

    async def get_latest_version(
        self,
        project_id: str,
        stage: str,
        artifact_type: ArtifactType | str,
    ) -> int:
        type_val = artifact_type.value if isinstance(artifact_type, ArtifactType) else artifact_type
        stmt = select(func.max(Artifact.version)).where(
            Artifact.project_id == project_id,
            Artifact.stage == stage,
            Artifact.artifact_type == type_val,
        )
        result = await self._session.execute(stmt)
        return int(result.scalar() or 0)

    async def list_for_project(
        self,
        project_id: str,
        *,
        stage: str | None = None,
        artifact_type: ArtifactType | str | None = None,
    ) -> Sequence[Artifact]:
        stmt = (
            select(Artifact)
            .where(Artifact.project_id == project_id)
            .order_by(Artifact.created_at.desc())
        )
        if stage is not None:
            stmt = stmt.where(Artifact.stage == stage)
        if artifact_type is not None:
            type_val = (
                artifact_type.value if isinstance(artifact_type, ArtifactType) else artifact_type
            )
            stmt = stmt.where(Artifact.artifact_type == type_val)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def update_status(self, artifact: Artifact, status: ArtifactStatus | str) -> Artifact:
        artifact.status = status.value if isinstance(status, ArtifactStatus) else status
        await self._session.commit()
        await self._session.refresh(artifact)
        return artifact

    async def supersede_drafts(
        self,
        project_id: str,
        stage: str,
        artifact_type: ArtifactType | str,
        *,
        exclude_artifact_id: str | None = None,
    ) -> int:
        """Mark prior DRAFT versions of the same artifact slot as SUPERSEDED.

        Approved artifacts are never modified destructively.
        """
        type_val = artifact_type.value if isinstance(artifact_type, ArtifactType) else artifact_type
        stmt = (
            update(Artifact)
            .where(
                Artifact.project_id == project_id,
                Artifact.stage == stage,
                Artifact.artifact_type == type_val,
                Artifact.status == ArtifactStatus.DRAFT.value,
            )
            .values(status=ArtifactStatus.SUPERSEDED.value)
        )
        if exclude_artifact_id is not None:
            stmt = stmt.where(Artifact.id != exclude_artifact_id)
        result = await self._session.execute(stmt)
        await self._session.commit()
        return int(result.rowcount or 0)
