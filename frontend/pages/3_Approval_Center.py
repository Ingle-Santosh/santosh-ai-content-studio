import streamlit as st

from content_studio.config.settings import settings
from frontend.api_client import StudioAPIClient, StudioAPIError

st.set_page_config(
    page_title="Approval Center — Santosh Analytics Studio",
    page_icon="✅",
    layout="wide",
)

client = StudioAPIClient(base_url=settings.API_BASE_URL)


def _submit_decision(
    *,
    decision: str,
    approval_id: str,
    wf_run_id: str | None,
    reviewer: str,
    notes: str,
) -> None:
    try:
        if wf_run_id:
            snap = client.resume_workflow(
                wf_run_id,
                decision=decision,
                reviewer=reviewer.strip() or "Creator",
                comments=notes.strip() or None,
            )
            st.success(
                f"Workflow resumed ({decision}) -> now `{snap['status']}` "
                f"at `{snap.get('current_stage')}`."
            )
        else:
            client.decide_approval(
                approval_id,
                status=decision,
                reviewer=reviewer.strip() or "Creator",
                comments=notes.strip() or None,
            )
            st.success(f"Recorded decision: {decision}.")
        st.rerun()
    except StudioAPIError as exc:
        st.error(str(exc))


st.title("✅ Human-in-the-Loop Approval Center")
st.caption("Review paused LangGraph workflows, inspect generated artifacts, and resume execution")

try:
    projects = client.list_projects()
    pending_approvals = client.list_approvals(status="PENDING")
except StudioAPIError as exc:
    st.error(f"Could not connect to FastAPI backend: {exc}")
    st.stop()

project_map = {p["id"]: p for p in projects}

if not pending_approvals:
    st.info("No pending human approvals right now. Start a workflow from Project Workspace.")
else:
    for item in pending_approvals:
        proj = project_map.get(item["project_id"], {})
        title = proj.get("title", item["project_id"])
        with st.container(border=True):
            st.markdown(f"### {title} — Gate: `{item['gate']}` (`{item['status']}`)")
            if item.get("comments"):
                st.write(item["comments"])

            if item.get("artifact_id") and st.button(
                "Preview Linked Artifact", key=f"ac_prev_{item['id']}"
            ):
                try:
                    payload = client.get_artifact_content(item["project_id"], item["artifact_id"])
                    st.markdown(payload["content"])
                except StudioAPIError as exc:
                    st.error(str(exc))

            reviewer = st.text_input("Reviewer", value="Santosh", key=f"ac_rev_{item['id']}")
            notes = st.text_area(
                "Comments / Revision Instructions",
                key=f"ac_notes_{item['id']}",
                height=80,
            )

            c1, c2, c3 = st.columns(3)
            run_id = item.get("run_id")

            if c1.button("Approve & Resume", key=f"ac_app_{item['id']}", type="primary"):
                _submit_decision(
                    decision="APPROVED",
                    approval_id=item["id"],
                    wf_run_id=run_id,
                    reviewer=reviewer,
                    notes=notes,
                )
            if c2.button("Request Changes", key=f"ac_chg_{item['id']}"):
                _submit_decision(
                    decision="CHANGES_REQUESTED",
                    approval_id=item["id"],
                    wf_run_id=run_id,
                    reviewer=reviewer,
                    notes=notes,
                )
            if c3.button("Reject", key=f"ac_rej_{item['id']}"):
                _submit_decision(
                    decision="REJECTED",
                    approval_id=item["id"],
                    wf_run_id=run_id,
                    reviewer=reviewer,
                    notes=notes,
                )
