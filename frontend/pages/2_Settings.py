import streamlit as st

from content_studio.config.settings import settings
from frontend.api_client import StudioAPIClient, StudioAPIError

st.set_page_config(
    page_title="Settings — Santosh Analytics Studio",
    page_icon="⚙️",
    layout="wide",
)

client = StudioAPIClient(base_url=settings.API_BASE_URL)

st.title("⚙️ Channel Guidelines & System Settings")
st.caption("Configure reusable Santosh Analytics channel preferences persisted in SQLite")

try:
    active = client.get_active_guideline()
except StudioAPIError as exc:
    st.error(f"Could not load channel guidelines from FastAPI backend: {exc}")
    st.stop()

g = active.get("guidelines_json", {})

with st.form("channel_guidelines_form"):
    st.subheader(f"Active Guideline Profile (`{active['slug']}`)")
    channel_name = st.text_input("Channel Name", value=active.get("channel_name", ""))
    audience = st.text_input("Target Audience", value=g.get("audience", ""))
    col1, col2 = st.columns(2)
    narration_language = col1.text_input(
        "Narration Language", value=g.get("narration_language", "Hinglish")
    )
    technical_terminology = col2.text_input(
        "Technical Terminology", value=g.get("technical_terminology", "English")
    )
    explanation_style = st.text_input("Explanation Style", value=g.get("explanation_style", ""))
    presentation_style = st.text_input("Presentation Style", value=g.get("presentation_style", ""))
    visual_standards = st.text_input("Visual Standards", value=g.get("visual_standards", ""))
    tutorial_approach = st.text_input("Tutorial Approach", value=g.get("tutorial_approach", ""))
    creator_bio_note = st.text_input("Creator Bio Note", value=g.get("creator_bio_note", ""))
    publishing_mode = st.text_input(
        "Publishing Mode", value=g.get("publishing_mode", "Manual review and upload")
    )
    core_topics_raw = st.text_input(
        "Core Topics (comma-separated)",
        value=", ".join(g.get("core_topics", [])),
    )
    extra_rules_raw = st.text_area(
        "Additional Rules (one per line)",
        value="\n".join(g.get("extra_rules", [])),
        height=100,
    )

    saved = st.form_submit_button("Save Channel Guidelines", type="primary")
    if saved:
        core_topics = [t.strip() for t in core_topics_raw.split(",") if t.strip()]
        extra_rules = [line.strip() for line in extra_rules_raw.splitlines() if line.strip()]
        payload = {
            "audience": audience.strip(),
            "narration_language": narration_language.strip(),
            "technical_terminology": technical_terminology.strip(),
            "explanation_style": explanation_style.strip(),
            "presentation_style": presentation_style.strip(),
            "core_topics": core_topics,
            "visual_standards": visual_standards.strip(),
            "tutorial_approach": tutorial_approach.strip(),
            "creator_bio_note": creator_bio_note.strip(),
            "publishing_mode": publishing_mode.strip(),
            "extra_rules": extra_rules,
        }
        try:
            updated = client.upsert_guideline(
                active["slug"],
                channel_name=channel_name.strip() or "Santosh Analytics",
                guidelines=payload,
                is_active=True,
            )
            st.success(f"Saved channel guidelines (`{updated['slug']}`).")
        except StudioAPIError as exc:
            st.error(str(exc))

st.divider()
st.subheader("Hybrid LLM Providers & Task Routing")
if st.button("Check LLM Providers Status"):
    try:
        llm_status = client.get_llm_status()
        m1, m2, m3 = st.columns(3)
        m1.metric("Local-Only Mode", str(llm_status["local_only"]))
        m2.metric("Global Budget Cap", f"${llm_status['max_budget_usd']:.2f}")
        m3.metric("Global Spend", f"${llm_status['current_global_spend_usd']:.4f}")

        st.markdown("**Providers**")
        for prov in llm_status.get("providers", []):
            badge = "Available" if prov["available"] else f"Unavailable ({prov.get('error')})"
            kind = "Cloud" if prov["is_cloud"] else "Local"
            st.write(f"- **{prov['provider']}** ({kind}): `{badge}`")
            if prov.get("models"):
                st.caption("Installed models: " + ", ".join(prov["models"][:10]))

        st.markdown("**Default Task Routing Table**")
        st.json(llm_status.get("routing_table", {}))
    except StudioAPIError as exc:
        st.error(str(exc))

st.divider()
st.subheader("Runtime Configuration (Read-Only)")
st.write(f"- **Local-Only Mode**: `{settings.LOCAL_ONLY}`")
st.write(f"- **Global Budget Cap**: `${settings.MAX_BUDGET_USD:.2f}`")
st.write(f"- **Ollama Endpoint**: `{settings.OLLAMA_BASE_URL}` (`{settings.OLLAMA_DEFAULT_MODEL}`)")
st.write(
    f"- **Cloud Provider**: `{settings.CLOUD_LLM_PROVIDER}` (`{settings.GEMINI_DEFAULT_MODEL}`)"
)
st.write(f"- **Artifact Root**: `{settings.resolved_projects_dir}`")
