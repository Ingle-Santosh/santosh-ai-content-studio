from pathlib import Path

from content_studio.config.settings import Settings
from content_studio.database.models.enums import (
    ArtifactStatus,
    ArtifactType,
    ClaimVerdict,
    SourceStatus,
)
from content_studio.database.models.evaluation import Evaluation
from content_studio.database.repositories import (
    EvaluationRepository,
    FactCheckRepository,
    ProjectRepository,
    ResearchRepository,
    SceneRepository,
    ScriptRepository,
    UsageRepository,
)
from content_studio.evaluation.rubric import (
    EVALUATION_PROMPT_VERSION,
    EvaluationDimensionScores,
    EvaluationReport,
    EvaluationWeights,
    LatencyCostSummary,
    LLMJudgeOutput,
    compute_weighted_score,
)
from content_studio.providers.llm import LLMMessage, ModelRouter, TaskType
from content_studio.services.artifact_service import ArtifactService, ProjectNotFoundError

_VISUAL_ARTIFACT_TYPES: frozenset[str] = frozenset(
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


def _render_evaluation_markdown(report: EvaluationReport) -> str:
    s = report.dimension_scores
    lc = report.latency_cost_summary
    lines = [
        "# Project Quality Evaluation Report",
        "",
        f"- **Project ID**: `{report.project_id}`",
        f"- **Evaluator**: `{report.evaluator}` (prompt `{report.evaluation_prompt_version}`)",
        f"- **Model**: `{report.model or 'deterministic'}`",
        f"- **Overall Weighted Score**: **{report.overall_score:.2f} / 100**",
        f"- **Human Review Mandatory**: `{report.human_review_required}`",
        "",
        "## Dimension Scores",
        "",
        "| Dimension | Weight | Score |",
        "|---|---:|---:|",
        f"| Factual Accuracy | {report.weights.factual_accuracy:.0%} | {s.factual_accuracy:.1f} |",
        f"| Research Quality | {report.weights.research_quality:.0%} | {s.research_quality:.1f} |",
        f"| Script Quality | {report.weights.script_quality:.0%} | {s.script_quality:.1f} |",
        f"| Teaching Clarity | {report.weights.teaching_clarity:.0%} | {s.teaching_clarity:.1f} |",
        f"| Visual Relevance | {report.weights.visual_relevance:.0%} | {s.visual_relevance:.1f} |",
        f"| Channel Guideline Compliance | {report.weights.channel_guideline_compliance:.0%} | "
        f"{s.channel_guideline_compliance:.1f} |",
        f"| Production Readiness | {report.weights.production_readiness:.0%} | "
        f"{s.production_readiness:.1f} |",
        "",
        "## Model Latency & Cost Telemetry",
        "",
        f"- **LLM Calls**: {lc.total_llm_calls}",
        f"- **Tokens**: {lc.total_prompt_tokens} prompt / {lc.total_completion_tokens} completion",
        f"- **Estimated Cost**: `${lc.total_estimated_cost_usd:.6f}`",
        f"- **Latency**: avg `{lc.avg_latency_ms:.1f} ms`, max `{lc.max_latency_ms} ms`",
        "",
        "## Feedback",
        "",
        report.feedback,
        "",
    ]
    return "\n".join(lines)


class EvaluationService:
    """Computes repeatable 7-dimension quality evaluations & model telemetry per project."""

    def __init__(
        self,
        *,
        app_settings: Settings,
        project_repo: ProjectRepository,
        research_repo: ResearchRepository,
        fact_check_repo: FactCheckRepository,
        script_repo: ScriptRepository,
        scene_repo: SceneRepository,
        usage_repo: UsageRepository,
        evaluation_repo: EvaluationRepository,
        artifact_service: ArtifactService,
        model_router: ModelRouter | None = None,
    ) -> None:
        self._settings = app_settings
        self._project_repo = project_repo
        self._research_repo = research_repo
        self._fact_check_repo = fact_check_repo
        self._script_repo = script_repo
        self._scene_repo = scene_repo
        self._usage_repo = usage_repo
        self._evaluation_repo = evaluation_repo
        self._artifact_service = artifact_service
        self._model_router = model_router

    async def evaluate_project(
        self,
        project_id: str,
        *,
        weights: EvaluationWeights | None = None,
        use_llm_judge: bool = False,
    ) -> EvaluationReport:
        project = await self._project_repo.get_by_id(project_id)
        if project is None:
            raise ProjectNotFoundError(f"Project '{project_id}' not found.")

        effective_weights = weights or EvaluationWeights()

        sources = list(await self._research_repo.list_sources(project_id))
        findings = list(await self._research_repo.list_findings(project_id))
        claims = list(await self._fact_check_repo.list_claims(project_id))
        script = await self._script_repo.get_for_project(project_id)
        scenes = list(await self._scene_repo.list_for_project(project_id))
        artifacts = list(await self._artifact_service.list_artifacts(project_id))
        usage_logs = list(await self._usage_repo.list_for_project(project_id))

        feedback_points: list[str] = []

        # 1. Factual Accuracy (25%)
        if claims:
            verified = sum(1 for c in claims if c.verdict == ClaimVerdict.VERIFIED.value)
            unsupported = sum(1 for c in claims if c.verdict == ClaimVerdict.UNSUPPORTED.value)
            conflicting = sum(1 for c in claims if c.verdict == ClaimVerdict.CONFLICTING.value)
            factual_score = (verified / len(claims)) * 100.0
            factual_score -= unsupported * 15.0 + conflicting * 10.0
            factual_score = max(0.0, min(100.0, round(factual_score, 1)))
            if unsupported or conflicting:
                feedback_points.append(
                    f"Resolve {unsupported} unsupported and {conflicting} conflicting claim(s)."
                )
        else:
            factual_score = 40.0 if findings else 0.0
            feedback_points.append("Run fact-checking to verify claims against sources.")

        # 2. Research Quality (15%)
        extracted_sources = [s for s in sources if s.status == SourceStatus.EXTRACTED.value]
        grounded_findings = [f for f in findings if f.source_urls_json]
        research_score = 0.0
        if extracted_sources:
            research_score += min(50.0, len(extracted_sources) * 20.0)
        if grounded_findings:
            research_score += min(50.0, (len(grounded_findings) / max(1, len(findings))) * 50.0)
        research_score = round(min(100.0, research_score), 1)
        if research_score < 70.0:
            feedback_points.append("Collect more extracted primary sources with grounded findings.")

        # 3. Script Quality (20%) & 4. Teaching Clarity (15%)
        latest_ver = script.versions[0] if (script and script.versions) else None
        if latest_ver is not None:
            val = latest_ver.validation_report_json or {}
            script_score = float(val.get("score", 60.0))
            has_demo = any(
                sec.get("code_demo_references") or sec.get("screen_recording_requirements")
                for sec in latest_ver.sections_json
            )
            has_examples = any(
                sec.get("section_type") in {"examples", "practical_demonstration"}
                for sec in latest_ver.sections_json
            )
            teaching_score = 50.0 + (25.0 if has_demo else 0.0) + (25.0 if has_examples else 0.0)
        else:
            script_score = 0.0
            teaching_score = 0.0
            feedback_points.append("Generate and validate a structured script.")

        # 5. Visual Relevance (10%)
        active_visuals = [
            a
            for a in artifacts
            if a.artifact_type in _VISUAL_ARTIFACT_TYPES
            and a.status not in {ArtifactStatus.SUPERSEDED.value, ArtifactStatus.FAILED.value}
        ]
        failed_visuals = [
            a
            for a in artifacts
            if a.artifact_type in _VISUAL_ARTIFACT_TYPES and a.status == ArtifactStatus.FAILED.value
        ]
        if scenes and active_visuals:
            visual_score = (
                min(100.0, 60.0 + len(active_visuals) * 15.0) - len(failed_visuals) * 25.0
            )
            visual_score = max(0.0, round(visual_score, 1))
        elif scenes:
            visual_score = 35.0
            feedback_points.append("Generate visual/code assets for storyboard scenes.")
        else:
            visual_score = 0.0
            feedback_points.append("Generate storyboard scenes and visual assets.")

        # 6. Channel Guideline Compliance (10%)
        guideline_score = 50.0
        if latest_ver is not None and latest_ver.language.lower() in {"hinglish", "english"}:
            guideline_score += 25.0
        yt_artifacts = [
            a for a in artifacts if a.artifact_type == ArtifactType.YOUTUBE_METADATA.value
        ]
        if yt_artifacts:
            guideline_score += 25.0
        guideline_score = min(100.0, round(guideline_score, 1))

        # 7. Production Readiness (5%)
        export_bundles = [
            a for a in artifacts if a.artifact_type == ArtifactType.EXPORT_BUNDLE.value
        ]
        prod_score = 0.0
        if script and script.approved_version is not None:
            prod_score += 35.0
        if scenes:
            prod_score += 25.0
        if export_bundles:
            prod_score += 40.0
        else:
            feedback_points.append("Export the final production ZIP package.")
        prod_score = min(100.0, round(prod_score, 1))

        # Optional LLM Judge blend for script_quality & teaching_clarity
        evaluator_name = "deterministic_rubric"
        model_used: str | None = None
        if use_llm_judge and self._model_router is not None and latest_ver is not None:
            prompt_path = self._settings.BASE_DIR / "prompts" / "evaluation" / "system.md"
            system_prompt = prompt_path.read_text(encoding="utf-8").strip()
            snippet = "\n".join(
                f"- {sec.get('title')}: {str(sec.get('narration', ''))[:240]}"
                for sec in latest_ver.sections_json[:9]
            )
            res = await self._model_router.generate_structured(
                task=TaskType.QA_REVIEW,
                messages=[
                    LLMMessage(role="system", content=system_prompt),
                    LLMMessage(
                        role="user",
                        content=f"Topic: {project.topic}\nScript Summary:\n{snippet}",
                    ),
                ],
                response_model=LLMJudgeOutput,
                project_id=project_id,
                node_name="quality_evaluator",
            )
            evaluator_name = "hybrid_llm_judge"
            model_used = f"{res.response.provider}/{res.response.model}"
            script_score = round((script_score + res.data.script_quality_score) / 2.0, 1)
            teaching_score = round((teaching_score + res.data.teaching_clarity_score) / 2.0, 1)
            feedback_points.append(f"LLM Judge: {res.data.feedback}")

        # Re-read usage logs if LLM judge ran so telemetry is completely up to date
        usage_logs = list(await self._usage_repo.list_for_project(project_id))
        latencies = [u.latency_ms for u in usage_logs]
        latency_cost = LatencyCostSummary(
            total_llm_calls=len(usage_logs),
            total_prompt_tokens=sum(u.prompt_tokens for u in usage_logs),
            total_completion_tokens=sum(u.completion_tokens for u in usage_logs),
            total_estimated_cost_usd=round(sum(u.estimated_cost_usd for u in usage_logs), 8),
            avg_latency_ms=round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
            max_latency_ms=max(latencies) if latencies else 0,
        )

        dim_scores = EvaluationDimensionScores(
            factual_accuracy=factual_score,
            research_quality=research_score,
            script_quality=script_score,
            teaching_clarity=teaching_score,
            visual_relevance=visual_score,
            channel_guideline_compliance=guideline_score,
            production_readiness=prod_score,
        )
        overall = compute_weighted_score(dim_scores, effective_weights)
        feedback = (
            " ".join(feedback_points)
            if feedback_points
            else "All evaluation dimensions meet target quality thresholds; human review required."
        )

        saved_row = await self._evaluation_repo.create(
            project_id=project_id,
            evaluator=evaluator_name,
            model=model_used,
            evaluation_prompt_version=EVALUATION_PROMPT_VERSION,
            weights_json=effective_weights.model_dump(),
            dimension_scores_json=dim_scores.model_dump(),
            overall_score=overall,
            feedback=feedback,
            latency_cost_summary_json=latency_cost.model_dump(),
        )

        report = EvaluationReport(
            evaluation_id=saved_row.id,
            project_id=project_id,
            evaluator=evaluator_name,
            model=model_used,
            evaluation_prompt_version=EVALUATION_PROMPT_VERSION,
            weights=effective_weights,
            dimension_scores=dim_scores,
            overall_score=overall,
            feedback=feedback,
            latency_cost_summary=latency_cost,
            human_review_required=True,
            evaluated_at=saved_row.evaluated_at,
        )

        report_art = await self._artifact_service.save_text(
            project_id=project_id,
            stage="export",
            artifact_type=ArtifactType.QA_REVIEW,
            name="evaluation_report.md",
            relative_path=Path("06_export") / "evaluation_report.md",
            content=_render_evaluation_markdown(report),
            metadata_json={"overall_score": overall, "evaluator": evaluator_name},
            supersede_previous_drafts=False,
        )
        report.report_artifact_id = report_art.id
        return report

    async def list_evaluations(self, project_id: str) -> list[Evaluation]:
        project = await self._project_repo.get_by_id(project_id)
        if project is None:
            raise ProjectNotFoundError(f"Project '{project_id}' not found.")
        return list(await self._evaluation_repo.list_for_project(project_id))
