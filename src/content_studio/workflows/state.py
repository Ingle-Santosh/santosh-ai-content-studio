from typing import Annotated, TypedDict


def _merge_unique_list(left: list[str] | None, right: list[str] | None) -> list[str]:
    merged: list[str] = list(left or [])
    for item in right or []:
        if item not in merged:
            merged.append(item)
    return merged


class ContentWorkflowState(TypedDict, total=False):
    """Lightweight LangGraph state holding metadata and artifact references only."""

    project_id: str
    run_id: str
    thread_id: str
    topic: str
    auto_approve: bool

    # Inputs & queries
    seed_urls: list[str]
    max_results_per_query: int
    search_queries: list[str]
    competitor_queries: list[str]

    # Artifact & entity references (never large payloads or binaries)
    brief_artifact_id: str | None
    research_artifact_id: str | None
    competitor_artifact_id: str | None
    fact_check_artifact_id: str | None
    script_version_number: int | None
    script_artifact_id: str | None
    storyboard_artifact_id: str | None

    # Execution & human-in-the-loop tracking
    current_stage: str
    completed_steps: Annotated[list[str], _merge_unique_list]
    last_gate: str | None
    last_decision: str | None
    revision_notes: str | None
    revision_count: int
    cancelled: bool
    errors: Annotated[list[str], _merge_unique_list]
