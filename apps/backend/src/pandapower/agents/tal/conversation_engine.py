"""Tal conversation engine — thin wrapper over the shared RecruiterChatEngine.

Tal's logic is identical to Elad's apart from persona + WhatsApp instance, so
the implementation lives in agents/recruiter_chat/engine.py. This module keeps
the historical import path (`TalConversationEngine`, `normalize_phone`) working.
"""

from __future__ import annotations

from pandapower.agents.recruiter_chat.engine import (  # noqa: F401
    RecruiterChatEngine,
    normalize_phone,
)


class TalConversationEngine(RecruiterChatEngine):
    """Initial-screening recruiter chat (recruiter='tal')."""

    def __init__(self):
        super().__init__(recruiter="tal")
