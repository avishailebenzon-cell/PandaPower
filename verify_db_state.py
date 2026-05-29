#!/usr/bin/env python3
"""Verify Pandi state in Supabase database."""

import os
import sys
from dotenv import load_dotenv

# Load environment
load_dotenv("apps/backend/.env")

# Add backend to path
sys.path.insert(0, "apps/backend/src")

from pandapower.core.supabase import init_supabase, get_supabase_client


async def verify():
    """Verify database state."""
    await init_supabase()
    supabase = await get_supabase_client()

    phone = "972526665248"

    print("\n" + "="*70)
    print("🔍 DATABASE VERIFICATION")
    print("="*70)

    # 1. Check pandi_clients
    print("\n[1️⃣] Checking pandi_clients...")
    try:
        result = await supabase.table("pandi_clients").select("*").eq(
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
            print(f"   ❌ No client found for phone {phone}")
    except Exception as e:
        print(f"   ❌ Error: {e}")

    # 2. Check pandi_messages
    print("\n[2️⃣] Checking pandi_messages...")
    try:
        result = await supabase.table("pandi_messages").select(
            "id, text, direction, created_at"
        ).eq("direction", "inbound").execute()

        if result.data:
            print(f"   ✅ Found {len(result.data)} inbound messages")
            for msg in result.data[-3:]:  # Show last 3
                text = msg.get("text", "")[:40]
                print(f"      - {msg.get('created_at')}: {text}")
        else:
            print(f"   ❌ No messages found")
    except Exception as e:
        print(f"   ❌ Error: {e}")

    # 3. Check pandi_conversations
    print("\n[3️⃣] Checking pandi_conversations...")
    try:
        result = await supabase.table("pandi_conversations").select("*").eq(
            "status", "open"
        ).execute()

        if result.data:
            print(f"   ✅ Found {len(result.data)} open conversations")
            for conv in result.data[-2:]:
                print(f"      - ID: {conv.get('id')[:8]}... Status: {conv.get('status')}")
        else:
            print(f"   ❌ No open conversations found")
    except Exception as e:
        print(f"   ❌ Error: {e}")

    # 4. Check candidate_referrals
    print("\n[4️⃣] Checking candidate_referrals...")
    try:
        result = await supabase.table("candidate_referrals").select(
            "referral_number, status, sla_deadline, is_sla_breached"
        ).order("created_at", desc=True).limit(5).execute()

        if result.data:
            print(f"   ✅ Found {len(result.data)} recent referrals")
            for ref in result.data:
                print(f"      - {ref.get('referral_number')}: {ref.get('status')} (SLA breach: {ref.get('is_sla_breached')})")
        else:
            print(f"   ❌ No referrals found")
    except Exception as e:
        print(f"   ❌ Error: {e}")

    print("\n" + "="*70)


if __name__ == "__main__":
    import asyncio
    asyncio.run(verify())
