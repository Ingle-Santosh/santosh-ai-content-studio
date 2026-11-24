from collections.abc import Sequence

from content_studio.database.models.approval import Approval
from content_studio.database.models.enums import ApprovalGate, ApprovalStatus, ArtifactStatus
from content_studio.database.repositories.approval_repository import ApprovalRepository
from content_studio.database.repositories.artifact_repository import ArtifactRepository
from content_studio.database.repositories.project_repository import ProjectRepository
from content_studio.services.artifact_service import (
    ArtifactNotFoundError,
    ProjectNotFoundError,
    ResourceNotFoundError,
)


class ApprovalNotFoundError(ResourceNotFoundError):
    """Raised when an approval record cannot be found."""


class ApprovalService:
    """Coordinates human-in-the-loop approval gates and linked artifact states."""

    def __init__(
        self,
        *,
        project_repo: ProjectRepository,
        approval_repo: ApprovalRepository,
        artifact_repo: ArtifactRepository,
    ) -> None:
        self._project_repo = project_repo
        self._approval_repo = approval_repo
        self._artifact_repo = artifact_repo

    async def request_approval(
        self,
        *,
        project_id: str,
        gate: ApprovalGate | str,
        run_id: str | None = None,
        artifact_id: str | None = None,
        comments: str | None = None,
    ) -> Approval:
        project = await self._project_repo.get_by_id(project_id)
        if project is None:
            raise ProjectNotFoundError(f"Project '{project_id}' not found.")

        if artifact_id is not None:
            artifact = await self._artifact_repo.get_by_id(artifact_id)
            if artifact is None or artifact.project_id != project_id:
                raise ArtifactNotFoundError(
                    f"Artifact '{artifact_id}' not found for project '{project_id}'."
                )

        return await self._approval_repo.create(
            project_id=project_id,
            gate=gate,
            run_id=run_id,
            artifact_id=artifact_id,
            comments=comments,
        )

    async def list_approvals(
        self,
        *,
        project_id: str | None = None,
        status: ApprovalStatus | str | None = None,
        gate: ApprovalGate | str | None = None,
        limit: int = 100,
    ) -> Sequence[Approval]:
        return await self._approval_repo.list_approvals(
            project_id=project_id,
            status=status,
            gate=gate,
            limit=limit,
        )

    async def get_approval(self, approval_id: str) -> Approval:
        approval = await self._approval_repo.get_by_id(approval_id)
        if approval is None:
            raise ApprovalNotFoundError(f"Approval '{approval_id}' not found.")
        return approval

    async def decide_approval(
        self,
        approval_id: str,
        *,
        status: ApprovalStatus,
        reviewer: str | None = None,
        comments: str | None = None,
    ) -> Approval:
        if status == ApprovalStatus.PENDING:
            raise ValueError("Decision status must be APPROVED, REJECTED, or CHANGES_REQUESTED.")

        approval = await self.get_approval(approval_id)
        updated = await self._approval_repo.decide(
            approval,
            status=status,
            reviewer=reviewer,
            comments=comments,
        )

        if status == ApprovalStatus.APPROVED and updated.artifact_id is not None:
            artifact = await self._artifact_repo.get_by_id(updated.artifact_id)
            if artifact is not None:
                await self._artifact_repo.update_status(artifact, ArtifactStatus.APPROVED)

        return updated
