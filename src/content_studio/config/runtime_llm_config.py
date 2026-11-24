import json
import logging
from pathlib import Path
from typing import Any

from content_studio.config.settings import Settings

logger = logging.getLogger(__name__)

_RUNTIME_CONFIG_FILENAME = "llm_runtime_config.json"

# Strictly non-secret settings allowed to persist in data/llm_runtime_config.json.
# API keys are NEVER written to this file.
_PERSISTED_FIELDS: tuple[str, ...] = (
    "LOCAL_ONLY",
    "PREFER_CLOUD_DEFAULT",
    "CLOUD_TASKS",
    "CLOUD_LLM_PROVIDER",
    "CLOUD_BASE_URL",
    "CLOUD_DEFAULT_MODEL",
    "OLLAMA_DEFAULT_MODEL",
    "OLLAMA_WRITING_MODEL",
    "OLLAMA_FAST_MODEL",
    "GEMINI_DEFAULT_MODEL",
    "OPENAI_DEFAULT_MODEL",
    "ANTHROPIC_DEFAULT_MODEL",
    "MAX_BUDGET_USD",
    "LLM_TIMEOUT_SECONDS",
)


def runtime_config_path(app_settings: Settings) -> Path:
    return app_settings.resolved_data_dir / _RUNTIME_CONFIG_FILENAME


def save_runtime_llm_config(app_settings: Settings) -> Path:
    """Persist non-secret LLM model/routing preferences so they survive server reloads."""
    path = runtime_config_path(app_settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {field: getattr(app_settings, field) for field in _PERSISTED_FIELDS}
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(path)
    return path


def apply_runtime_llm_config(app_settings: Settings) -> bool:
    """Load persisted non-secret LLM model/routing preferences onto app_settings if present."""
    path = runtime_config_path(app_settings)
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return False
    except (OSError, ValueError) as exc:
        logger.warning("Ignoring unreadable runtime LLM config at %s: %s", path, exc)
        return False

    for field in _PERSISTED_FIELDS:
        if field in data:
            setattr(app_settings, field, data[field])
    return True
