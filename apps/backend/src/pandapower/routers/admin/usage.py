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
                "note": "טבלת llm_usage לא קיימת עדיין — הרץ migration 011 או POST /admin/setup/migrations",
            }
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/matching-config")
async def get_matching_config(supabase_client=Depends(get_supabase_client)):
    """Read the hybrid-matching depth (Claude top-N) — the cost/coverage knob."""
    try:
        r = await supabase_client.table("system_settings").select("setting_value").eq(
            "setting_key", "matching.claude_top_n"
        ).limit(1).execute()
        n = 8
        if r.data and r.data[0].get("setting_value") is not None:
            n = int(float(str(r.data[0]["setting_value"]).strip().strip('"')))
        return {"claude_top_n": n}
    except Exception:
        return {"claude_top_n": 8}


@router.post("/matching-config")
async def set_matching_config(body: dict, supabase_client=Depends(get_supabase_client)):
    """Set the hybrid-matching depth. Higher = broader Claude coverage, more $."""
    try:
        n = max(1, min(100, int(body.get("claude_top_n", 8))))
        existing = await supabase_client.table("system_settings").select("id").eq(
            "setting_key", "matching.claude_top_n"
        ).limit(1).execute()
        if existing.data:
            await supabase_client.table("system_settings").update(
                {"setting_value": str(n)}
            ).eq("setting_key", "matching.claude_top_n").execute()
        else:
            await supabase_client.table("system_settings").insert(
                {"setting_key": "matching.claude_top_n", "setting_value": str(n)}
            ).execute()
        return {"claude_top_n": n}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/unit-costs")
async def unit_costs(
    days: int = Query(0, ge=0, le=3650, description="Window in days; 0 = all-time"),
    supabase_client=Depends(get_supabase_client),
):
    """Average cost per CV scan and per match, plus the cost breakdown.

    - cost per CV  = (cv_parse $ + convertapi_extract $) / # CV parses
    - cost per match = agent_match $ / # match evaluations

    Returns 0s gracefully if the llm_usage table doesn't exist yet.
    """
    try:
        q = supabase_client.table("llm_usage").select(
            "stage, estimated_cost_usd, units"
        )
        if days and days > 0:
            since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            q = q.gte("created_at", since)

        # Paginate to be safe on large tables.
        rows, off = [], 0
        while True:
            b = (await q.range(off, off + 999).execute()).data or []
            rows.extend(b)
            if len(b) < 1000 or len(rows) >= _FETCH_CAP:
                break
            off += 1000

        agg: dict[str, dict] = defaultdict(lambda: {"cost": 0.0, "units": 0})
        for r in rows:
            st = r.get("stage") or "unknown"
            agg[st]["cost"] += float(r.get("estimated_cost_usd") or 0.0)
            agg[st]["units"] += int(r.get("units") or 1)

        cv_parse_cost = agg["cv_parse"]["cost"]
        cv_parse_n = agg["cv_parse"]["units"]
        convertapi_cost = agg["convertapi_extract"]["cost"]
        convertapi_n = agg["convertapi_extract"]["units"]
        match_cost = agg["agent_match"]["cost"]
        match_n = agg["agent_match"]["units"]

        # A CV "scan" = one CV parse; its full cost includes the ConvertAPI
        # extraction that fed it. Spread total convertapi cost across parses.
        cv_total_cost = cv_parse_cost + convertapi_cost
        cost_per_cv = (cv_total_cost / cv_parse_n) if cv_parse_n else 0.0
        cost_per_match = (match_cost / match_n) if match_n else 0.0

        total_cost = sum(v["cost"] for v in agg.values())

        return {
            "days": days or "all",
            "cost_per_cv_usd": round(cost_per_cv, 5),
            "cost_per_match_usd": round(cost_per_match, 5),
            "counts": {
                "cv_parses": cv_parse_n,
                "convertapi_conversions": convertapi_n,
                "match_evaluations": match_n,
            },
            "components": {
                "cv_parse_usd": round(cv_parse_cost, 4),
                "convertapi_usd": round(convertapi_cost, 4),
                "agent_match_usd": round(match_cost, 4),
                "other_usd": round(total_cost - cv_parse_cost - convertapi_cost - match_cost, 4),
            },
            "total_cost_usd": round(total_cost, 4),
        }
    except Exception as e:
        msg = str(e).lower()
        if "llm_usage" in msg and ("does not exist" in msg or "not find" in msg or "relation" in msg):
            return {
                "days": days or "all",
                "cost_per_cv_usd": 0.0,
                "cost_per_match_usd": 0.0,
                "counts": {"cv_parses": 0, "convertapi_conversions": 0, "match_evaluations": 0},
                "components": {"cv_parse_usd": 0.0, "convertapi_usd": 0.0, "agent_match_usd": 0.0, "other_usd": 0.0},
                "total_cost_usd": 0.0,
                "note": "טבלת llm_usage לא קיימת עדיין — הרץ migration 011.",
            }
        logger.error(f"unit-costs failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
