"""Admin endpoints for Anthropic token-usage / cost visibility.

Reads the llm_usage table (populated by integrations.usage_tracker) and returns
aggregates so the admin can see exactly which pipeline stage and which model is
spending Claude credits.

  GET /admin/usage/summary?days=7   - totals + per-stage + per-model + daily series
"""
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from pandapower.core.supabase import get_supabase_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/usage", tags=["admin-usage"])

# Cap how many rows we pull into memory for a single summary request.
_FETCH_CAP = 100_000

# Human-readable Hebrew labels for known stages (frontend falls back to the raw key).
STAGE_LABELS = {
    "cv_parse": "ניתוח קורות חיים",
    "agent_match": "התאמת מועמדים",
    "pandi_conversation": "סוכן Pandi (שיחות)",
    "pandi_moderation": "Pandi — סינון תוכן",
    "unknown": "לא מסווג",
}


@router.get("/summary")
async def usage_summary(
    days: int = Query(7, ge=1, le=90),
    supabase_client=Depends(get_supabase_client),
) -> dict:
    """Aggregate llm_usage over the last `days` days.

    Returns totals plus breakdowns by stage, by model, and a per-day series.
    Aggregation is done in Python (Supabase REST has no GROUP BY), bounded by
    _FETCH_CAP rows. If the cap is hit, `truncated` is true.
    """
    try:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        resp = (
            await supabase_client.table("llm_usage")
            .select("stage,model,input_tokens,output_tokens,total_tokens,estimated_cost_usd,created_at")
            .gte("created_at", since)
            .order("created_at", desc=True)
            .limit(_FETCH_CAP)
            .execute()
        )
        rows = resp.data or []
        truncated = len(rows) >= _FETCH_CAP

        def _blank():
            return {"calls": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost_usd": 0.0}

        totals = _blank()
        by_stage: dict[str, dict] = defaultdict(_blank)
        by_model: dict[str, dict] = defaultdict(_blank)
        by_day: dict[str, dict] = defaultdict(_blank)

        for r in rows:
            it = int(r.get("input_tokens") or 0)
            ot = int(r.get("output_tokens") or 0)
            tt = int(r.get("total_tokens") or (it + ot))
            cost = float(r.get("estimated_cost_usd") or 0.0)
            stage = r.get("stage") or "unknown"
            model = r.get("model") or "unknown"
            day = (r.get("created_at") or "")[:10]  # YYYY-MM-DD

            for bucket in (totals, by_stage[stage], by_model[model], by_day[day]):
                bucket["calls"] += 1
                bucket["input_tokens"] += it
                bucket["output_tokens"] += ot
                bucket["total_tokens"] += tt
                bucket["cost_usd"] += cost

        def _stage_list():
            out = []
            for key, v in by_stage.items():
                item = dict(v)
                item["stage"] = key
                item["label"] = STAGE_LABELS.get(key, key)
                item["cost_usd"] = round(item["cost_usd"], 4)
                out.append(item)
            return sorted(out, key=lambda x: x["cost_usd"], reverse=True)

        def _model_list():
            out = []
            for key, v in by_model.items():
                item = dict(v)
                item["model"] = key
                item["cost_usd"] = round(item["cost_usd"], 4)
                out.append(item)
            return sorted(out, key=lambda x: x["cost_usd"], reverse=True)

        def _day_list():
            out = []
            for key, v in by_day.items():
                item = dict(v)
                item["day"] = key
                item["cost_usd"] = round(item["cost_usd"], 4)
                out.append(item)
            return sorted(out, key=lambda x: x["day"])

        totals["cost_usd"] = round(totals["cost_usd"], 4)

        return {
            "days": days,
            "since": since,
            "truncated": truncated,
            "totals": totals,
            "by_stage": _stage_list(),
            "by_model": _model_list(),
            "by_day": _day_list(),
        }

    except Exception as e:
        logger.error(f"Usage summary failed: {e}", exc_info=True)
        # If the table doesn't exist yet, return an empty-but-valid shape so the
        # dashboard renders a friendly "no data" state instead of erroring.
        msg = str(e).lower()
        if "llm_usage" in msg and ("does not exist" in msg or "not find" in msg or "relation" in msg):
            return {
                "days": days,
                "since": None,
                "truncated": False,
                "totals": {"calls": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost_usd": 0.0},
                "by_stage": [],
                "by_model": [],
                "by_day": [],
                "note": "טבלת llm_usage לא קיימת עדיין — הרץ migration 009 או POST /admin/setup/migrations",
            }
        raise HTTPException(status_code=500, detail=str(e))
