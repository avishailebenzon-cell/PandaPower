"""Per-conversation debounce for recruiter auto-replies (Tal / Elad).

When a candidate fires several WhatsApp messages in quick succession, each one
arrives as its own webhook. Without debouncing the agent would reply to every
single message. Instead we record each inbound immediately, then arm a short
quiet-window timer; only the LAST message in the burst actually generates a
reply — and since `generate_reply` reads the full history, that one reply
naturally covers everything the candidate just said.

Mechanism: a per-conversation version counter. Every inbound bumps the version
and schedules a task that sleeps `DEBOUNCE_SECONDS` and then replies *only if*
its version is still the latest. Earlier tasks wake to a stale version and quietly
bow out — so no task is ever cancelled mid-reply.

In-process state. This is safe because the web app runs a single worker (see the
scheduler-consolidation note); a multi-worker deployment would need a shared
store (e.g. Redis) instead.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

logger = logging.getLogger(__name__)

# How long the candidate must be quiet before the agent replies. Tuned so a
# person typing 2-3 quick messages gets a single consolidated answer.
DEBOUNCE_SECONDS = 8.0

# conversation key -> latest inbound version seen
_versions: dict[str, int] = {}


def schedule_reply(recruiter: str, conv_id: str, delay: float = DEBOUNCE_SECONDS) -> None:
    """Arm a debounced auto-reply for this conversation.

    Call this right after recording an inbound message. If more inbounds arrive
    within `delay` seconds, only the last one results in a reply."""
    key = f"{recruiter}:{conv_id}"
    version = _versions.get(key, 0) + 1
    _versions[key] = version

    async def _run() -> None:
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        # A newer message arrived during the quiet window — let its task reply.
        if _versions.get(key) != version:
            return
        from pandapower.agents.recruiter_chat.engine import RecruiterChatEngine

        try:
            await RecruiterChatEngine(recruiter).generate_reply(UUID(conv_id))
        except Exception as e:
            logger.error(
                f"{recruiter} debounced reply failed for {conv_id}: {e}", exc_info=True
            )

    try:
        asyncio.create_task(_run())
    except RuntimeError as e:
        # No running loop (shouldn't happen in the web app) — fall back to inline.
        logger.error(f"Could not schedule debounced reply for {key}: {e}")
