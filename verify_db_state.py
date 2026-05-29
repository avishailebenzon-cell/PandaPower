#!/usr/bin/env python3
"""Verify Pandi state in Supabase database."""

import os
import sys
from dotenv import load_dotenv
from supabase import create_client

# Load environment
load_dotenv("apps/backend/.env")

def verify():
    """Verify database state."""
    phone = "972526665248"

    print("\n" + "="*70)
    print("🔍 DATABASE VERIFICATION")
    print("="*70)

    # Create Supabase client
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not url or not key:
        print("❌ Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")
        return

    supabase = create_client(url, key)

    # 1. Check pandi_clients
    print("\n[1️⃣] Checking pandi_clients...")
    try:
        result = supabase.table("pandi_clients").select("*").eq(
            "phone", phone
        ).execute()

        if result.data:
            client = result.data[0]
            print(f"   ✅ Client found!")
            print(f"      - ID: {client.get('id')}")
            print(f"      - Phone: {client.get('phone')}")
            print(f"      - Status: {client.get('intake_status')}")
            print(f"      - Created: {client.get('created_at')}")
        else:
            print(f"   ⚠️  No client found for phone {phone}")
    except Exception as e:
        print(f"   ❌ Error: {str(e)[:80]}")

    # 2. Check pandi_messages
    print("\n[2️⃣] Checking pandi_messages...")
    try:
        result = supabase.table("pandi_messages").select(
            "id, text, direction, created_at"
        ).eq("direction", "inbound").order("created_at", desc=True).limit(3).execute()

        if result.data:
            print(f"   ✅ Found {len(result.data)} inbound messages")
            for msg in result.data:
                text = msg.get("text", "")[:40]
                print(f"      - {msg.get('created_at')}: {text}")
        else:
            print(f"   ⚠️  No messages found")
    except Exception as e:
        print(f"   ❌ Error: {str(e)[:80]}")

    # 3. Check pandi_conversations
    print("\n[3️⃣] Checking pandi_conversations...")
    try:
        result = supabase.table("pandi_conversations").select("id, status, created_at").eq(
            "status", "open"
        ).execute()

        if result.data:
            print(f"   ✅ Found {len(result.data)} open conversations")
            for conv in result.data[-2:]:
                print(f"      - ID: {str(conv.get('id'))[:8]}... Status: {conv.get('status')}")
        else:
            print(f"   ⚠️  No open conversations found")
    except Exception as e:
        print(f"   ❌ Error: {str(e)[:80]}")

    # 4. Check candidate_referrals
    print("\n[4️⃣] Checking candidate_referrals...")
    try:
        result = supabase.table("candidate_referrals").select(
            "referral_number, status, sla_deadline, candidate_number"
        ).order("created_at", desc=True).limit(5).execute()

        if result.data:
            print(f"   ✅ Found {len(result.data)} recent referrals")
            for ref in result.data:
                sla = ref.get('sla_deadline', 'N/A')
                print(f"      - {ref.get('referral_number')}: {ref.get('status')} (SLA: {sla})")
        else:
            print(f"   ⚠️  No referrals found yet")
    except Exception as e:
        print(f"   ❌ Error: {str(e)[:80]}")

    print("\n" + "="*70)


if __name__ == "__main__":
    verify()
