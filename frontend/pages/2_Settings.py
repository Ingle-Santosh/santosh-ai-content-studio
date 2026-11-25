import streamlit as st

from content_studio.config.settings import settings
from frontend.api_client import StudioAPIClient, StudioAPIError

st.set_page_config(
    page_title="Model Registry & Settings — Santosh Analytics Studio",
    page_icon="⚙️",
    layout="wide",
)

client = StudioAPIClient(base_url=settings.API_BASE_URL)

st.title("⚙️ Model Registry, Hybrid Routing & Channel Settings")
st.caption(
    "Register local or cloud API models (OpenRouter, Groq, Gemini, OpenAI, Claude, Ollama) "
    "and assign small local models to easy steps and powerful models to important steps."
)

_ALL_TASKS: list[tuple[str, str]] = [
    ("topic_strategy", "Topic Strategy (Easy / Local)"),
    ("research_synthesis", "Research Synthesis (Important)"),
    ("fact_check", "Fact Checking (Important)"),
    ("scriptwriting", "Scriptwriting — Hinglish (Important)"),
    ("storyboard", "Storyboard (Important)"),
    ("asset_planning", "Asset Planning (Easy / Local)"),
    ("code_generation", "Code / Diagram Generation"),
    ("qa_review", "QA Review (Easy / Local)"),
    ("metadata", "YouTube Metadata (Easy / Local)"),
    ("general", "General / Competitors (Easy / Local)"),
]
_DEFAULT_IMPORTANT_TASKS = ["research_synthesis", "fact_check", "scriptwriting", "storyboard"]

try:
    llm_status = client.get_llm_status()
    registry_payload = client.list_registered_models()
    registered_models = list(registry_payload.get("items", []))
    presets = list(registry_payload.get("presets", []))
except StudioAPIError as exc:
    st.error(f"Could not connect to FastAPI backend: {exc}")
    st.stop()

tab_registry, tab_routing, tab_guidelines = st.tabs(
    [
        "🗂️ Model Registry",
        "⚡ Hybrid Task Routing",
        "🎬 Channel Guidelines & Info",
    ]
)

with tab_registry:
    st.subheader(
        "Register a New Model (Local Ollama, OpenRouter Free/Cheap, Groq, Gemini, OpenAI, Claude)"
    )
    preset_labels = ["(Blank — Custom Entry)", *[p["label"] for p in presets]]
    chosen_preset_label = st.selectbox(
        "Quick-Fill from Recommended Preset (optional)",
        preset_labels,
        help="Pick an OpenRouter free/cheap, Groq free, local Ollama, or direct API preset.",
    )
    selected_preset = next((p for p in presets if p["label"] == chosen_preset_label), None)

    provider_list = [
        "openrouter",
        "groq",
        "ollama",
        "gemini",
        "openai",
        "anthropic",
        "openai_compatible",
    ]
    tier_list = ["local_small", "cloud_free", "cloud_powerful"]

    default_prov = selected_preset["provider"] if selected_preset else "openrouter"
    default_tier = selected_preset["tier"] if selected_preset else "cloud_free"
    default_name = selected_preset["label"] if selected_preset else ""
    default_model_id = selected_preset["model_id"] if selected_preset else ""
    default_base_url = (
        selected_preset["base_url"] if selected_preset else "https://openrouter.ai/api/v1"
    )
    default_in_cost = float(selected_preset["input_cost_per_1m"]) if selected_preset else 0.0
    default_out_cost = float(selected_preset["output_cost_per_1m"]) if selected_preset else 0.0
    default_notes = selected_preset["notes"] if selected_preset else ""

    preset_idx = preset_labels.index(chosen_preset_label)

    with st.form("register_model_form", clear_on_submit=False):
        r1, r2 = st.columns(2)
        reg_name = r1.text_input(
            "Display Name",
            value=default_name,
            placeholder="e.g., OpenRouter Llama 3.3 70B Free",
            key=f"reg_name_{preset_idx}",
        )
        reg_provider = r2.selectbox(
            "Provider",
            provider_list,
            index=provider_list.index(default_prov) if default_prov in provider_list else 0,
            key=f"reg_prov_{preset_idx}",
        )

        r3, r4 = st.columns(2)
        reg_model_id = r3.text_input(
            "Model ID (exact provider API model slug)",
            value=default_model_id,
            placeholder="e.g., meta-llama/llama-3.3-70b-instruct:free or qwen2.5:3b",
            key=f"reg_mid_{preset_idx}",
        )
        reg_base_url = r4.text_input(
            "API Base URL",
            value=default_base_url,
            placeholder="https://openrouter.ai/api/v1",
            key=f"reg_url_{preset_idx}",
        )

        r5, r6 = st.columns([2, 1])
        reg_api_key = r5.text_input(
            "API Key / Token (not required for local Ollama; stored in gitignored local vault)",
            type="password",
            placeholder="Paste OpenRouter / Groq / Gemini / OpenAI / Anthropic API token",
            key=f"reg_key_{preset_idx}",
        )
        reg_tier = r6.selectbox(
            "Model Tier",
            tier_list,
            index=tier_list.index(default_tier) if default_tier in tier_list else 0,
            help="'local_small'=local, 'cloud_free'=$0 API, 'cloud_powerful'=paid API.",
            key=f"reg_tier_{preset_idx}",
        )

        c1, c2, c3 = st.columns([1, 1, 2])
        reg_in_cost = c1.number_input(
            "Input $/1M tokens",
            min_value=0.0,
            max_value=200.0,
            value=default_in_cost,
            step=0.05,
            key=f"reg_in_{preset_idx}",
        )
        reg_out_cost = c2.number_input(
            "Output $/1M tokens",
            min_value=0.0,
            max_value=200.0,
            value=default_out_cost,
            step=0.05,
            key=f"reg_out_{preset_idx}",
        )
        reg_notes = c3.text_input(
            "Notes (optional)", value=default_notes, key=f"reg_notes_{preset_idx}"
        )

        if st.form_submit_button("Register Model", type="primary"):
            if len(reg_name.strip()) < 2 or not reg_model_id.strip():
                st.warning("Please enter both a Display Name and a Model ID.")
            else:
                try:
                    created = client.register_model(
                        name=reg_name.strip(),
                        provider=reg_provider,
                        model_id=reg_model_id.strip(),
                        base_url=reg_base_url.strip() or None,
                        api_key=reg_api_key.strip() or None,
                        tier=reg_tier,
                        input_cost_per_1m=float(reg_in_cost),
                        output_cost_per_1m=float(reg_out_cost),
                        notes=reg_notes.strip() or None,
                    )
                    st.success(
                        f"Registered `{created['name']}` "
                        f"(`{created['provider']}/{created['model_id']}`)."
                    )
                    st.rerun()
                except StudioAPIError as exc:
                    st.error(str(exc))

    st.divider()
    st.subheader(f"Registered Models ({len(registered_models)})")
    if not registered_models:
        st.info(
            "No models registered yet. Pick a preset above (e.g., Local Qwen 2.5 3B and "
            "OpenRouter Llama 3.3 70B Free) and click Register Model."
        )
    else:
        for item in registered_models:
            key_badge = (
                f"🔑 `{item['api_key_hint']}`"
                if item.get("has_api_key")
                else ("🟢 Local (no key needed)" if not item["is_cloud"] else "⚠️ No API key set")
            )
            cost_badge = (
                "FREE ($0)"
                if (item["input_cost_per_1m"] == 0.0 and item["output_cost_per_1m"] == 0.0)
                else f"${item['input_cost_per_1m']:.2f} / ${item['output_cost_per_1m']:.2f} per 1M"
            )
            with st.container(border=True):
                left, right = st.columns([4, 2])
                with left:
                    st.markdown(
                        f"**{item['name']}** — `{item['provider']}` / `{item['model_id']}` "
                        f"· `{item['tier']}` · {cost_badge}"
                    )
                    st.caption(f"Endpoint: `{item['base_url']}` · {key_badge}")
                    if item.get("notes"):
                        st.caption(item["notes"])
                with right:
                    b1, b2 = st.columns(2)
                    if b1.button("Test", key=f"test_reg_{item['id']}"):
                        with st.spinner(f"Testing {item['name']}..."):
                            try:
                                res = client.test_registered_model(item["id"])
                                if res["ok"]:
                                    preview = res.get("reply_preview") or ""
                                    st.success(f"OK ({res['latency_ms']}ms): {preview}")
                                else:
                                    st.error(f"Failed: {res.get('error')}")
                            except StudioAPIError as exc:
                                st.error(str(exc))
                    if b2.button("Delete", key=f"del_reg_{item['id']}"):
                        try:
                            client.delete_registered_model(item["id"])
                            st.rerun()
                        except StudioAPIError as exc:
                            st.error(str(exc))

with tab_routing:
    st.subheader("Select Models from Registry for Easy vs. Important Steps")
    reg_by_id = {m["id"]: m for m in registered_models}

    small_id = llm_status.get("small_model_id")
    powerful_id = llm_status.get("powerful_model_id")
    small_label = (
        f"{reg_by_id[small_id]['name']}"
        if small_id and small_id in reg_by_id
        else f"ollama/{llm_status.get('ollama_default_model')}"
    )
    powerful_label = (
        f"{reg_by_id[powerful_id]['name']}"
        if powerful_id and powerful_id in reg_by_id
        else f"{llm_status.get('cloud_provider')}/{llm_status.get('cloud_default_model')}"
    )

    m1, m2, m3, m4 = st.columns(4)
    if llm_status["local_only"]:
        mode_badge = "Local Only"
        default_mode_idx = 0
    elif llm_status.get("prefer_cloud_default"):
        mode_badge = "Cloud All"
        default_mode_idx = 2
    else:
        mode_badge = "Hybrid Tiered"
        default_mode_idx = 1

    m1.metric("Active Mode", mode_badge)
    m2.metric("Easy Steps Model", small_label[:28])
    m3.metric("Important Steps Model", powerful_label[:28])
    m4.metric(
        "Global Spend / Cap",
        f"${llm_status['current_global_spend_usd']:.4f} / ${llm_status['max_budget_usd']:.2f}",
    )

    reg_options_none = ["(Use Default Local Ollama)"] + [m["id"] for m in registered_models]
    reg_options_cloud = ["(None — Fallback to Local)"] + [m["id"] for m in registered_models]

    def _fmt_reg(opt_id: str) -> str:
        if opt_id not in reg_by_id:
            return opt_id
        m = reg_by_id[opt_id]
        tag = (
            "LOCAL"
            if not m["is_cloud"]
            else ("FREE API" if m["input_cost_per_1m"] == 0 else "PAID API")
        )
        return f"[{tag}] {m['name']} ({m['provider']}/{m['model_id']})"

    providers_by_name = {p["provider"]: p for p in llm_status.get("providers", [])}
    ollama_models = [
        m for m in providers_by_name.get("ollama", {}).get("models", []) if m != "qwen2.5-coder:14b"
    ]
    cur_ollama = llm_status.get("ollama_default_model") or settings.OLLAMA_DEFAULT_MODEL
    if cur_ollama == "qwen2.5-coder:14b":
        cur_ollama = "qwen2.5:3b"
    if cur_ollama not in ollama_models:
        ollama_models.insert(0, cur_ollama)

    with st.form("hybrid_routing_form"):
        mode_choices = [
            "Local Only — Free Local Ollama Models for All Steps",
            "Hybrid Tiered (Recommended) — Local Small + Registry Cloud for Important Steps",
            "Cloud All — Powerful Registered Model for Every Step (with Local Fallback)",
        ]
        selected_mode = st.radio("Routing Mode", mode_choices, index=default_mode_idx)

        s_col1, s_col2 = st.columns(2)
        small_idx = reg_options_none.index(small_id) if small_id in reg_options_none else 0
        chosen_small_id = s_col1.selectbox(
            "Small / Easy Steps Model (from Registry)",
            reg_options_none,
            index=small_idx,
            format_func=_fmt_reg,
        )
        pow_idx = reg_options_cloud.index(powerful_id) if powerful_id in reg_options_cloud else 0
        chosen_powerful_id = s_col2.selectbox(
            "Important / Powerful Steps Model (from Registry)",
            reg_options_cloud,
            index=pow_idx,
            format_func=_fmt_reg,
        )

        task_keys = [k for k, _ in _ALL_TASKS]
        task_labels = dict(_ALL_TASKS)
        current_cloud_tasks = list(llm_status.get("cloud_tasks") or []) or _DEFAULT_IMPORTANT_TASKS
        selected_cloud_tasks = st.multiselect(
            "Important Steps Routed to Powerful Model (Hybrid Tiered Mode)",
            options=task_keys,
            default=[t for t in current_cloud_tasks if t in task_keys],
            format_func=lambda k: task_labels.get(k, k),
        )

        b_col1, b_col2, b_col3 = st.columns(3)
        fallback_ollama = b_col1.selectbox(
            "Fallback Local Ollama Model",
            ollama_models,
            index=ollama_models.index(cur_ollama) if cur_ollama in ollama_models else 0,
        )
        max_budget = b_col2.number_input(
            "Global Paid Budget Cap (USD)",
            min_value=0.0,
            max_value=500.0,
            value=float(llm_status.get("max_budget_usd", 0.0)),
            step=0.5,
            help="Free tier models (OpenRouter :free, Groq, Ollama) run even at $0.00.",
        )
        timeout_sec = b_col3.number_input(
            "LLM Timeout (seconds)",
            min_value=15.0,
            max_value=900.0,
            value=float(llm_status.get("llm_timeout_seconds", 180.0)),
            step=15.0,
        )

        if st.form_submit_button("Save Routing Configuration", type="primary"):
            is_local_only = selected_mode.startswith("Local Only")
            is_cloud_all = selected_mode.startswith("Cloud All")
            try:
                client.update_llm_config(
                    local_only=is_local_only,
                    prefer_cloud_default=is_cloud_all,
                    cloud_tasks=[] if is_local_only else selected_cloud_tasks,
                    small_model_id=""
                    if chosen_small_id == "(Use Default Local Ollama)"
                    else chosen_small_id,
                    powerful_model_id=""
                    if chosen_powerful_id == "(None — Fallback to Local)"
                    else chosen_powerful_id,
                    ollama_default_model=fallback_ollama,
                    max_budget_usd=float(max_budget),
                    llm_timeout_seconds=float(timeout_sec),
                )
                st.success("Saved Hybrid Routing configuration!")
                st.rerun()
            except StudioAPIError as exc:
                st.error(str(exc))

    with st.expander("Provider Health & Default Routing Table"):
        for prov in llm_status.get("providers", []):
            badge = "Available" if prov["available"] else f"Unavailable ({prov.get('error')})"
            kind = "Cloud" if prov["is_cloud"] else "Local"
            st.write(f"- **{prov['provider']}** ({kind}): `{badge}`")
        st.json(llm_status.get("routing_table", {}))

with tab_guidelines:
    try:
        active = client.get_active_guideline()
    except StudioAPIError as exc:
        st.error(f"Could not load channel guidelines: {exc}")
        active = None

    if active is not None:
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
            explanation_style = st.text_input(
                "Explanation Style", value=g.get("explanation_style", "")
            )
            presentation_style = st.text_input(
                "Presentation Style", value=g.get("presentation_style", "")
            )
            visual_standards = st.text_input(
                "Visual Standards", value=g.get("visual_standards", "")
            )
            tutorial_approach = st.text_input(
                "Tutorial Approach", value=g.get("tutorial_approach", "")
            )
            creator_bio_note = st.text_input(
                "Creator Bio Note", value=g.get("creator_bio_note", "")
            )
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

            if st.form_submit_button("Save Channel Guidelines", type="primary"):
                core_topics = [t.strip() for t in core_topics_raw.split(",") if t.strip()]
                extra_rules = [
                    line.strip() for line in extra_rules_raw.splitlines() if line.strip()
                ]
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
    st.write(f"- **Artifact Root**: `{settings.resolved_projects_dir}`")
