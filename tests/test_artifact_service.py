import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from content_studio.database.models.enums import ArtifactStatus, ArtifactType
from content_studio.database.repositories import ArtifactRepository, ProjectRepository
from content_studio.services import ArtifactService, ProjectNotFoundError
from content_studio.storage.artifact_store import ArtifactStore


@pytest.mark.asyncio
async def test_artifact_service_versioning_superseding_and_integrity(
    db_session: AsyncSession,
    artifact_store: ArtifactStore,
) -> None:
    project_repo = ProjectRepository(db_session)
    artifact_repo = ArtifactRepository(db_session)
    service = ArtifactService(
        project_repo=project_repo,
        artifact_repo=artifact_repo,
        store=artifact_store,
    )

    project = await project_repo.create(title="RAG vs CAG", topic="RAG vs CAG Architecture")
    await artifact_store.ainit_project_dirs(project.id)

    # Save v1 draft
    v1 = await service.save_text(
        project_id=project.id,
        stage="script",
        artifact_type=ArtifactType.SCRIPT,
        name="script.md",
        content="# Script v1\nNamaste devs!",
    )
    assert v1.version == 1
    assert v1.relative_path == "03_script/script_v1.md"
    assert v1.status == ArtifactStatus.DRAFT.value

    # Approve v1 — approved versions must NOT be superseded by newer drafts
    await service.update_status(project.id, v1.id, ArtifactStatus.APPROVED)

    # Save v2 draft
    v2 = await service.save_text(
        project_id=project.id,
        stage="script",
        artifact_type=ArtifactType.SCRIPT,
        name="script.md",
        content="# Script v2\nUpdated hook!",
    )
    assert v2.version == 2
    assert v2.relative_path == "03_script/script_v2.md"

    # Save v3 draft -> v2 (DRAFT) becomes SUPERSEDED, v1 (APPROVED) stays APPROVED
    v3 = await service.save_text(
        project_id=project.id,
        stage="script",
        artifact_type=ArtifactType.SCRIPT,
        name="script.md",
        content="# Script v3\nFinal polish!",
    )
    assert v3.version == 3

    reloaded_v1 = await service.get_artifact(project.id, v1.id)
    reloaded_v2 = await service.get_artifact(project.id, v2.id)
    reloaded_v3 = await service.get_artifact(project.id, v3.id)
    assert reloaded_v1.status == ArtifactStatus.APPROVED.value
    assert reloaded_v2.status == ArtifactStatus.SUPERSEDED.value
    assert reloaded_v3.status == ArtifactStatus.DRAFT.value

    # Integrity verification passes before tampering
    report_ok = await service.verify_integrity(project.id, v3.id)
    assert report_ok.is_valid is True
    assert report_ok.exists_on_disk is True
    assert report_ok.actual_checksum == v3.checksum_sha256

    # Simulate external tampering on disk -> integrity check catches mismatch
    disk_path = artifact_store.resolve_artifact_path(project.id, v3.relative_path)
    disk_path.write_text("# Tampered content", encoding="utf-8")
    report_bad = await service.verify_integrity(project.id, v3.id)
    assert report_bad.is_valid is False
    assert report_bad.exists_on_disk is True
    assert report_bad.actual_checksum != report_bad.expected_checksum


@pytest.mark.asyncio
async def test_artifact_service_rejects_missing_project(
    db_session: AsyncSession,
    artifact_store: ArtifactStore,
) -> None:
    service = ArtifactService(
        project_repo=ProjectRepository(db_session),
        artifact_repo=ArtifactRepository(db_session),
        store=artifact_store,
    )
    with pytest.raises(ProjectNotFoundError):
        await service.save_text(
            project_id="non-existent-id",
            stage="research",
            artifact_type=ArtifactType.RESEARCH_BRIEF,
            name="brief.md",
            content="hello",
        )
