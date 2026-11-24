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

(
    tab_workflow,
    tab_research,
    tab_competitors,
    tab_fact_check,
    tab_script,
    tab_storyboard,
    tab_artifacts,
    tab_add,
    tab_approvals,
) = st.tabs(
    [
        "Workflow",
        "Research",
        "Competitors",
        "Fact Checking",
        "Script",
        "Storyboard",
        "Artifacts Browser",
        "Add Artifact",
        "Approvals",
    ]
)

with tab_workflow:
    st.subheader("LangGraph End-to-End Pipeline")
    with st.form("start_workflow_form"):
        wf_seeds_raw = st.text_area(
            "Seed Reference URLs (optional, one per line)",
            height=70,
        )
        w1, w2 = st.columns(2)
        wf_max_res = w1.slider("Search Results per Query", min_value=1, max_value=10, value=5)
        wf_auto = w2.checkbox("Auto-Approve Gates (Skip Human Pauses)", value=False)
        if st.form_submit_button("Start Full Workflow", type="primary"):
            wf_seeds = [line.strip() for line in wf_seeds_raw.splitlines() if line.strip()] or None
            with st.spinner("Running LangGraph pipeline until next human approval gate..."):
                try:
                    snap = client.start_workflow(
                        project_id,
                        seed_urls=wf_seeds,
                        max_results_per_query=wf_max_res,
                        auto_approve=wf_auto,
                    )
                    st.success(
                        f"Workflow `{snap['run_id'][:8]}` is now `{snap['status']}` "
                        f"at stage `{snap.get('current_stage')}`."
                    )
                except StudioAPIError as exc:
                    st.error(str(exc))

    st.markdown("### Workflow History")
    try:
        wf_runs = client.list_project_workflows(project_id)
    except StudioAPIError as exc:
        st.error(str(exc))
        wf_runs = []

    if not wf_runs:
        st.caption("No LangGraph workflow runs started for this project yet.")
    else:
        for run in wf_runs:
            with st.container(border=True):
                st.markdown(
                    f"**Run `{run['id'][:8]}`** (`{run['thread_id']}`) — "
                    f"`{run['status']}` · Stage: `{run.get('current_stage') or '—'}`"
                )
                if run.get("error_message"):
                    st.error(run["error_message"])
                if run["status"] == "INTERRUPTED":
                    wf_notes = st.text_input(
                        "Gate Feedback / Revision Notes",
                        key=f"wf_notes_{run['id']}",
                    )
                    b1, b2, b3 = st.columns(3)
                    if b1.button("Approve & Resume", key=f"wf_app_{run['id']}", type="primary"):
                        try:
                            client.resume_workflow(
                                run["id"],
                                decision="APPROVED",
                                comments=wf_notes.strip() or None,
                            )
                            st.rerun()
                        except StudioAPIError as exc:
                            st.error(str(exc))
                    if b2.button("Request Changes", key=f"wf_chg_{run['id']}"):
                        try:
                            client.resume_workflow(
                                run["id"],
                                decision="CHANGES_REQUESTED",
                                comments=wf_notes.strip() or None,
                            )
                            st.rerun()
                        except StudioAPIError as exc:
                            st.error(str(exc))
                    if b3.button("Cancel Run", key=f"wf_can_{run['id']}"):
                        try:
                            client.cancel_workflow(run["id"])
                            st.rerun()
                        except StudioAPIError as exc:
                            st.error(str(exc))

with tab_research:
    st.subheader("Research Engine")
    with st.form("run_research_form"):
        queries_raw = st.text_area(
            "Custom Search Queries (optional, one per line; defaults to topic-derived queries)",
            height=80,
        )
        seeds_raw = st.text_area(
            "Reference URLs (optional, one per line)",
            height=80,
            placeholder="https://docs.python.org/...",
        )
        r_col1, r_col2 = st.columns(2)
        max_results = r_col1.slider("Max Results per Query", min_value=1, max_value=10, value=5)
        synthesize = r_col2.checkbox("Synthesize Structured Findings with LLM", value=True)
        run_clicked = st.form_submit_button("Run Research", type="primary")
        if run_clicked:
            queries = [line.strip() for line in queries_raw.splitlines() if line.strip()] or None
            seed_urls = [line.strip() for line in seeds_raw.splitlines() if line.strip()] or None
            with st.spinner("Searching, extracting pages, and synthesizing research report..."):
                try:
                    report = client.run_research(
                        project_id,
                        queries=queries,
                        seed_urls=seed_urls,
                        max_results_per_query=max_results,
                        synthesize_with_llm=synthesize,
                    )
                    st.success(
                        f"Research complete: {report['sources_extracted']} extracted, "
                        f"{report['sources_failed']} failed, "
                        f"{report['duplicates_skipped']} duplicates skipped."
                    )
                except StudioAPIError as exc:
                    st.error(str(exc))

    st.markdown("### Grounded Research Findings")
    try:
        findings = client.list_research_findings(project_id)
    except StudioAPIError as exc:
        st.error(str(exc))
        findings = []

    if not findings:
        st.caption("No research findings yet. Run research above to generate grounded findings.")
    else:
        for finding in findings:
            badge = " ⚠️ Contradiction" if finding.get("is_contradiction") else ""
            with st.container(border=True):
                st.markdown(
                    f"**{finding['title']}** — `{finding['category']}` "
                    f"(confidence `{finding['confidence']:.2f}`){badge}"
                )
                st.write(finding["summary"])
                urls = finding.get("source_urls_json", [])
                if urls:
                    st.caption("Sources: " + " | ".join(urls))

    st.markdown("### Discovered Sources")
    try:
        sources = client.list_research_sources(project_id)
    except StudioAPIError as exc:
        st.error(str(exc))
        sources = []

    if not sources:
        st.caption("No sources collected yet.")
    else:
        for src in sources:
            with st.container(border=True):
                st.markdown(
                    f"**[{src['title'] or src['url']}]({src['url']})** "
                    f"(`{src['domain']}` · `{src['provider']}` · `{src['status']}`)"
                )
                if src.get("error_message"):
                    st.caption(f"Extraction note: {src['error_message']}")

with tab_competitors:
    st.subheader("Competitor YouTube Analysis")
    with st.form("run_competitors_form"):
        comp_queries_raw = st.text_area(
            "YouTube Search Queries (optional, one per line; defaults to project topic)",
            height=70,
        )
        comp_urls_raw = st.text_area(
            "Specific YouTube Video URLs (optional, one per line)",
            height=70,
            placeholder="https://www.youtube.com/watch?v=...",
        )
        c_col1, c_col2 = st.columns(2)
        comp_max = c_col1.slider("Max Videos", min_value=1, max_value=15, value=5)
        comp_llm = c_col2.checkbox("Generate Content-Gap Analysis with LLM", value=True)
        if st.form_submit_button("Run Competitor Analysis", type="primary"):
            c_queries = [
                line.strip() for line in comp_queries_raw.splitlines() if line.strip()
            ] or None
            c_urls = [line.strip() for line in comp_urls_raw.splitlines() if line.strip()] or None
            with st.spinner("Collecting public YouTube metadata and analyzing content gaps..."):
                try:
                    comp_report = client.run_competitor_analysis(
                        project_id,
                        queries=c_queries,
                        video_urls=c_urls,
                        max_results=comp_max,
                        analyze_with_llm=comp_llm,
                    )
                    st.success(f"Analyzed {comp_report['videos_analyzed']} competitor videos.")
                    if comp_report.get("gap_analysis"):
                        st.markdown("**Recommended Positioning**")
                        st.write(comp_report["gap_analysis"]["recommended_positioning"])
                except StudioAPIError as exc:
                    st.error(str(exc))

    try:
        competitors = client.list_competitors(project_id)
    except StudioAPIError as exc:
        st.error(str(exc))
        competitors = []

    if not competitors:
        st.caption("No competitor videos analyzed yet.")
    else:
        for vid in competitors:
            with st.container(border=True):
                views = (
                    f"{vid['view_count']:,} views"
                    if vid.get("view_count") is not None
                    else "views n/a"
                )
                st.markdown(
                    f"**[{vid['title']}]({vid['url']})** — {vid.get('channel_name') or 'Unknown'} "
                    f"(`{views}` · `{vid['provider']}`)"
                )
                if vid.get("topics_covered_json"):
                    st.caption("Topics: " + ", ".join(vid["topics_covered_json"]))

with tab_fact_check:
    st.subheader("Evidence-Based Fact Checking")
    with st.form("run_fact_check_form"):
        custom_claims_raw = st.text_area(
            "Additional Claims to Verify (optional, one per line)",
            height=80,
        )
        req_approval = st.checkbox(
            "Create Research Approval Gate (Gate 2) after fact-check",
            value=True,
        )
        if st.form_submit_button("Run Fact Checker", type="primary"):
            custom_claims = [
                line.strip() for line in custom_claims_raw.splitlines() if line.strip()
            ] or None
            with st.spinner("Extracting claims and verifying against project evidence..."):
                try:
                    fc_report = client.run_fact_check(
                        project_id,
                        custom_claims=custom_claims,
                        request_research_approval=req_approval,
                    )
                    st.success(
                        f"Fact-check complete: {fc_report['verified_count']} verified, "
                        f"{fc_report['unsupported_count']} unsupported, "
                        f"{fc_report['conflicting_count']} conflicting, "
                        f"{fc_report['uncertain_count']} uncertain."
                    )
                except StudioAPIError as exc:
                    st.error(str(exc))

    verdict_filter = st.selectbox(
        "Filter Claims by Verdict",
        ["All", "VERIFIED", "UNSUPPORTED", "CONFLICTING", "UNCERTAIN"],
    )
    try:
        claims = client.list_claims(
            project_id,
            verdict=None if verdict_filter == "All" else verdict_filter,
        )
    except StudioAPIError as exc:
        st.error(str(exc))
        claims = []

    if not claims:
        st.caption("No claims audited yet. Run the fact checker after collecting research sources.")
    else:
        for claim in claims:
            with st.container(border=True):
                st.markdown(
                    f"**[{claim['verdict']}]** (risk: `{claim['risk_level']}`, "
                    f"confidence: `{claim['confidence']:.2f}`)"
                )
                st.write(claim["statement"])
                st.caption(f"Rationale: {claim['rationale']}")
                if claim.get("evidence_summary"):
                    st.warning(claim["evidence_summary"])

with tab_script:
    st.subheader("Structured Hinglish Scriptwriter")
    with st.form("generate_script_form"):
        rev_notes = st.text_area(
            "Revision / Style Instructions (optional)",
            height=80,
            placeholder="e.g., Make the hook punchier and expand the Python demo explanation.",
        )
        s_col1, s_col2 = st.columns(2)
        req_res_approval = s_col1.checkbox("Require Approved Research (Gate 2)", value=False)
        req_script_approval = s_col2.checkbox("Create Script Approval Gate (Gate 3)", value=True)
        if st.form_submit_button("Generate Script Version", type="primary"):
            with st.spinner("Generating structured 9-section script from channel guidelines..."):
                try:
                    gen = client.generate_script(
                        project_id,
                        revision_notes=rev_notes.strip() or None,
                        require_approved_research=req_res_approval,
                        request_script_approval=req_script_approval,
                    )
                    st.success(
                        f"Generated Script v{gen['version_number']} "
                        f"({gen['word_count']} words, validation score "
                        f"{gen['validation']['score']}/100)."
                    )
                except StudioAPIError as exc:
                    st.error(str(exc))

    try:
        script_data = client.get_script(project_id)
    except StudioAPIError as exc:
        st.error(str(exc))
        script_data = None

    if not script_data or not script_data.get("versions"):
        st.caption("No script generated yet.")
    else:
        st.markdown(
            f"**{script_data['title']}** — Status: `{script_data['status']}` | "
            f"Current: `v{script_data['current_version']}` | "
            f"Approved: `{script_data.get('approved_version') or 'None'}`"
        )
        for ver in script_data["versions"]:
            val = ver.get("validation_report_json") or {}
            header = (
                f"v{ver['version_number']} · `{ver['status']}` · {ver['word_count']} words · "
                f"~{ver['total_estimated_duration_seconds'] // 60}m "
                f"{ver['total_estimated_duration_seconds'] % 60}s · "
                f"Score: {val.get('score', 'n/a')}/100"
            )
            with st.expander(
                header, expanded=(ver["version_number"] == script_data["current_version"])
            ):
                if val.get("errors"):
                    st.error("Validation errors: " + " | ".join(val["errors"]))
                if val.get("warnings"):
                    st.warning("Warnings: " + " | ".join(val["warnings"]))
                if ver["status"] != "APPROVED" and st.button(
                    f"Approve Script v{ver['version_number']}",
                    key=f"approve_script_v{ver['version_number']}",
                    type="primary",
                ):
                    try:
                        client.approve_script_version(project_id, ver["version_number"])
                        st.success(f"Approved Script v{ver['version_number']}.")
                        st.rerun()
                    except StudioAPIError as exc:
                        st.error(str(exc))
                for sec in ver.get("sections_json", []):
                    st.markdown(
                        f"**{sec.get('title')}** (`{sec.get('section_type')}`, "
                        f"~{sec.get('estimated_duration_seconds', 0)}s)"
                    )
                    st.write(sec.get("narration", ""))
                    if sec.get("visual_instructions"):
                        st.caption(f"Visuals: {sec['visual_instructions']}")

with tab_storyboard:
    st.subheader("Scene-by-Scene Storyboard")
    with st.form("generate_storyboard_form"):
        req_approved_script = st.checkbox(
            "Require Approved Script (Gate 3) before storyboarding",
            value=True,
        )
        if st.form_submit_button("Generate Storyboard Scenes", type="primary"):
            with st.spinner("Breaking approved script into scenes and asset requirements..."):
                try:
                    sb = client.generate_storyboard(
                        project_id,
                        require_approved_script=req_approved_script,
                    )
                    st.success(
                        f"Generated {sb['total_scenes']} scenes with "
                        f"{sb['total_asset_requirements']} asset requirement(s)."
                    )
                except StudioAPIError as exc:
                    st.error(str(exc))

    try:
        scenes = client.list_scenes(project_id)
    except StudioAPIError as exc:
        st.error(str(exc))
        scenes = []

    if not scenes:
        st.caption("No storyboard scenes yet. Approve a script version and generate above.")
    else:
        for scene in scenes:
            with st.container(border=True):
                st.markdown(
                    f"**Scene {scene['scene_number']}: {scene['title']}** — "
                    f"`{scene['visual_type']}` (~{scene['estimated_duration_seconds']}s) · "
                    f"Section: `{scene['related_script_section']}`"
                )
                st.write(scene["narration"])
                if scene.get("on_screen_text"):
                    st.caption(f"On-screen text: {scene['on_screen_text']}")
                if scene.get("camera_or_screen_instructions"):
                    st.caption(f"Camera/Screen: {scene['camera_or_screen_instructions']}")
                assets = scene.get("asset_requirements_json") or []
                if assets:
                    st.caption(
                        "Assets needed: "
                        + " | ".join(f"[{a['asset_type']}] {a['title']}" for a in assets)
                    )

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
