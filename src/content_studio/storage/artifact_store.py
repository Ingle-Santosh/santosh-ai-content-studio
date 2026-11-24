import asyncio
import json
import shutil
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from content_studio.config.settings import settings
from content_studio.utils.hashing import sha256_bytes

PROJECT_STAGE_DIRS: tuple[str, ...] = (
    "01_research",
    "02_outline",
    "03_script",
    "04_visuals",
    "05_demos",
    "06_export",
)


class StoredArtifact(BaseModel):
    relative_path: str
    size_bytes: int
    checksum_sha256: str


class ArtifactStore:
    """Filesystem-backed artifact store using pathlib.Path exclusively."""

    def __init__(self, projects_dir: Path | None = None) -> None:
        self._projects_dir = (projects_dir or settings.resolved_projects_dir).resolve()

    @property
    def projects_dir(self) -> Path:
        return self._projects_dir

    def _validate_project_id(self, project_id: str) -> str:
        cleaned = project_id.strip()
        if (
            not cleaned
            or "/" in cleaned
            or "\\" in cleaned
            or ".." in cleaned
            or Path(cleaned).is_absolute()
        ):
            raise ValueError(f"Invalid project_id for filesystem storage: {project_id!r}")
        return cleaned

    def project_dir(self, project_id: str) -> Path:
        safe_id = self._validate_project_id(project_id)
        root = (self._projects_dir / safe_id).resolve()
        if not root.is_relative_to(self._projects_dir):
            raise ValueError(f"Project directory escapes projects root: {project_id!r}")
        return root

    def init_project_dirs(self, project_id: str) -> Path:
        root = self.project_dir(project_id)
        root.mkdir(parents=True, exist_ok=True)
        for stage_dir in PROJECT_STAGE_DIRS:
            (root / stage_dir).mkdir(parents=True, exist_ok=True)
        return root

    def resolve_artifact_path(self, project_id: str, relative_path: str | Path) -> Path:
        root = self.project_dir(project_id)
        rel = Path(relative_path)
        if rel.is_absolute():
            raise ValueError("Artifact path must be relative to the project directory.")
        resolved = (root / rel).resolve()
        if not resolved.is_relative_to(root):
            raise ValueError(f"Artifact path escapes project directory: {relative_path!r}")
        return resolved

    def write_bytes(
        self,
        project_id: str,
        relative_path: str | Path,
        content: bytes,
    ) -> StoredArtifact:
        target = self.resolve_artifact_path(project_id, relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        tmp_path = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            tmp_path.write_bytes(content)
            tmp_path.replace(target)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

        root = self.project_dir(project_id)
        rel_posix = target.relative_to(root).as_posix()
        return StoredArtifact(
            relative_path=rel_posix,
            size_bytes=len(content),
            checksum_sha256=sha256_bytes(content),
        )

    def write_text(
        self,
        project_id: str,
        relative_path: str | Path,
        content: str,
        *,
        encoding: str = "utf-8",
    ) -> StoredArtifact:
        return self.write_bytes(project_id, relative_path, content.encode(encoding))

    def write_json(
        self,
        project_id: str,
        relative_path: str | Path,
        payload: BaseModel | dict[str, Any] | list[Any],
    ) -> StoredArtifact:
        if isinstance(payload, BaseModel):
            serialized = payload.model_dump_json(indent=2)
        else:
            serialized = json.dumps(payload, indent=2, ensure_ascii=False)
        return self.write_text(project_id, relative_path, serialized)

    def read_bytes(self, project_id: str, relative_path: str | Path) -> bytes:
        target = self.resolve_artifact_path(project_id, relative_path)
        return target.read_bytes()

    def read_text(
        self,
        project_id: str,
        relative_path: str | Path,
        *,
        encoding: str = "utf-8",
    ) -> str:
        target = self.resolve_artifact_path(project_id, relative_path)
        return target.read_text(encoding=encoding)

    def exists(self, project_id: str, relative_path: str | Path) -> bool:
        target = self.resolve_artifact_path(project_id, relative_path)
        return target.is_file()

    def delete_project_dir(self, project_id: str) -> None:
        root = self.project_dir(project_id)
        if root.exists():
            shutil.rmtree(root)

    # Async wrappers for non-blocking I/O in FastAPI & LangGraph
    async def ainit_project_dirs(self, project_id: str) -> Path:
        return await asyncio.to_thread(self.init_project_dirs, project_id)

    async def awrite_bytes(
        self,
        project_id: str,
        relative_path: str | Path,
        content: bytes,
    ) -> StoredArtifact:
        return await asyncio.to_thread(self.write_bytes, project_id, relative_path, content)

    async def awrite_text(
        self,
        project_id: str,
        relative_path: str | Path,
        content: str,
        *,
        encoding: str = "utf-8",
    ) -> StoredArtifact:
        return await asyncio.to_thread(
            self.write_text, project_id, relative_path, content, encoding=encoding
        )

    async def awrite_json(
        self,
        project_id: str,
        relative_path: str | Path,
        payload: BaseModel | dict[str, Any] | list[Any],
    ) -> StoredArtifact:
        return await asyncio.to_thread(self.write_json, project_id, relative_path, payload)

    async def aread_bytes(self, project_id: str, relative_path: str | Path) -> bytes:
        return await asyncio.to_thread(self.read_bytes, project_id, relative_path)

    async def aread_text(
        self,
        project_id: str,
        relative_path: str | Path,
        *,
        encoding: str = "utf-8",
    ) -> str:
        return await asyncio.to_thread(self.read_text, project_id, relative_path, encoding=encoding)

    async def adelete_project_dir(self, project_id: str) -> None:
        await asyncio.to_thread(self.delete_project_dir, project_id)
