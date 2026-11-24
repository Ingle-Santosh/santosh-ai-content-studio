import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from content_studio.database.models.artifact import Artifact
from content_studio.database.models.enums import ArtifactStatus, ArtifactType
from content_studio.database.repositories.artifact_repository import ArtifactRepository
from content_studio.database.repositories.project_repository import ProjectRepository
from content_studio.storage.artifact_store import ArtifactStore
from content_studio.utils.hashing import sha256_bytes

STAGE_DIR_MAP: dict[str, str] = {
    "research": "01_research",
    "01_research": "01_research",
    "brief": "02_outline",
    "outline": "02_outline",
    "storyboard": "02_outline",
    "02_outline": "02_outline",
    "script": "03_script",
    "03_script": "03_script",
    "visuals": "04_visuals",
    "assets": "04_visuals",
    "04_visuals": "04_visuals",
    "demos": "05_demos",
    "code": "05_demos",
    "05_demos": "05_demos",
    "production": "06_export",
    "export": "06_export",
    "06_export": "06_export",
}

_SAFE_SEGMENT_RE = re.compile(r"[^A-Za-z0-9._-]+")


class ResourceNotFoundError(LookupError):
    """Base error raised when a requested domain entity does not exist."""


class ProjectNotFoundError(ResourceNotFoundError):
    """Raised when a target project cannot be found."""


class ArtifactNotFoundError(ResourceNotFoundError):
    """Raised when a target artifact cannot be found for a project."""


class ArtifactFileMissingError(FileNotFoundError):
    """Raised when an artifact record exists in DB but its file is missing on disk."""


class ArtifactIntegrityReport(BaseModel):
    artifact_id: str
    relative_path: str
    exists_on_disk: bool
    expected_checksum: str | None
    actual_checksum: str | None
    expected_size_bytes: int
    actual_size_bytes: int | None
    is_valid: bool


def _sanitize_filename(name: str) -> tuple[str, str]:
    base = Path(name.strip()).name
    if not base or base in {".", ".."}:
        raise ValueError(f"Invalid artifact filename: {name!r}")
    stem = _SAFE_SEGMENT_RE.sub("_", Path(base).stem).strip("._") or "artifact"
    suffix = "".join(Path(base).suffixes)
    if suffix and not re.fullmatch(r"(\.[A-Za-z0-9]+)+", suffix):
        raise ValueError(f"Invalid artifact file extension: {suffix!r}")
    return stem, suffix


def _resolve_stage_dir(stage: str) -> str:
    normalized = stage.strip().lower()
    if normalized in STAGE_DIR_MAP:
        return STAGE_DIR_MAP[normalized]
    cleaned = _SAFE_SEGMENT_RE.sub("_", normalized).strip("._")
    if not cleaned:
        raise ValueError(f"Invalid artifact stage: {stage!r}")
    return cleaned


class ArtifactService:
    """Coordinates filesystem ArtifactStore with database ArtifactRepository."""

    def __init__(
        self,
        *,
        project_repo: ProjectRepository,
        artifact_repo: ArtifactRepository,
        store: ArtifactStore,
    ) -> None:
        self._project_repo = project_repo
        self._artifact_repo = artifact_repo
        self._store = store

    async def _require_project(self, project_id: str) -> None:
        project = await self._project_repo.get_by_id(project_id)
        if project is None:
            raise ProjectNotFoundError(f"Project '{project_id}' not found.")

    async def save_bytes(
        self,
        *,
        project_id: str,
        stage: str,
        artifact_type: ArtifactType | str,
        name: str,
        content: bytes,
        relative_path: str | Path | None = None,
        run_id: str | None = None,
        status: ArtifactStatus | str = ArtifactStatus.DRAFT,
        metadata_json: dict[str, Any] | None = None,
        supersede_previous_drafts: bool = True,
    ) -> Artifact:
        await self._require_project(project_id)

        type_val = artifact_type.value if isinstance(artifact_type, ArtifactType) else artifact_type
        latest_version = await self._artifact_repo.get_latest_version(project_id, stage, type_val)
        next_version = latest_version + 1

        if relative_path is None:
            stage_dir = _resolve_stage_dir(stage)
            stem, suffix = _sanitize_filename(name)
            target_rel_path: str | Path = Path(stage_dir) / f"{stem}_v{next_version}{suffix}"
        else:
            target_rel_path = relative_path

        stored = await self._store.awrite_bytes(project_id, target_rel_path, content)

        artifact = await self._artifact_repo.create(
            project_id=project_id,
            run_id=run_id,
            stage=stage,
            artifact_type=type_val,
            name=Path(name.strip()).name,
            relative_path=stored.relative_path,
            version=next_version,
            status=status,
            checksum_sha256=stored.checksum_sha256,
            size_bytes=stored.size_bytes,
            metadata_json=metadata_json or {},
        )

        if supersede_previous_drafts:
            await self._artifact_repo.supersede_drafts(
                project_id,
                stage,
                type_val,
                exclude_artifact_id=artifact.id,
            )

        return artifact

    async def save_text(
        self,
        *,
        project_id: str,
        stage: str,
        artifact_type: ArtifactType | str,
        name: str,
        content: str,
        encoding: str = "utf-8",
        relative_path: str | Path | None = None,
        run_id: str | None = None,
        status: ArtifactStatus | str = ArtifactStatus.DRAFT,
        metadata_json: dict[str, Any] | None = None,
        supersede_previous_drafts: bool = True,
    ) -> Artifact:
        return await self.save_bytes(
            project_id=project_id,
            stage=stage,
            artifact_type=artifact_type,
            name=name,
            content=content.encode(encoding),
            relative_path=relative_path,
            run_id=run_id,
            status=status,
            metadata_json=metadata_json,
            supersede_previous_drafts=supersede_previous_drafts,
        )

    async def save_json(
        self,
        *,
        project_id: str,
        stage: str,
        artifact_type: ArtifactType | str,
        name: str,
        payload: BaseModel | dict[str, Any] | list[Any],
        relative_path: str | Path | None = None,
        run_id: str | None = None,
        status: ArtifactStatus | str = ArtifactStatus.DRAFT,
        metadata_json: dict[str, Any] | None = None,
        supersede_previous_drafts: bool = True,
    ) -> Artifact:
        import json

        if isinstance(payload, BaseModel):
            serialized = payload.model_dump_json(indent=2)
        else:
            serialized = json.dumps(payload, indent=2, ensure_ascii=False)
        return await self.save_text(
            project_id=project_id,
            stage=stage,
            artifact_type=artifact_type,
            name=name,
            content=serialized,
            relative_path=relative_path,
            run_id=run_id,
            status=status,
            metadata_json=metadata_json,
            supersede_previous_drafts=supersede_previous_drafts,
        )

    async def list_artifacts(
        self,
        project_id: str,
        *,
        stage: str | None = None,
        artifact_type: ArtifactType | str | None = None,
    ) -> Sequence[Artifact]:
        await self._require_project(project_id)
        return await self._artifact_repo.list_for_project(
            project_id,
            stage=stage,
            artifact_type=artifact_type,
        )

    async def get_artifact(self, project_id: str, artifact_id: str) -> Artifact:
        await self._require_project(project_id)
        artifact = await self._artifact_repo.get_by_id(artifact_id)
        if artifact is None or artifact.project_id != project_id:
            raise ArtifactNotFoundError(
                f"Artifact '{artifact_id}' not found for project '{project_id}'."
            )
        return artifact

    async def read_artifact_bytes(
        self, project_id: str, artifact_id: str
    ) -> tuple[Artifact, bytes]:
        artifact = await self.get_artifact(project_id, artifact_id)
        if not self._store.exists(project_id, artifact.relative_path):
            raise ArtifactFileMissingError(
                f"Artifact file missing on disk: {artifact.relative_path}"
            )
        data = await self._store.aread_bytes(project_id, artifact.relative_path)
        return artifact, data

    async def read_artifact_text(
        self,
        project_id: str,
        artifact_id: str,
        *,
        encoding: str = "utf-8",
    ) -> tuple[Artifact, str]:
        artifact, data = await self.read_artifact_bytes(project_id, artifact_id)
        return artifact, data.decode(encoding)

    async def verify_integrity(self, project_id: str, artifact_id: str) -> ArtifactIntegrityReport:
        artifact = await self.get_artifact(project_id, artifact_id)
        if not self._store.exists(project_id, artifact.relative_path):
            return ArtifactIntegrityReport(
                artifact_id=artifact.id,
                relative_path=artifact.relative_path,
                exists_on_disk=False,
                expected_checksum=artifact.checksum_sha256,
                actual_checksum=None,
                expected_size_bytes=artifact.size_bytes,
                actual_size_bytes=None,
                is_valid=False,
            )

        data = await self._store.aread_bytes(project_id, artifact.relative_path)
        actual_checksum = sha256_bytes(data)
        actual_size = len(data)
        is_valid = (
            artifact.checksum_sha256 is not None
            and actual_checksum == artifact.checksum_sha256
            and actual_size == artifact.size_bytes
        )
        return ArtifactIntegrityReport(
            artifact_id=artifact.id,
            relative_path=artifact.relative_path,
            exists_on_disk=True,
            expected_checksum=artifact.checksum_sha256,
            actual_checksum=actual_checksum,
            expected_size_bytes=artifact.size_bytes,
            actual_size_bytes=actual_size,
            is_valid=is_valid,
        )

    async def update_status(
        self,
        project_id: str,
        artifact_id: str,
        status: ArtifactStatus | str,
    ) -> Artifact:
        artifact = await self.get_artifact(project_id, artifact_id)
        return await self._artifact_repo.update_status(artifact, status)
