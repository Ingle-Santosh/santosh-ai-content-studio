import json
import re
from typing import Any

from pydantic import BaseModel, ValidationError

from content_studio.providers.llm.types import StructuredOutputError

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def extract_json_payload(raw_text: str) -> Any:
    """Extract and decode a JSON object or array from raw LLM text output."""
    stripped = raw_text.strip()
    if not stripped:
        raise json.JSONDecodeError("Empty response text", raw_text, 0)

    # 1. Direct parse
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # 2. Markdown fenced block
    fence_match = _FENCE_RE.search(stripped)
    if fence_match:
        candidate = fence_match.group(1).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # 3. Balanced outermost object/array slice
    first_obj = stripped.find("{")
    last_obj = stripped.rfind("}")
    if first_obj != -1 and last_obj > first_obj:
        candidate = stripped[first_obj : last_obj + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    first_arr = stripped.find("[")
    last_arr = stripped.rfind("]")
    if first_arr != -1 and last_arr > first_arr:
        candidate = stripped[first_arr : last_arr + 1]
        return json.loads(candidate)

    raise json.JSONDecodeError("No valid JSON payload found in LLM output", stripped, 0)


def parse_structured_output[T: BaseModel](raw_text: str, response_model: type[T]) -> T:
    """Parse raw model text and validate strictly against a Pydantic model."""
    try:
        payload = extract_json_payload(raw_text)
    except json.JSONDecodeError as exc:
        raise StructuredOutputError(
            f"Failed to parse JSON for {response_model.__name__}: {exc}"
        ) from exc

    try:
        return response_model.model_validate(payload)
    except ValidationError as exc:
        raise StructuredOutputError(
            f"Output failed Pydantic validation for {response_model.__name__}: {exc}"
        ) from exc
