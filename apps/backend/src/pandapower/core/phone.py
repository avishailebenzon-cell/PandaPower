"""Phone-number normalization for WhatsApp / Green API.

One place that understands every shape a number arrives in — +972, 0049…,
00972, 0xx national, bare 9-digit mobile, with spaces / dashes / parentheses —
and turns it into the two canonical forms the rest of the system needs:

    to_international("058-666-5248")  -> "972586665248"
    to_chat_id("058-666-5248")       -> "972586665248@c.us"

It is Israel-first (the recruitment domain is Israeli) but tolerant of foreign
numbers: anything that already looks international is passed through within
Green API's own 7–15 digit bound rather than rejected.

Why this exists: the old `normalize_phone` merely stripped non-digits, so a
malformed number like "+9726665248" (missing the "58" mobile prefix) sailed
straight through to Green API, which rejected it with HTTP 400 while the
message was silently marked "stored but not sent". `is_valid()` now catches
that class of error *before* we ever call Green API, so the UI can show a
real reason instead of a silent drop.
"""

from __future__ import annotations

import re
from typing import Optional

_NON_DIGITS = re.compile(r"\D")

# Israeli country code, no '+'.
_IL_CC = "972"


def _digits_only(raw: Optional[str]) -> str:
    """Every digit in the input, in order. '+972 (58) 666-5248' -> '97258...'."""
    return _NON_DIGITS.sub("", raw or "")


def normalize_phone(raw: Optional[str]) -> str:
    """Backwards-compatible digits-only form, for tolerant matching/storage.

    Kept so existing callers (and stored `candidate_phone` values) keep working.
    Prefer :func:`to_international` for anything that talks to Green API."""
    return _digits_only(raw)


def to_international(raw: Optional[str]) -> Optional[str]:
    """Canonical international digits-only form (no '+', no separators).

    Returns ``None`` only when the input has no digits at all. The shape rules,
    applied in order:

      * drop a leading ``00`` international access prefix
      * already ``972…``                         -> keep
      * national ``0XXXXXXXXX``                  -> ``972`` + drop the leading 0
      * bare Israeli mobile ``5XXXXXXXX`` (9 d.) -> prepend ``972``
      * bare Israeli landline ``[2-489]XXXXXXX`` (8 d.) -> prepend ``972``
      * anything else                            -> assume already international
    """
    digits = _digits_only(raw)
    if not digits:
        return None
    if digits.startswith("00"):
        digits = digits[2:]
    if not digits:
        return None
    if digits.startswith(_IL_CC):
        return digits
    if digits.startswith("0"):
        return _IL_CC + digits[1:]
    if len(digits) == 9 and digits[0] == "5":
        return _IL_CC + digits
    if len(digits) == 8 and digits[0] in "23489":
        return _IL_CC + digits
    return digits


def is_valid(raw: Optional[str]) -> bool:
    """True iff the number canonicalizes to a plausible WhatsApp recipient.

    Israeli numbers (``972…``) are checked strictly — mobile is ``972`` + 9
    digits starting with 5, landline is ``972`` + 8 digits. Foreign numbers
    fall back to Green API's own bound of 7–15 digits."""
    intl = to_international(raw)
    if not intl:
        return False
    if intl.startswith(_IL_CC):
        national = intl[len(_IL_CC):]
        if national.startswith("5"):
            return len(national) == 9          # mobile:   972 + 5XXXXXXXX
        return len(national) == 8 and national[:1] in "23489"  # landline
    return 7 <= len(intl) <= 15


def to_chat_id(raw: Optional[str]) -> Optional[str]:
    """Green API chatId (``<international-digits>@c.us``), or ``None`` if the
    number isn't a valid WhatsApp recipient. This is the only function that
    should build a ``@c.us`` string."""
    if not is_valid(raw):
        return None
    return f"{to_international(raw)}@c.us"


def chat_id_to_phone(chat_id: Optional[str]) -> str:
    """Extract the digits-only phone from a Green API chatId.

    Handles ``9725…@c.us`` (individual) and ``…@g.us`` / ``…@lid`` shapes by
    taking everything before the first ``@``."""
    if not chat_id:
        return ""
    return (chat_id.split("@", 1)[0] or "").strip()


def phones_match(a: Optional[str], b: Optional[str]) -> bool:
    """Tolerant equality across formats — compares the national tail so that
    ``+972-58-666-5248``, ``0586665248`` and ``972586665248`` all match."""
    ia, ib = to_international(a), to_international(b)
    if not ia or not ib:
        return False
    if ia == ib:
        return True
    return ia[-9:] == ib[-9:]
