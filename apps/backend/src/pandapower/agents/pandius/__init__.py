"""Pandius (פנדיוס) — the inbound, candidate-facing WhatsApp agent.

Male counterpart to Pandi. Pandi fields client requests (looking for
candidates); Pandius answers job seekers: collects their basic details, stores
them as a contact with status "מועמד לחברה" (candidate), accepts a CV into the
normal scan pipeline, and tries to surface a relevant open job.
"""

from .conversation_engine import PandiusConversationEngine

__all__ = ["PandiusConversationEngine"]
