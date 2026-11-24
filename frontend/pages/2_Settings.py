import streamlit as st

from content_studio.config.settings import settings
from frontend.api_client import StudioAPIClient, StudioAPIError

st.set_page_config(
    page_title="Settings — Santosh Analytics Studio",
    page_icon="⚙️",
    layout="wide",
)

client = StudioAPIClient(base_url=settings.API_BASE_URL)

st.title("⚙️ Model Selection, Channel Guidelines & Settings")
st.caption(
    "Choose your active LLM provider/model and configure Santosh Analytics channel guidelines"
)

_CLOUD_PROVIDER_PRESETS: dict[str, tuple[str, list[str], str]] = {
    "gemini": (
        "Google Gemini API",
        ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.5-flash-lite", "gemini-2.0-flash"],
        "https://generativelanguage.googleapis.com/v1beta",
    ),
    "openai": (
        "OpenAI API",
        ["gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini"],
        "https://api.openai.com/v1",
    ),
    "anthropic": (
        "Anthropic Claude API",
        ["claude-sonnet-4-20250514", "claude-3-7-sonnet-latest", "claude-3-5-haiku-latest"],
        "https://api.anthropic.com/v1",
    ),
    "openai_compatible": (
        "Custom OpenAI-Compatible (OpenRouter / Groq / DeepSeek / etc.)",
        [
            "deepseek-chat",
            "llama-3.3-70b-versatile",
            "openai/gpt-4.1-mini",
            "anthropic/claude-sonnet-4",
            "google/gemini-2.5-flash",
        ],
        "https://openrouter.ai/api/v1",
    ),
}

_ALL_TASKS: list[tuple[str, str]] = [
    ("topic_strategy", "Topic Strategy (Lightweight)"),
    ("research_synthesis", "Research Synthesis (Important)"),
    ("fact_check", "Fact Checking (Important)"),
    ("scriptwriting", "Scriptwriting (Important)"),
    ("storyboard", "Storyboard (Important)"),
    ("asset_planning", "Asset Planning (Lightweight)"),
    ("code_generation", "Code / Diagram Generation"),
    ("qa_review", "QA Review (Lightweight)"),
    ("metadata", "YouTube Metadata (Lightweight)"),
    ("general", "General / Competitor Analysis (Lightweight)"),
]
_DEFAULT_IMPORTANT_TASKS = ["research_synthesis", "fact_check", "scriptwriting", "storyboard"]

st.subheader("🤖 AI Model & Hybrid Provider Selection")
try:
    llm_status = client.get_llm_status()
except StudioAPIError as exc:
    st.error(f"Could not load LLM status from FastAPI backend: {exc}")
    llm_status = None

if llm_status is not None:
    providers_by_name = {p["provider"]: p for p in llm_status.get("providers", [])}
    ollama_models = [
        m for m in providers_by_name.get("ollama", {}).get("models", []) if m != "qwen2.5-coder:14b"
    ]
    current_ollama = llm_status.get("ollama_default_model") or settings.OLLAMA_DEFAULT_MODEL
    if current_ollama == "qwen2.5-coder:14b":
        current_ollama = "qwen3.5:9b"
    if current_ollama and current_ollama not in ollama_models:
        ollama_models.insert(0, current_ollama)
    for suggested in ("qwen3.5:9b", "qwen2.5:7b", "qwen2.5:3b", "llama3.2:3b", "phi4-mini"):
        if suggested not in ollama_models:
            ollama_models.append(suggested)
    ollama_options = [*ollama_models, "Custom..."]

    current_fast = llm_status.get("ollama_fast_model") or ""
    fast_options = ["(Same as Default Local Model)", *ollama_models, "Custom..."]

    current_cloud_provider = llm_status.get("cloud_provider") or "gemini"
    if current_cloud_provider not in _CLOUD_PROVIDER_PRESETS:
        current_cloud_provider = "gemini"
    current_cloud_model = llm_status.get("cloud_default_model") or ""
    current_cloud_tasks = list(llm_status.get("cloud_tasks") or [])

    if llm_status["local_only"]:
        active_mode_label = "Local Only (Ollama)"
        default_mode_idx = 0
    elif llm_status.get("prefer_cloud_default"):
        active_mode_label = f"Cloud All ({current_cloud_provider})"
        default_mode_idx = 2
    else:
        active_mode_label = f"Hybrid Tiered (Local + {current_cloud_provider})"
        default_mode_idx = 1

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Active Mode", active_mode_label)
    m2.metric("Local Model", current_ollama)
    m3.metric("Cloud Model", f"{current_cloud_provider}/{current_cloud_model or 'n/a'}")
    m4.metric(
        "Global Spend / Cap",
        f"${llm_status['current_global_spend_usd']:.4f} / ${llm_status['max_budget_usd']:.2f}",
    )

    # Provider picker outside form so model presets & default base URL update immediately
    provider_keys = list(_CLOUD_PROVIDER_PRESETS.keys())
    selected_cloud_provider = st.selectbox(
        "Powerful Cloud Provider (for Important Steps or Full Cloud Mode)",
        provider_keys,
        index=provider_keys.index(current_cloud_provider),
        format_func=lambda k: _CLOUD_PROVIDER_PRESETS[k][0],
    )
    _, cloud_presets, default_cloud_url = _CLOUD_PROVIDER_PRESETS[selected_cloud_provider]
    cloud_model_options = list(cloud_presets)
    if (
        selected_cloud_provider == current_cloud_provider
        and current_cloud_model
        and current_cloud_model not in cloud_model_options
    ):
        cloud_model_options.insert(0, current_cloud_model)
    cloud_model_options.append("Custom...")

    with st.form("llm_model_selection_form"):
        mode_choices = [
            "Local Only — Free Small Ollama Models for All Steps",
            "Hybrid Tiered (Recommended) — Small Local + Powerful Cloud for Important Steps",
            "Cloud All — Powerful Cloud Model for Every Step (with Local Fallback)",
        ]
        selected_mode = st.radio(
            "Routing Mode",
            mode_choices,
            index=default_mode_idx,
        )

        col_l, col_c = st.columns(2)
        with col_l:
            st.markdown("**Small / Fast Local Models (Ollama)**")
            ollama_idx = (
                ollama_options.index(current_ollama) if current_ollama in ollama_options else 0
            )
            chosen_ollama = st.selectbox(
                "Default Local Model",
                ollama_options,
                index=ollama_idx,
                help="Recommended small models: qwen2.5:3b, llama3.2:3b, phi4-mini, qwen3.5:9b.",
            )
            custom_ollama = st.text_input(
                "Custom Default Local Model (if 'Custom...' selected)",
                placeholder="e.g., qwen2.5:3b",
            )
            fast_idx = fast_options.index(current_fast) if current_fast in fast_options else 0
            chosen_fast = st.selectbox(
                "Fast Local Model (for QA & Asset Planning)",
                fast_options,
                index=fast_idx,
            )
            custom_fast = st.text_input(
                "Custom Fast Local Model (if 'Custom...' selected)",
                placeholder="e.g., llama3.2:3b",
            )

        with col_c:
            st.markdown(
                f"**Powerful Cloud Model ({_CLOUD_PROVIDER_PRESETS[selected_cloud_provider][0]})**"
            )
            c_idx = (
                cloud_model_options.index(current_cloud_model)
                if (
                    selected_cloud_provider == current_cloud_provider
                    and current_cloud_model in cloud_model_options
                )
                else 0
            )
            chosen_cloud_model = st.selectbox(
                "Cloud Model",
                cloud_model_options,
                index=c_idx,
                help="Choose a preset or select 'Custom...' to enter any valid model ID.",
            )
            custom_cloud_model = st.text_input(
                "Custom Cloud Model ID (if 'Custom...' selected)",
                placeholder="e.g., gpt-4.1, claude-sonnet-4-20250514, gemini-2.5-pro",
            )
            key_hint = (
                "API key active (leave blank to keep current key)"
                if (
                    selected_cloud_provider == current_cloud_provider
                    and llm_status.get("cloud_api_key_configured")
                )
                else f"Paste {selected_cloud_provider.upper()} API key / token"
            )
            cloud_api_key = st.text_input(
                "Cloud API Key / Token (runtime memory only — never saved to Git/DB)",
                type="password",
                placeholder=key_hint,
            )
            base_url_val = (
                llm_status.get("cloud_base_url") or default_cloud_url
                if selected_cloud_provider == current_cloud_provider
                else default_cloud_url
            )
            cloud_base_url = st.text_input(
                "Cloud API Base URL",
                value=base_url_val,
                help="For OpenRouter/Groq/DeepSeek, select Custom OpenAI-Compatible & set URL.",
            )

        task_keys = [k for k, _ in _ALL_TASKS]
        task_labels = dict(_ALL_TASKS)
        default_selected_tasks = current_cloud_tasks or _DEFAULT_IMPORTANT_TASKS
        selected_cloud_tasks = st.multiselect(
            "Important Steps Routed to Powerful Cloud Model (used in Hybrid Tiered Mode)",
            options=task_keys,
            default=[t for t in default_selected_tasks if t in task_keys],
            format_func=lambda k: task_labels.get(k, k),
        )

        g1, g2 = st.columns(2)
        max_budget = g1.number_input(
            "Global Budget Cap (USD)",
            min_value=0.0,
            max_value=500.0,
            value=float(llm_status.get("max_budget_usd", 0.0)),
            step=0.5,
        )
        timeout_sec = g2.number_input(
            "LLM Timeout (seconds)",
            min_value=15.0,
            max_value=900.0,
            value=float(llm_status.get("llm_timeout_seconds", 180.0)),
            step=15.0,
        )

        if st.form_submit_button("Save Model Configuration", type="primary"):
            is_local_only = selected_mode.startswith("Local Only")
            is_cloud_all = selected_mode.startswith("Cloud All")
            final_ollama = (
                custom_ollama.strip() if chosen_ollama == "Custom..." else chosen_ollama
            ) or current_ollama
            if chosen_fast == "(Same as Default Local Model)":
                final_fast = ""
            elif chosen_fast == "Custom...":
                final_fast = custom_fast.strip()
            else:
                final_fast = chosen_fast
            final_cloud_model = (
                custom_cloud_model.strip()
                if chosen_cloud_model == "Custom..."
                else chosen_cloud_model
            )
            try:
                updated_llm = client.update_llm_config(
                    local_only=is_local_only,
                    prefer_cloud_default=is_cloud_all,
                    cloud_tasks=[] if is_local_only else selected_cloud_tasks,
                    cloud_provider=selected_cloud_provider,
                    cloud_default_model=final_cloud_model,
                    cloud_base_url=cloud_base_url.strip() or default_cloud_url,
                    cloud_api_key=cloud_api_key.strip() or None,
                    ollama_default_model=final_ollama,
                    ollama_fast_model=final_fast,
                    max_budget_usd=float(max_budget),
                    llm_timeout_seconds=float(timeout_sec),
                )
                st.success(
                    f"Saved! Local: `{updated_llm['ollama_default_model']}` | "
                    f"Cloud: `{updated_llm['cloud_provider']}/{updated_llm['cloud_default_model']}`"
                )
                if not is_local_only and not updated_llm.get("cloud_api_key_configured"):
                    st.warning(
                        "Cloud mode is enabled, but no API key is configured yet — "
                        "requests will fall back to local Ollama until you enter a key."
                    )
                if not is_local_only and updated_llm["max_budget_usd"] <= 0.0:
                    st.warning(
                        "Global Budget Cap is $0.00 — increase it above $0.00 (and set a "
                        "Project Budget in Project Workspace) to allow cloud calls."
                    )
            except StudioAPIError as exc:
                st.error(str(exc))

    with st.expander("Provider Health & Per-Step Task Routing Table"):
        for prov in llm_status.get("providers", []):
            badge = "Available" if prov["available"] else f"Unavailable ({prov.get('error')})"
            kind = "Cloud" if prov["is_cloud"] else "Local"
            st.write(f"- **{prov['provider']}** ({kind}): `{badge}`")
            if prov.get("models"):
                st.caption("Models: " + ", ".join(prov["models"][:12]))
        st.json(llm_status.get("routing_table", {}))

st.divider()

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
st.subheader("System Paths & Endpoints (Read-Only)")
st.write(f"- **Backend API**: `{settings.API_BASE_URL}`")
st.write(f"- **Ollama Endpoint**: `{settings.OLLAMA_BASE_URL}`")
st.write(f"- **Cloud Provider**: `{settings.CLOUD_LLM_PROVIDER}` (`{settings.GEMINI_BASE_URL}`)")
st.write(f"- **Artifact Root**: `{settings.resolved_projects_dir}`")
