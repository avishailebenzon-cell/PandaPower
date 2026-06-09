#!/usr/bin/env python3
"""Set the Panda-Tech branding for the formatted-CV generator.

Embeds the logo image as a base64 *data URI* directly in system_settings, so the
CV renderer (ConvertAPI html→pdf) never needs to fetch an external URL — the
logo always shows and never expires. Also sets contact phone / website / email.

Usage:
    python scripts/set_panda_logo.py /path/to/panda_logo.png
    python scripts/set_panda_logo.py ~/Downloads/panda_logo.png

Requires SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY in the backend .env / env.
"""
import base64
import mimetypes
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from supabase import create_client  # noqa: E402

from pandapower.core.config import settings  # noqa: E402

# Edit these if the company details ever change.
CONTACT_PHONE = "03-9191709"
CONTACT_WEBSITE = "www.pandatech.co.il"
CONTACT_EMAIL = "jobs@pandatech.co.il"


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/set_panda_logo.py /path/to/logo.png")
        return 1

    logo_path = Path(sys.argv[1]).expanduser()
    if not logo_path.exists():
        print(f"❌ File not found: {logo_path}")
        return 1

    mime = mimetypes.guess_type(str(logo_path))[0] or "image/png"
    b64 = base64.b64encode(logo_path.read_bytes()).decode("ascii")
    data_uri = f"data:{mime};base64,{b64}"
    print(f"✓ Encoded {logo_path.name} ({len(b64) // 1024} KB base64, {mime})")

    url = settings.SUPABASE_URL
    key = settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_ANON_KEY
    if not (url and key):
        print("❌ SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not configured")
        return 1
    sb = create_client(url, key)

    rows = [
        {"setting_key": "panda_cv.logo_url", "setting_value": data_uri},
        {"setting_key": "panda_cv.contact_phone", "setting_value": CONTACT_PHONE},
        {"setting_key": "panda_cv.contact_website", "setting_value": CONTACT_WEBSITE},
        {"setting_key": "panda_cv.contact_email", "setting_value": CONTACT_EMAIL},
        {"setting_key": "panda_cv.company_name", "setting_value": "panda tech"},
    ]
    sb.table("system_settings").upsert(rows, on_conflict="setting_key").execute()
    print("✓ Saved panda_cv.* branding to system_settings (logo embedded as data URI)")
    print("  Generate a CV from the Elad screen → '🐼 קו״ח פנדה-טק' to see it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
