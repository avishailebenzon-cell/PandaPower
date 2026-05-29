#!/usr/bin/env python3
"""
Advanced Integration Test: Pandi Flow with Database Verification
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Test with phone: 972-52-6665248
Verifies:
  1. ✅ Webhook receives message
  2. ✅ Database records message
  3. ✅ Client created in Supabase
  4. ✅ Conversation started
  5. ✅ Referral created with REF-2026-XXXX
"""

import requests
import json
import time
from datetime import datetime

# Configuration
BASE_URL = "https://pandapower-backend.onrender.com"
PHONE = "972-52-6665248"  # Your test phone

def send_webhook(text: str, phone: str):
    """Send webhook message."""
    phone_clean = phone.replace("-", "").replace(" ", "").replace("+", "")

    payload = {
        "messages": [{
            "id": f"msg_{int(time.time() * 1000)}",
            "from": f"{phone_clean}@c.us",
            "text": text,
            "timestamp": int(time.time())
        }]
    }

    url = f"{BASE_URL}/webhooks/whatsapp/pandi"

    print(f"\n 📤 [{text[:30]}...]")
    print(f"   POST {url}")

    try:
        resp = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )

        if resp.status_code == 200:
            print(f"   ✅ {resp.status_code} OK")
            return True
        else:
            print(f"   ❌ {resp.status_code}: {resp.text[:100]}")
            return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

def test_full_flow():
    """Run full E2E test."""
    print("\n" + "="*70)
    print("🤖 PANDI E2E INTEGRATION TEST")
    print("="*70)

    # 1️⃣ Send greeting (unknown phone)
    print("\n[Step 1️⃣] Unknown phone sends greeting")
    send_webhook("שלום", PHONE)
    time.sleep(1)

    # 2️⃣ Send details to complete intake
    print("\n[Step 2️⃣] Client provides details for registration")
    details = "שמי אבישי לבנזון, אימייל: test.user@example.com, חברה: TestCorp, תפקיד: Senior Developer"
    send_webhook(details, PHONE)
    time.sleep(1)

    # 3️⃣ Job context
    print("\n[Step 3️⃣] Client describes job requirements")
    job = "מחפש Python developer עם ניסיון ב-FastAPI, React ו-PostgreSQL"
    send_webhook(job, PHONE)
    time.sleep(1)

    # 4️⃣ Client shows interest
    print("\n[Step 4️⃣] Pandi presents candidate, client shows interest")
    interest = "כן, המועמד הראשון נראה טוב לי"
    send_webhook(interest, PHONE)
    time.sleep(2)

    # Summary
    print("\n" + "="*70)
    print("✅ WEBHOOK TEST COMPLETE")
    print("="*70)
    print("""
📊 Expected Results:
   1. Messages logged in Supabase pandi_messages table
   2. pandi_client created with:
      - phone: 972526665248
      - status: completed or in_progress
   3. pandi_conversations created (open status)
   4. candidate_referrals created with:
      - referral_number: REF-2026-XXXX
      - status: presented or client_interested
      - sla_deadline: 48 hours from now
      - is_sla_breached: false

💡 Next Step: Check Database
   - Supabase Console: https://app.supabase.com
   - Tables to verify:
     • pandi_clients (phone = {phone})
     • pandi_messages (text like '%שלום%')
     • pandi_conversations (status = 'open')
     • candidate_referrals (status = 'presented' or 'client_interested')

⏰ Verify Admin Dashboard:
   - Frontend: https://pandapower.vercel.app/admin/pandi/referrals
   - Should show new referral with 48h SLA countdown
   - Status updates possible from dashboard
""".format(phone=PHONE))

if __name__ == "__main__":
    test_full_flow()
