#!/usr/bin/env python3
"""
E2E Test: Pandi WhatsApp Bot Flow
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Test with phone: 972-52-6665248
Tests entire flow:
  1. Unknown phone → Pandi identifies client
  2. New client registration
  3. Job context gathering
  4. Candidate search & presentation
  5. Referral creation
  6. SLA tracking
"""

import json
import requests
import time
from datetime import datetime

# Configuration
BASE_URL = "https://pandapower-backend.onrender.com"
PHONE = "972-52-6665248"  # Your phone number
WEBHOOK_SECRET = ""  # Empty for testing (no auth required)

def normalize_phone(phone: str) -> str:
    """Convert to WhatsApp format."""
    # Remove dashes, spaces
    clean = phone.replace("-", "").replace(" ", "").strip()
    # Ensure E.164 format: +972526665248
    if not clean.startswith("+"):
        if clean.startswith("0"):
            clean = "+972" + clean[1:]
        else:
            clean = "+" + clean
    return clean

def simulate_green_api_webhook(text: str, phone: str):
    """Simulate Green API webhook payload.

    Green API sends:
    {
      "messages": [{
        "id": "message_id",
        "from": "972526665248@c.us",
        "text": "hello",
        "timestamp": 1234567890
      }]
    }
    """
    phone_normalized = phone.replace("+", "").replace("-", "")

    payload = {
        "messages": [{
            "id": f"msg_{int(time.time() * 1000)}",
            "from": f"{phone_normalized}@c.us",
            "text": text,
            "timestamp": int(time.time())
        }]
    }

    url = f"{BASE_URL}/webhooks/whatsapp/pandi"
    if WEBHOOK_SECRET:
        url += f"?token={WEBHOOK_SECRET}"

    print(f"\n📤 SENDING: {text}")
    print(f"   Phone: {phone}")
    print(f"   Endpoint: POST /webhooks/whatsapp/pandi")

    try:
        resp = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        print(f"   Response: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"   Event: {data.get('event', 'unknown')}")
            return True
        else:
            print(f"   Error: {resp.text}")
            return False
    except Exception as e:
        print(f"   Failed: {e}")
        return False

def test_flow():
    """Run the full E2E test."""
    print("\n" + "="*70)
    print("🤖 PANDI E2E TEST - Full Client Identification + Referral Flow")
    print("="*70)

    # Step 1: Send greeting
    print("\n[Step 1️⃣] Unknown phone sends greeting")
    simulate_green_api_webhook("שלום", PHONE)
    time.sleep(2)

    # Step 2: Phone number doesn't exist → intake flow starts
    print("\n[Step 2️⃣] Pandi identifies phone (new client)")
    print("    Expected: Pandi asks for client details")

    # Step 3: Send client details
    print("\n[Step 3️⃣] Client sends personal details")
    details = "אישור לא קיים, אני רוצה להירשם. שם: אבישי לבנזון, מייל: test@example.com, חברה: TechCorp, תפקיד: CTO"
    simulate_green_api_webhook(details, PHONE)
    time.sleep(2)

    # Step 4: Continue with job context
    print("\n[Step 4️⃣] Client provides job context (skills, level, location)")
    job_context = "אני מחפש מוביל תכנה בעל ניסיון ב-Python, React, Cloud"
    simulate_green_api_webhook(job_context, PHONE)
    time.sleep(2)

    # Step 5: Pandi searches and presents candidates
    print("\n[Step 5️⃣] Pandi searches database and presents matches")
    print("    Expected: Up to 3 anonymized candidates (C000001, C000002, etc)")

    # Step 6: Simulate client interest
    print("\n[Step 6️⃣] Client indicates interest in first candidate")
    simulate_green_api_webhook("כן, המועמד הראשון נראה מתאים", PHONE)
    time.sleep(2)

    print("\n" + "="*70)
    print("✅ Test Flow Complete!")
    print("="*70)
    print("\n📊 Verify in Admin Dashboard:")
    print("   1. Go to https://pandapower.vercel.app/admin/pandi/referrals")
    print("   2. You should see a new referral REF-2026-XXXX")
    print("   3. Status: 'presented' or 'client_interested'")
    print("   4. SLA countdown showing 48 hours")
    print("\n📧 Email Notifications:")
    print(f"   Check: {PHONE} for WhatsApp messages")
    print(f"   Check: avishai.lebenzon@gmail.com for referral notifications")

if __name__ == "__main__":
    test_flow()
