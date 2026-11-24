import streamlit as st

from content_studio.config.settings import settings
from content_studio.database.models.enums import ArtifactType
from frontend.api_client import StudioAPIClient, StudioAPIError

st.set_page_config(
    page_title="Project Workspace — Santosh Analytics Studio",
    page_icon="📂",
    layout="wide",
)

client = StudioAPIClient(base_url=settings.API_BASE_URL)

st.title("📂 Project Workspace")
st.caption("Browse versioned artifacts, verify checksums, and review human approval gates")

try:
    projects = client.list_projects()
except StudioAPIError as exc:
    st.error(f"Could not connect to FastAPI backend: {exc}")
    st.stop()

if not projects:
    st.info("No projects yet. Create a project on the Home page first.")
    st.stop()

project_options = {f"{p['title']} ({p['status']})": p for p in projects}
selected_label = st.selectbox("Select Project", list(project_options.keys()))
project = project_options[selected_label]
project_id = project["id"]

meta_cols = st.columns(4)
meta_cols[0].metric("Status", project["status"])
meta_cols[1].metric("Stage", project.get("current_stage") or "—")
meta_cols[2].metric("Budget (USD)", f"${project.get('budget_usd', 0.0):.2f}")
meta_cols[3].metric("Spent (USD)", f"${project.get('spent_usd', 0.0):.2f}")

tab_artifacts, tab_add, tab_approvals = st.tabs(["Artifacts Browser", "Add Artifact", "Approvals"])

with tab_artifacts:
    filter_col1, filter_col2 = st.columns(2)
    stage_filter = filter_col1.selectbox(
        "Filter by Stage",
        ["All", "research", "outline", "script", "visuals", "demos", "export"],
    )
    type_options = ["All", *[t.value for t in ArtifactType]]
    type_filter = filter_col2.selectbox("Filter by Type", type_options)

    try:
        artifacts = client.list_artifacts(
            project_id,
            stage=None if stage_filter == "All" else stage_filter,
            artifact_type=None if type_filter == "All" else type_filter,
        )
    except StudioAPIError as exc:
        st.error(str(exc))
        artifacts = []

    if not artifacts:
        st.caption("No artifacts recorded for this project yet.")
    else:
        for art in artifacts:
            header = (
                f"v{art['version']} · {art['name']} "
                f"(`{art['stage']}` / `{art['artifact_type']}` — `{art['status']}`)"
            )
            with st.expander(header):
                st.write(f"- **Path**: `{art['relative_path']}`")
                st.write(f"- **Size**: {art['size_bytes']} bytes")
                st.write(f"- **SHA-256**: `{art.get('checksum_sha256') or 'n/a'}`")

                btn_col1, btn_col2 = st.columns(2)
                if btn_col1.button("Preview Content", key=f"preview_{art['id']}"):
                    try:
                        payload = client.get_artifact_content(project_id, art["id"])
                        st.code(payload["content"], language="markdown")
                    except StudioAPIError as exc:
                        st.error(str(exc))

                if btn_col2.button("Verify Checksum", key=f"verify_{art['id']}"):
                    try:
                        report = client.verify_artifact(project_id, art["id"])
                        if report["is_valid"]:
                            st.success("Checksum verified against file on disk.")
                        else:
                            st.error("Integrity mismatch or file missing on disk!")
                            st.json(report)
                    except StudioAPIError as exc:
                        st.error(str(exc))

with tab_add:
    st.subheader("Save Artifact to Project Store")
    with st.form("add_artifact_form", clear_on_submit=True):
        stage = st.selectbox(
            "Stage", ["research", "outline", "script", "visuals", "demos", "export"]
        )
        artifact_type = st.selectbox("Artifact Type", [t.value for t in ArtifactType])
        name = st.text_input("Filename", placeholder="e.g., content_brief.md")
        content = st.text_area("Content", height=200)
        submitted = st.form_submit_button("Save Versioned Artifact", type="primary")
        if submitted:
            if not name.strip():
                st.warning("Please enter a filename.")
            else:
                try:
                    saved = client.create_artifact(
                        project_id,
                        stage=stage,
                        artifact_type=artifact_type,
                        name=name.strip(),
                        content=content,
                    )
                    st.success(
                        f"Saved v{saved['version']} at `{saved['relative_path']}` "
                        f"(SHA-256: `{saved['checksum_sha256'][:12]}...`)"
                    )
                except StudioAPIError as exc:
                    st.error(str(exc))

with tab_approvals:
    st.subheader("Project Approval Gates")
    try:
        approvals = client.list_approvals(project_id=project_id)
    except StudioAPIError as exc:
        st.error(str(exc))
        approvals = []

    if not approvals:
        st.caption("No approval requests yet for this project.")
    else:
        for item in approvals:
            with st.container(border=True):
                st.markdown(f"**Gate: `{item['gate']}`** — Status: `{item['status']}`")
                if item.get("comments"):
                    st.caption(f"Notes: {item['comments']}")
                if item["status"] == "PENDING":
                    comment = st.text_input("Review Comment", key=f"comment_{item['id']}")
                    c1, c2, c3 = st.columns(3)
                    if c1.button("Approve", key=f"approve_{item['id']}", type="primary"):
                        client.decide_approval(
                            item["id"],
                            status="APPROVED",
                            reviewer="Creator",
                            comments=comment or None,
                        )
                        st.rerun()
                    if c2.button("Request Changes", key=f"changes_{item['id']}"):
                        client.decide_approval(
                            item["id"],
                            status="CHANGES_REQUESTED",
                            reviewer="Creator",
                            comments=comment or None,
                        )
                        st.rerun()
                    if c3.button("Reject", key=f"reject_{item['id']}"):
                        client.decide_approval(
                            item["id"],
                            status="REJECTED",
                            reviewer="Creator",
                            comments=comment or None,
                        )
                        st.rerun()
