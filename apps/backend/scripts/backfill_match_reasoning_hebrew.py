"""One-time backfill: translate existing match_reasoning text to Hebrew.

New matches are generated in Hebrew (see agent_matching.py prompt change), but
matches created before that change still hold English match_reasoning text that
is displayed in the admin screens (CarmitPage etc.). This script finds every
match whose reasoning is still (mostly) English and rewrites it in Hebrew via
Claude, preserving the meaning. Rows already in Hebrew are skipped.

Usage:
    python -m scripts.backfill_match_reasoning_hebrew          # apply
    python -m scripts.backfill_match_reasoning_hebrew --dry-run  # preview only

NOTE: requires Anthropic API access. If the account is over its usage limit the
translation calls will fail — run this once the limit is lifted.
"""

import asyncio
import sys

from pandapower.core.config import settings
from pandapower.core.supabase import get_supabase_client
from pandapower.integrations.claude_api import AnthropicClient

DRY_RUN = "--dry-run" in sys.argv

TRANSLATE_SYSTEM = (
    "You are a professional Hebrew translator for a recruitment system. "
    "Translate the recruiter-facing match explanation into natural, professional "
    "Hebrew. Keep proper nouns, technologies, and acronyms (e.g. Python, AWS, BSc) "
    "as-is. Preserve any leading symbols like ✓ ✗ ⚠ ~. Return ONLY the translated "
    "text, with no preamble, quotes, or commentary."
)


def _is_hebrew(text: str) -> bool:
    """True if the text already contains a meaningful amount of Hebrew."""
    if not text:
        return True  # nothing to translate
    hebrew = sum(1 for ch in text if "֐" <= ch <= "׿")
    return hebrew >= max(3, len(text) * 0.1)


async def _translate(client: AnthropicClient, text: str) -> str:
    data = await client._make_request_with_retry(
        messages=[{"role": "user", "content": text}],
        system=TRANSLATE_SYSTEM,
    )
    parts = data.get("content", []) or []
    out = "".join(p.get("text", "") for p in parts if p.get("type") == "text").strip()
    return out or text


async def main():
    sb = await get_supabase_client()
    client = AnthropicClient(settings.ANTHROPIC_API_KEY)
    client.usage_stage = "backfill_translate"
    client.model = "claude-haiku-4-5"  # translation is cheap; use the small model

    # Page through all matches that have reasoning.
    rows = []
    offset = 0
    while True:
        r = (
            await sb.table("matches")
            .select("id, match_reasoning")
            .neq("match_reasoning", None)
            .range(offset, offset + 999)
            .execute()
        )
        batch = r.data or []
        rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000

    to_translate = [
        row for row in rows
        if (row.get("match_reasoning") or "").strip() and not _is_hebrew(row["match_reasoning"])
    ]
    print(f"Total matches with reasoning: {len(rows)}")
    print(f"English (need translation): {len(to_translate)}")
    if DRY_RUN:
        for row in to_translate[:10]:
            print(f"  - {row['id']}: {row['match_reasoning'][:80]}...")
        print("(dry-run, no changes written)")
        await client.close()
        return

    done = 0
    for row in to_translate:
        try:
            he = await _translate(client, row["match_reasoning"])
            await sb.table("matches").update({"match_reasoning": he}).eq("id", row["id"]).execute()
            done += 1
            if done % 10 == 0:
                print(f"  translated {done}/{len(to_translate)}")
        except Exception as e:
            print(f"  FAILED {row['id']}: {e}")

    print(f"Done. Translated {done}/{len(to_translate)} match reasonings to Hebrew.")
    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
