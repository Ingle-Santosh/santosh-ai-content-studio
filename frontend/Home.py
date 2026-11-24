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
    st.write(f"- **Backend**: FastAPI (`{settings.API_BASE_URL}`)")
    st.write(f"- **Database**: Local SQLite (`{settings.resolved_data_dir / 'content_studio.db'}`)")
    st.write(f"- **Primary Inference**: Ollama (`{settings.OLLAMA_BASE_URL}`)")
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
