"""Shared company knowledge for every PandaPower agent.

Every agent (Tal, Elad, Pandi, Dana) must describe פנדה-טק the same, correct way
and must never invent facts. This module is the single source of truth for:

  • COMPANY_PROFILE  — who PandaTech is (engineering + outsourcing, not placement).
  • FACILITY_FACTS   — the *only* approved answers about specific defense sites.

Inject these into each agent's system prompt so the messaging stays consistent.
"""

# Who PandaTech is — injected into every agent's system prompt.
# NOTE: PandaTech is an OUTSOURCING / engineering company, NOT a placement
# ("השמה") company. An employee is hired *by* PandaTech and works on PandaTech's
# behalf inside the projects of PandaTech's defense clients.
COMPANY_PROFILE = """--- מי זו פנדה-טק (חובה להכיר, אסור לסטות מזה) ---
פנדה-טק היא חברת הנדסה בתחום הביטחוני (ולא חברת השמה!). החברה מגייסת עובדים לעבוד
*אצלה ומטעמה*, ומציבה אותם בפרויקטים אצל הלקוחות הביטחוניים שלה. כלומר: העובד הוא
עובד פנדה-טק בלבד — כל תנאי השכר והתנאים הסוציאליים הם של פנדה-טק, וכולם תנאי הייטק.

עובדות על החברה (אפשר לשתף בגאווה, אך בלי להגזים):
- חברה ותיקה — קיימת מעל 20 שנה, עם חוסן פיננסי והזמנות עבודה לשנים רבות קדימה.
- עוסקת בליבת הפרויקטים הביטחוניים בישראל ומחוצה לה.
- בעלת לקוחות אסטרטגיים רבים ושותפה בפרויקטים לאומיים מרכזיים וחשובים.

אם מועמד שואל "איפה אעבוד / אצל מי אהיה מועסק" — ההבהרה היא תמיד: אתה עובד פנדה-טק,
כל התנאים הם של פנדה-טק, ומטעמה תוצב בפרויקט אצל לקוח.
*לעולם* אל תתאר/י את פנדה-טק כ"חברת השמה" או "חברת כוח אדם"."""


# Approved facts about specific defense sites/organizations. Agents must answer
# ONLY from this list and never invent details. Anything not here → say it can be
# detailed in a face-to-face meeting, and the person is welcome to check online.
FACILITY_FACTS = """--- מענה על ארגונים/מפעלים ספציפיים (אסור להמציא!) ---
ענה/י אך ורק לפי הרשימה הזו. אל תמציא/י פרטים שאינם כאן.
- מל"מ / מב"ת / מל"ט — אלה מפעלים השייכים לתעשייה האווירית, ופנדה-טק עובדת איתם
  בשיתוף פעולה.
- מפעל תומר — מפעל ביטחוני; נוכל לפרט עליו בהמשך בפגישה פרונטלית.
- רפאל — שני מרכזי פיתוח ביטחוני בצפון הארץ: בחיפה ובאזור כרמיאל.
- "פרויקט בדרום" — נוכל לענות על כך בפגישה פרונטלית; מדובר בעבודה באזור יבנה.
לכל ארגון אחר שאינו ברשימה — אפשר לציין שניתן יהיה לפרט בפגישה פרונטלית, ושהמועמד
מוזמן גם לבדוק באינטרנט לגבי הארגון הספציפי. בכל מקרה — חשוב להדגיש שהעבודה היא בפנדה-טק."""


# Operators can append extra, live-editable company knowledge through the admin
# UI (System Settings → "פרופיל החברה"). It is stored in system_settings under
# this key as a plain-text string and appended to the shared block at runtime,
# so updates take effect without a redeploy. The hardcoded blocks above are the
# read-only baseline; this is the editable layer on top.
COMPANY_PROFILE_EXTRA_KEY = "company_profile.extra"


def render_company_block(extra: str = "") -> str:
    """Return the full shared company block: baseline profile + facility facts,
    plus any operator-added content. Pass the value loaded from settings as
    ``extra`` (empty string when there is none)."""
    block = f"{COMPANY_PROFILE}\n\n{FACILITY_FACTS}"
    extra = (extra or "").strip()
    if extra:
        block += "\n\n--- מידע נוסף על החברה (נוסף ע\"י הצוות) ---\n" + extra
    return block


async def load_company_extra(supabase) -> str:
    """Load the operator-added company content from system_settings.

    Never raises — returns "" if the key is missing or on any error, so the
    agents keep working with the baseline block."""
    try:
        res = await supabase.table("system_settings").select(
            "setting_value"
        ).eq("setting_key", COMPANY_PROFILE_EXTRA_KEY).limit(1).execute()
        if res.data:
            val = res.data[0].get("setting_value")
            # Tolerate both the plain-text convention and a {"value": ...} blob.
            if isinstance(val, dict):
                return str(val.get("value") or "")
            return str(val or "")
    except Exception:
        pass
    return ""
