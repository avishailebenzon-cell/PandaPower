"""Anthropic token-usage tracking.

Single source of truth for "where are our Claude credits going?". Every Claude
call (CV parse, agent matching, Pandi conversation, …) records one row in the
`llm_usage` table via `record_usage()`. The admin dashboard then aggregates by
stage / model / day.

Design notes:
- `record_usage()` is BEST-EFFORT. It never raises — billing visibility must
  never break the pipeline. If the table is missing (migration 009 not applied)
  it degrades silently.
- Pricing is approximate (public list prices, USD per 1M tokens) and only meant
  for relative comparison between stages, not for accounting. Override per-model
  in PRICING below as prices change.
"""
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# USD per 1,000,000 tokens, (input, output). Matched by substring against the
# model id, longest-match-wins, so "claude-haiku-4-5" beats a generic "haiku".
PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4":   (15.0, 75.0),
    "claude-opus":     (15.0, 75.0),
    "claude-sonnet-4": (3.0, 15.0),
    "claude-sonnet":   (3.0, 15.0),
    "claude-haiku-4":  (1.0, 5.0),
    "claude-haiku":    (0.8, 4.0),
}
_DEFAULT_PRICE = (3.0, 15.0)  # unknown model → assume Sonnet-class


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Approximate USD cost for one call. Never raises."""
    try:
        m = (model or "").lower()
        price = _DEFAULT_PRICE
        best_len = 0
        for key, val in PRICING.items():
            if key in m and len(key) > best_len:
                price, best_len = val, len(key)
        in_rate, out_rate = price
        return (input_tokens / 1_000_000.0) * in_rate + (output_tokens / 1_000_000.0) * out_rate
    except Exception:
        return 0.0


async def record_usage(
    stage: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    supabase_client: Optional[Any] = None,
) -> None:
    """Persist one Claude call's token usage. Best-effort, never raises.

    Args:
        stage: logical pipeline stage, e.g. 'cv_parse', 'agent_match',
            'pandi_conversation', 'pandi_moderation'.
        model: the Claude model id used.
        input_tokens / output_tokens: from the API response's usage block.
        supabase_client: optional existing client; one is created if omitted.
    """
    try:
        input_tokens = int(input_tokens or 0)
        output_tokens = int(output_tokens or 0)
        total = input_tokens + output_tokens
        cost = estimate_cost(model, input_tokens, output_tokens)

        client = supabase_client
        if client is None:
            from pandapower.core.supabase import get_supabase_client
            client = await get_supabase_client()

        await client.table("llm_usage").insert(
            {
                "stage": stage,
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total,
                "estimated_cost_usd": round(cost, 6),
                "units": 1,
            }
        ).execute()
    except Exception as e:
        # Visibility must never break the pipeline. Degrade silently.
        logger.debug(f"record_usage skipped for stage={stage} model={model}: {e}")


# Default $ per ConvertAPI conversion if not configured. The Growth plan is
# 15,000 conversions/mo; set the REAL plan price via system_settings
# 'convertapi.cost_per_conversion' for accurate numbers.
DEFAULT_CONVERTAPI_COST_PER_CONVERSION = 0.005


async def record_convertapi_usage(
    cost_per_conversion: Optional[float] = None,
    units: int = 1,
    supabase_client: Optional[Any] = None,
) -> None:
    """Record one (or more) ConvertAPI conversions as a cost row. Best-effort.

    ConvertAPI isn't token-based, so we store the $ directly in
    estimated_cost_usd and the number of conversions in `units`.
    """
    try:
        client = supabase_client
        if client is None:
            from pandapower.core.supabase import get_supabase_client
            client = await get_supabase_client()

        per = cost_per_conversion
        if per is None:
            try:
                from pandapower.integrations.convertapi_client import get_convertapi_config
                cfg = await get_convertapi_config(client)
                per = float(cfg.get("cost_per_conversion") or DEFAULT_CONVERTAPI_COST_PER_CONVERSION)
            except Exception:
                per = DEFAULT_CONVERTAPI_COST_PER_CONVERSION

        await client.table("llm_usage").insert(
            {
                "stage": "convertapi_extract",
                "model": "convertapi",
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "estimated_cost_usd": round(per * units, 6),
                "units": units,
            }
        ).execute()
    except Exception as e:
        logger.debug(f"record_convertapi_usage skipped: {e}")
