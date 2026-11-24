import asyncio
from dataclasses import dataclass, field
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from content_studio.database.models.enums import ApprovalGate, ApprovalStatus
from content_studio.services import (
    ApprovalService,
    CompetitorService,
    FactCheckService,
    ResearchService,
    ScriptwriterService,
    StoryboardService,
    TopicStrategistService,
)
from content_studio.workflows.state import ContentWorkflowState


@dataclass
class PipelineServices:
    topic_strategist: TopicStrategistService
    research: ResearchService
    competitor: CompetitorService
    fact_checker: FactCheckService
    scriptwriter: ScriptwriterService
    storyboard: StoryboardService
    approval: ApprovalService
    # Guards shared AsyncSession when parallel nodes execute inside a single test/request session
    db_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def build_content_pipeline_graph(
    services: PipelineServices,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
) -> Any:
    """Compile the human-in-the-loop LangGraph content production workflow."""

    async def topic_strategist_node(state: ContentWorkflowState) -> ContentWorkflowState:
        is_revision = (
            state.get("last_gate") == ApprovalGate.BRIEF.value
            and state.get("last_decision") == ApprovalStatus.CHANGES_REQUESTED.value
        )
        if "topic_strategist" in state.get("completed_steps", []) and not is_revision:
            return {"current_stage": "brief_ready"}

        async with services.db_lock:
            report = await services.topic_strategist.generate_brief(
                state["project_id"],
                revision_notes=state.get("revision_notes") if is_revision else None,
                request_brief_approval=False,
                run_id=state.get("run_id"),
            )
        return {
            "brief_artifact_id": report.brief_markdown_artifact_id,
            "search_queries": report.brief.search_queries,
            "competitor_queries": report.brief.competitor_queries,
            "current_stage": "brief_ready",
            "completed_steps": ["topic_strategist"],
            "revision_notes": None,
        }

    async def _run_approval_gate(
        state: ContentWorkflowState,
        *,
        gate: ApprovalGate,
        artifact_id: str | None,
        summary: str,
    ) -> ContentWorkflowState:
        if state.get("auto_approve", False):
            return {
                "last_gate": gate.value,
                "last_decision": ApprovalStatus.APPROVED.value,
                "revision_notes": None,
                "current_stage": f"{gate.value}_approved",
            }

        async with services.db_lock:
            existing = await services.approval.list_approvals(
                project_id=state["project_id"],
                gate=gate,
                status=ApprovalStatus.PENDING,
            )
            matching = [a for a in existing if a.run_id == state.get("run_id")]
            if matching:
                approval = matching[0]
            else:
                approval = await services.approval.request_approval(
                    project_id=state["project_id"],
                    gate=gate,
                    run_id=state.get("run_id"),
                    artifact_id=artifact_id,
                    comments=summary,
                )

        decision_payload = interrupt(
            {
                "gate": gate.value,
                "approval_id": approval.id,
                "artifact_id": artifact_id,
                "summary": summary,
            }
        )

        status_raw = str(decision_payload.get("status", ApprovalStatus.APPROVED.value)).upper()
        comments = decision_payload.get("comments")
        rev_count = int(state.get("revision_count", 0))
        if status_raw == ApprovalStatus.CHANGES_REQUESTED.value:
            rev_count += 1

        return {
            "last_gate": gate.value,
            "last_decision": status_raw,
            "revision_notes": comments,
            "revision_count": rev_count,
            "cancelled": status_raw == ApprovalStatus.REJECTED.value,
            "current_stage": f"{gate.value}_{status_raw.lower()}",
        }

    async def gate_brief_node(state: ContentWorkflowState) -> ContentWorkflowState:
        return await _run_approval_gate(
            state,
            gate=ApprovalGate.BRIEF,
            artifact_id=state.get("brief_artifact_id"),
            summary="Gate 1: Review and approve the Content Brief before starting research.",
        )

    async def research_node(state: ContentWorkflowState) -> ContentWorkflowState:
        if "research" in state.get("completed_steps", []):
            return {}
        async with services.db_lock:
            report = await services.research.run_research(
                state["project_id"],
                queries=state.get("search_queries") or None,
                seed_urls=state.get("seed_urls") or None,
                max_results_per_query=state.get("max_results_per_query", 5),
                synthesize_with_llm=True,
                run_id=state.get("run_id"),
            )
        return {
            "research_artifact_id": report.report_markdown_artifact_id,
            "completed_steps": ["research"],
        }

    async def competitor_node(state: ContentWorkflowState) -> ContentWorkflowState:
        if "competitor_analysis" in state.get("completed_steps", []):
            return {}
        async with services.db_lock:
            report = await services.competitor.run_analysis(
                state["project_id"],
                queries=state.get("competitor_queries") or None,
                max_results=state.get("max_results_per_query", 5),
                analyze_with_llm=True,
                run_id=state.get("run_id"),
            )
        return {
            "competitor_artifact_id": report.report_markdown_artifact_id,
            "completed_steps": ["competitor_analysis"],
        }

    async def merge_research_node(_state: ContentWorkflowState) -> ContentWorkflowState:
        return {
            "current_stage": "research_merged",
            "completed_steps": ["merge_research"],
        }

    async def fact_checker_node(state: ContentWorkflowState) -> ContentWorkflowState:
        is_revision = (
            state.get("last_gate") == ApprovalGate.RESEARCH.value
            and state.get("last_decision") == ApprovalStatus.CHANGES_REQUESTED.value
        )
        if "fact_checker" in state.get("completed_steps", []) and not is_revision:
            return {"current_stage": "fact_check_ready"}

        custom_claims = (
            [state["revision_notes"]] if is_revision and state.get("revision_notes") else None
        )
        async with services.db_lock:
            report = await services.fact_checker.run_fact_check(
                state["project_id"],
                custom_claims=custom_claims,
                request_research_approval=False,
                run_id=state.get("run_id"),
            )
        return {
            "fact_check_artifact_id": report.report_markdown_artifact_id,
            "current_stage": "fact_check_ready",
            "completed_steps": ["fact_checker"],
            "revision_notes": None,
        }

    async def gate_research_node(state: ContentWorkflowState) -> ContentWorkflowState:
        return await _run_approval_gate(
            state,
            gate=ApprovalGate.RESEARCH,
            artifact_id=state.get("fact_check_artifact_id"),
            summary="Gate 2: Review research, competitor gaps, and fact-check report.",
        )

    async def scriptwriter_node(state: ContentWorkflowState) -> ContentWorkflowState:
        is_revision = (
            state.get("last_gate") == ApprovalGate.SCRIPT.value
            and state.get("last_decision") == ApprovalStatus.CHANGES_REQUESTED.value
        )
        if "scriptwriter" in state.get("completed_steps", []) and not is_revision:
            return {"current_stage": "script_ready"}

        async with services.db_lock:
            report = await services.scriptwriter.generate_script(
                state["project_id"],
                revision_notes=state.get("revision_notes") if is_revision else None,
                require_approved_research=False,
                request_script_approval=False,
                run_id=state.get("run_id"),
            )
        return {
            "script_version_number": report.version_number,
            "script_artifact_id": report.script_markdown_artifact_id,
            "current_stage": "script_ready",
            "completed_steps": ["scriptwriter"],
            "revision_notes": None,
        }

    async def gate_script_node(state: ContentWorkflowState) -> ContentWorkflowState:
        result = await _run_approval_gate(
            state,
            gate=ApprovalGate.SCRIPT,
            artifact_id=state.get("script_artifact_id"),
            summary=(
                f"Gate 3: Review Script v{state.get('script_version_number') or 1} "
                "before storyboarding."
            ),
        )
        # When approved (either via human resume or auto_approve), mark ScriptVersion APPROVED
        if (
            result.get("last_decision") == ApprovalStatus.APPROVED.value
            and state.get("script_version_number") is not None
        ):
            async with services.db_lock:
                await services.scriptwriter.approve_version(
                    state["project_id"],
                    int(state["script_version_number"]),
                    reviewer="Creator",
                    comments=result.get("revision_notes"),
                )
        return result

    async def storyboard_node(state: ContentWorkflowState) -> ContentWorkflowState:
        if "storyboard" in state.get("completed_steps", []):
            return {"current_stage": "storyboard_ready"}

        async with services.db_lock:
            report = await services.storyboard.generate_storyboard(
                state["project_id"],
                script_version_number=state.get("script_version_number"),
                require_approved_script=True,
                run_id=state.get("run_id"),
            )
        return {
            "storyboard_artifact_id": report.storyboard_markdown_artifact_id,
            "current_stage": "storyboard_ready",
            "completed_steps": ["storyboard"],
        }

    def _route_after_brief(state: ContentWorkflowState) -> str | list[str]:
        decision = state.get("last_decision")
        if decision == ApprovalStatus.APPROVED.value:
            return ["research_node", "competitor_node"]
        if decision == ApprovalStatus.CHANGES_REQUESTED.value:
            return "topic_strategist"
        return END

    def _route_after_research(state: ContentWorkflowState) -> str:
        decision = state.get("last_decision")
        if decision == ApprovalStatus.APPROVED.value:
            return "scriptwriter"
        if decision == ApprovalStatus.CHANGES_REQUESTED.value:
            return "fact_checker"
        return END

    def _route_after_script(state: ContentWorkflowState) -> str:
        decision = state.get("last_decision")
        if decision == ApprovalStatus.APPROVED.value:
            return "storyboard"
        if decision == ApprovalStatus.CHANGES_REQUESTED.value:
            return "scriptwriter"
        return END

    builder = StateGraph(ContentWorkflowState)

    builder.add_node("topic_strategist", topic_strategist_node)
    builder.add_node("gate_brief", gate_brief_node)
    builder.add_node("research_node", research_node)
    builder.add_node("competitor_node", competitor_node)
    builder.add_node("merge_research", merge_research_node)
    builder.add_node("fact_checker", fact_checker_node)
    builder.add_node("gate_research", gate_research_node)
    builder.add_node("scriptwriter", scriptwriter_node)
    builder.add_node("gate_script", gate_script_node)
    builder.add_node("storyboard", storyboard_node)

    builder.add_edge(START, "topic_strategist")
    builder.add_edge("topic_strategist", "gate_brief")
    builder.add_conditional_edges(
        "gate_brief",
        _route_after_brief,
        ["research_node", "competitor_node", "topic_strategist", END],
    )
    builder.add_edge("research_node", "merge_research")
    builder.add_edge("competitor_node", "merge_research")
    builder.add_edge("merge_research", "fact_checker")
    builder.add_edge("fact_checker", "gate_research")
    builder.add_conditional_edges(
        "gate_research",
        _route_after_research,
        ["scriptwriter", "fact_checker", END],
    )
    builder.add_edge("scriptwriter", "gate_script")
    builder.add_conditional_edges(
        "gate_script",
        _route_after_script,
        ["storyboard", "scriptwriter", END],
    )
    builder.add_edge("storyboard", END)

    return builder.compile(checkpointer=checkpointer)
