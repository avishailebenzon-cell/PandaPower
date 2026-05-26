import sys
sys.path.insert(0, "src")
import asyncio
from pandapower.core.supabase import get_supabase_client

async def check_schema():
    db = await get_supabase_client()
    
    # Try to query the contacts table to see what columns it has
    try:
        result = db.table("contacts").select("*").limit(1).execute()
        print("✓ Contacts table exists")
        if result.data:
            print(f"Row data: {result.data[0]}")
            print(f"Columns: {result.data[0].keys()}")
        else:
            print("No data in contacts table yet")
    except Exception as e:
        print(f"✗ Error querying contacts table: {e}")
        print(f"Error type: {type(e).__name__}")
    
    # Try to get table info via information_schema
    try:
        result = db.rpc("get_table_info", {"table_name": "contacts"}).execute()
        print(f"Table info: {result}")
    except Exception as e:
        print(f"Could not get table info via RPC: {e}")

asyncio.run(check_schema())
