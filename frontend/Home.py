import streamlit as st

from content_studio.config.settings import settings
from frontend.api_client import StudioAPIClient, StudioAPIError

st.set_page_config(
    page_title="Santosh Analytics Studio",
    page_icon="🎬",
    layout="wide",
)

client = StudioAPIClient(base_url=settings.API_BASE_URL)

st.title("🎬 Santosh Analytics — AI Content Studio")
st.caption("Local-First Production Platform for Technical Education")

st.sidebar.header("System Controls")
if st.sidebar.button("Check Backend Health"):
    try:
        health = client.get_health()
        st.sidebar.success(f"Connected: {health['status']}")
        st.sidebar.json(health)
    except StudioAPIError as exc:
        st.sidebar.error(str(exc))

try:
    metrics = client.get_system_metrics()
except StudioAPIError:
    metrics = None

if metrics is not None:
    by_status = metrics.get("projects_by_status") or {}
    in_progress = sum(
        by_status.get(k, 0)
        for k in ("RESEARCHING", "SCRIPTING", "STORYBOARDING", "GENERATING_ASSETS")
    )
    awaiting_review = by_status.get("AWAITING_APPROVAL", 0)
    completed = by_status.get("COMPLETED", 0)
    kpi_cols = st.columns(6)
    kpi_cols[0].metric("Total Projects", metrics.get("total_projects", 0))
    kpi_cols[1].metric("In Progress", in_progress)
    kpi_cols[2].metric("Awaiting Approval", awaiting_review)
    kpi_cols[3].metric("Completed", completed)
    kpi_cols[4].metric("Pending Approvals", metrics.get("pending_approvals", 0))
    kpi_cols[5].metric(
        "LLM Spend (USD)",
        f"${metrics.get('total_estimated_cost_usd', 0.0):.4f}",
        help=(
            f"{metrics.get('total_llm_calls', 0)} calls · "
            f"{metrics.get('total_tokens', 0):,} tokens · "
            f"avg {metrics.get('avg_llm_latency_ms', 0.0):.0f} ms"
        ),
    )

st.divider()

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("Start New Video Project")
    with st.form("new_project_form", clear_on_submit=True):
        topic = st.text_input(
            "Video Topic",
            placeholder="e.g., RAG vs CAG vs MAG: Architectural Trade-offs",
        )
        title = st.text_input(
            "Short Title (Optional)",
            placeholder="Defaults to the video topic if left blank",
        )
        duration = st.slider("Target Duration (Minutes)", min_value=5, max_value=60, value=15)
        language = st.selectbox("Narration Language", ["Hinglish", "English"])
        audience = st.selectbox(
            "Audience Level",
            ["Beginner", "Intermediate (Data/AI Engineers)", "Advanced"],
            index=1,
        )
        opt_col1, opt_col2 = st.columns(2)
        include_code_demo = opt_col1.checkbox("Include Code Demo", value=True)
        include_animations = opt_col2.checkbox("Include HTML Animations", value=True)

        submitted = st.form_submit_button("Create Project", type="primary")
        if submitted:
            if len(topic.strip()) < 3:
                st.warning("Please enter a topic with at least 3 characters.")
            else:
                try:
                    created = client.create_project(
                        topic=topic.strip(),
                        title=title.strip() or None,
                        duration_minutes=duration,
                        language=language,
                        audience_level=audience,
                        include_code_demo=include_code_demo,
                        include_animations=include_animations,
                    )
                    st.success(f"Project created: '{created['title']}' (ID: `{created['id']}`)")
                except StudioAPIError as exc:
                    st.error(str(exc))

with col2:
    st.subheader("System Configuration")
    try:
        llm_live = client.get_llm_status()
    except StudioAPIError:
        llm_live = None
    st.write(f"- **Backend**: FastAPI (`{settings.API_BASE_URL}`)")
    st.write(f"- **Database**: Local SQLite (`{settings.resolved_data_dir / 'content_studio.db'}`)")
    st.write(f"- **Primary Local Inference**: Ollama (`{settings.OLLAMA_BASE_URL}`)")
    if llm_live is not None:
        st.write(f"- **Active Local Model**: `{llm_live.get('ollama_default_model')}`")
        st.write(
            f"- **Cloud Provider / Model**: "
            f"`{llm_live.get('cloud_provider')}/{llm_live.get('cloud_default_model')}` "
            f"(key configured: `{llm_live.get('cloud_api_key_configured')}`)"
        )
        st.write(f"- **Local-Only Mode**: `{llm_live.get('local_only')}`")
        st.write(f"- **LLM Timeout**: `{llm_live.get('llm_timeout_seconds')}s`")
    else:
        st.write(f"- **Default Model**: `{settings.OLLAMA_DEFAULT_MODEL}`")
        st.write(f"- **Local-Only Mode**: `{settings.LOCAL_ONLY}`")

st.divider()
st.subheader("Projects")

try:
    projects = client.list_projects()
except StudioAPIError as exc:
    st.info(f"Start the FastAPI backend to load projects. ({exc})")
    projects = []

if not projects:
    st.caption("No projects yet. Create your first technical video project above.")
else:
    for project in projects:
        cfg = project.get("config", {})
        with st.container(border=True):
            row_left, row_right = st.columns([4, 1])
            with row_left:
                st.markdown(f"**{project['title']}** — `{project['status']}`")
                st.caption(
                    f"Topic: {project['topic']} | "
                    f"{cfg.get('duration_minutes', 15)} min | "
                    f"{cfg.get('language', 'Hinglish')} | "
                    f"{cfg.get('audience_level', 'Intermediate')}"
                )
            with row_right:
                if st.button("Delete", key=f"del_{project['id']}"):
                    try:
                        client.delete_project(project["id"])
                        st.rerun()
                    except StudioAPIError as exc:
                        st.error(str(exc))
