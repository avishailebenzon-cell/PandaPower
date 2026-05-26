"""
Blocklist of email senders that are NEVER the candidate themselves.

CVs arrive at jobs@pandatech.co.il from many sources:
- Recruitment platforms (jobnet, alljobs, drushim, jobmaster, alljob, talma, jobinfo...)
- Forwarded from PandaTech's internal mailboxes
- Cross-posted from other recruiters / partner agencies

In all these cases, the "From:" email is the intermediary platform, NOT the
candidate. The candidate's REAL email lives inside the CV file itself.

This module is the source of truth for "is this email actually the candidate?"
Used by:
- cv_parse_worker (before overwriting candidate_email with Claude's extraction)
- candidate_creation_worker (defense-in-depth: refuse to dedupe by these emails)
- the historical-data fixup script

Adding more domains: just append to BLOCKED_DOMAINS or BLOCKED_EXACT below.
"""

import re
from typing import Optional


# Exact email addresses we know are never candidates.
# Use this for one-off mailboxes (specific recruiters at your org).
BLOCKED_EXACT: set[str] = {
    # Our own mailboxes (the inboxes that RECEIVE candidate CVs)
    "jobs@pandatech.co.il",
    "recruitment@pandatech.co.il",
    "hr@pandatech.co.il",
    "careers@pandatech.co.il",
    # Known internal recruiters who forward CVs
    # (add per-org as you discover them)
}


# Whole domains we know are intermediaries / job boards / forwarders.
# Any address @ one of these is treated as a sender, not a candidate.
BLOCKED_DOMAINS: set[str] = {
    # Israeli job boards & recruitment platforms
    "alljobs.co.il",
    "alljob.co.il",
    "jobnet.co.il",
    "drushim.co.il",
    "jobmaster.co.il",
    "talma.co.il",
    "jobinfo.co.il",
    "linkedin.com",         # invites/notifications, never a real candidate addr
    "messages.linkedin.com",
    "ethire.co.il",
    "career.co.il",
    "winwin.co.il",
    "machanaim.org.il",
    "jobspot.co.il",
    "jobpoint.co.il",
    "applicantstack.com",
    "lever.co",
    "greenhouse.io",
    "workable.com",
    "comeet.co",
    "smartrecruiters.com",
    "ramat-gan.muni.il",    # municipality forwards
    # Generic role mailboxes that are NEVER the candidate's own address
    # (we match these on the LOCAL-PART, not the domain — see helpers below)
    # 'noreply', 'no-reply', 'donotreply', 'mailer-daemon' handled below
}


# Local-part prefixes that signal "no human reads this mailbox".
# An email like noreply@anything is never a candidate.
BLOCKED_LOCAL_PARTS: set[str] = {
    "noreply",
    "no-reply",
    "donotreply",
    "do-not-reply",
    "mailer-daemon",
    "postmaster",
    "bounce",
    "bounces",
    "notification",
    "notifications",
    "alerts",
    "info",                 # often used by job boards (info@jobnet.co.il)
    "jobs",                 # jobs@somewhere = sender mailbox
    "careers",
    "hr",
    "recruitment",
    "recruiting",
    "talent",
    "applications",
    "candidate",            # candidate@platform is the platform, not the human
    "candidates",
}


_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def is_sender_email(email: Optional[str]) -> bool:
    """Return True if `email` is a known intermediary / sender, NOT a candidate.

    Used by cv_parse to refuse to set candidate_email to something that's
    obviously the platform / recruiter / forwarding mailbox.

    Decision flow:
    1. Empty / malformed → True (treat as not-a-candidate so we skip it)
    2. Listed in BLOCKED_EXACT → True
    3. Domain in BLOCKED_DOMAINS → True
    4. Local-part is a role mailbox (noreply, info, jobs, hr...) → True
    5. Otherwise → False (looks like a real personal email)
    """
    if not email or not isinstance(email, str):
        return True

    email = email.strip().lower()
    if not _EMAIL_RE.match(email):
        # Malformed — better safe than sorry
        return True

    if email in BLOCKED_EXACT:
        return True

    try:
        local, domain = email.split("@", 1)
    except ValueError:
        return True

    if domain in BLOCKED_DOMAINS:
        return True

    # Match subdomains too: messages.linkedin.com → linkedin.com
    for blocked_domain in BLOCKED_DOMAINS:
        if domain.endswith("." + blocked_domain):
            return True

    if local in BLOCKED_LOCAL_PARTS:
        return True

    return False


def is_likely_candidate_email(email: Optional[str]) -> bool:
    """Convenience inverse: True if `email` plausibly belongs to a real candidate."""
    return bool(email) and not is_sender_email(email)
