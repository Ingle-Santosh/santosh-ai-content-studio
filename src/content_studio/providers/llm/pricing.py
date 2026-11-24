"""Configurable per-1M-token pricing table for estimated LLM cost tracking.

Local providers (Ollama) are always $0.00.
Cloud pricing entries are conservative estimates for budget enforcement; exact billing
always lives in the cloud provider's dashboard.
"""

# (input_usd_per_1m_tokens, output_usd_per_1m_tokens)
_MODEL_PRICING_PER_1M: dict[str, tuple[float, float]] = {
    "gemini-2.5-flash": (0.15, 0.60),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.0-flash": (0.10, 0.40),
}

_DEFAULT_CLOUD_PRICING_PER_1M: tuple[float, float] = (0.50, 2.00)


def estimate_cost_usd(
    *,
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    if provider.lower() == "ollama":
        return 0.0

    normalized_model = model.lower().strip()
    in_rate, out_rate = _DEFAULT_CLOUD_PRICING_PER_1M
    for prefix, rates in _MODEL_PRICING_PER_1M.items():
        if normalized_model.startswith(prefix):
            in_rate, out_rate = rates
            break

    cost = (prompt_tokens / 1_000_000.0) * in_rate + (completion_tokens / 1_000_000.0) * out_rate
    return round(max(cost, 0.0), 8)
