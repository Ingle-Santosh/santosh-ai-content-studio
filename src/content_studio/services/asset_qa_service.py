from pathlib import Path

from content_studio.contracts.assets import AssetQACheckItem, AssetQAReport
from content_studio.database.models.enums import ApprovalGate, ArtifactStatus, ArtifactType
from content_studio.services.animation_renderer import validate_sanitized_html
from content_studio.services.approval_service import ApprovalService
from content_studio.services.artifact_service import ArtifactService
from content_studio.services.diagram_renderer import validate_mermaid_syntax

_ASSET_TYPES_TO_AUDIT: frozenset[str] = frozenset(
    {
        ArtifactType.DIAGRAM_MMD.value,
        ArtifactType.DIAGRAM_SVG.value,
        ArtifactType.DIAGRAM_PNG.value,
        ArtifactType.HTML_ANIMATION.value,
        ArtifactType.IMAGE.value,
        ArtifactType.SCREENSHOT.value,
        ArtifactType.CODE_DEMO.value,
    }
)


def _render_qa_markdown(report: AssetQAReport) -> str:
    lines = [
        "# Asset Quality Assurance Report",
        "",
        f"- **Project ID**: `{report.project_id}`",
        f"- **Overall Status**: {'PASSED' if report.passed else 'FAILED'}",
        f"- **Summary**: {report.passed_count}/{report.total_assets} passed "
        f"({report.failed_count} failed)",
        "",
    ]
    if report.blocking_issues:
        lines.append("## Blocking Issues")
        lines.append("")
        for issue in report.blocking_issues:
            lines.append(f"- ❌ {issue}")
        lines.append("")

    lines.append("## Audited Assets")
    lines.append("")
    for item in report.items:
        badge = "✅ PASS" if item.passed else "❌ FAIL"
        lines.append(f"- {badge} `{item.name}` (`{item.artifact_type}`, `{item.relative_path}`)")
        for iss in item.issues:
            lines.append(f"  - {iss}")
    lines.append("")
    return "\n".join(lines)


class AssetQAService:
    """Deterministic technical & provenance QA gate for generated visual/code assets."""

    def __init__(
        self,
        *,
        artifact_service: ArtifactService,
        approval_service: ApprovalService | None = None,
    ) -> None:
        self._artifact_service = artifact_service
        self._approval_service = approval_service

    async def run_qa(
        self,
        project_id: str,
        *,
        request_assets_approval: bool = True,
        run_id: str | None = None,
    ) -> AssetQAReport:
        all_artifacts = await self._artifact_service.list_artifacts(project_id)
        target_artifacts = [
            art
            for art in all_artifacts
            if art.artifact_type in _ASSET_TYPES_TO_AUDIT
            and art.status != ArtifactStatus.SUPERSEDED.value
        ]

        items: list[AssetQACheckItem] = []
        blocking_issues: list[str] = []

        for art in target_artifacts:
            issues: list[str] = []
            integrity = await self._artifact_service.verify_integrity(project_id, art.id)
            if not integrity.is_valid:
                issues.append("File missing on disk or SHA-256 checksum mismatch.")

            meta = art.metadata_json or {}

            if art.status == ArtifactStatus.FAILED.value:
                issues.append("Artifact is in FAILED status and must be retried.")

            if art.artifact_type == ArtifactType.DIAGRAM_MMD.value and integrity.exists_on_disk:
                _, text = await self._artifact_service.read_artifact_text(project_id, art.id)
                issues.extend(validate_mermaid_syntax(text))

            elif art.artifact_type == ArtifactType.DIAGRAM_SVG.value and integrity.exists_on_disk:
                _, text = await self._artifact_service.read_artifact_text(project_id, art.id)
                if "<svg" not in text.lower():
                    issues.append("SVG artifact does not contain a valid <svg> root element.")

            elif (
                art.artifact_type == ArtifactType.HTML_ANIMATION.value and integrity.exists_on_disk
            ):
                _, text = await self._artifact_service.read_artifact_text(project_id, art.id)
                issues.extend(validate_sanitized_html(text))

            elif art.artifact_type == ArtifactType.CODE_DEMO.value:
                if not meta.get("validation_passed", False):
                    exec_info = meta.get("execution") or {}
                    err_msg = (
                        "; ".join(exec_info.get("blocked_reasons") or [])
                        or exec_info.get("stderr")
                        or "Code demo has not passed isolated execution validation."
                    )
                    issues.append(f"Code validation failed: {err_msg}")

            elif art.artifact_type == ArtifactType.SCREENSHOT.value:
                prov = meta.get("provenance")
                if not isinstance(prov, dict) or not prov.get("captured_by"):
                    issues.append("Screenshot is missing mandatory provenance metadata.")

            passed = len(issues) == 0
            if not passed:
                blocking_issues.append(f"{art.name}: {'; '.join(issues)}")

            items.append(
                AssetQACheckItem(
                    artifact_id=art.id,
                    name=art.name,
                    artifact_type=art.artifact_type,
                    relative_path=art.relative_path,
                    passed=passed,
                    checksum_valid=integrity.is_valid,
                    issues=issues,
                )
            )

        passed_count = sum(1 for item in items if item.passed)
        failed_count = len(items) - passed_count
        overall_passed = len(items) > 0 and failed_count == 0
        if len(items) == 0:
            blocking_issues.append("No visual or code assets have been generated yet.")

        report = AssetQAReport(
            project_id=project_id,
            passed=overall_passed,
            total_assets=len(items),
            passed_count=passed_count,
            failed_count=failed_count,
            blocking_issues=blocking_issues,
            items=items,
        )

        qa_md = await self._artifact_service.save_text(
            project_id=project_id,
            stage="visuals",
            artifact_type=ArtifactType.QA_REVIEW,
            name="asset_qa_report.md",
            relative_path=Path("04_visuals") / "asset_qa_report.md",
            content=_render_qa_markdown(report),
            run_id=run_id,
            metadata_json={"passed": overall_passed, "failed_count": failed_count},
        )
        report.report_artifact_id = qa_md.id

        # Only create Gate 4 approval when Asset QA passes cleanly!
        if overall_passed and request_assets_approval and self._approval_service is not None:
            approval = await self._approval_service.request_approval(
                project_id=project_id,
                gate=ApprovalGate.STORYBOARD_ASSETS,
                run_id=run_id,
                artifact_id=qa_md.id,
                comments=f"Asset QA passed ({passed_count}/{len(items)} assets verified).",
            )
            report.approval_id = approval.id

        return report
