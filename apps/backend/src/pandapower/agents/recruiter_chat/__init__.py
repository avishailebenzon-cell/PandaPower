"""Shared conversation engine for the recruiter chat agents (Tal & Elad).

Both Tal (initial screening, talks with candidates) and Elad (placements, talks
with clients) run identical machinery over the recruiter_conversations /
recruiter_messages tables — only the persona and the WhatsApp instance differ.
This package holds that shared engine so the two agents stay in lock-step.
"""
