import sys
sys.path.insert(0, "src")
import asyncio
from pandapower.workers.pipedrive_sync import sync_pipedrive_contacts

async def test_sync():
    try:
        print("Starting Pipedrive contact sync...\n")
        result = await sync_pipedrive_contacts()
        
        print("\n" + "="*60)
        print("SYNC COMPLETED!")
        print("="*60)
        print(f"Total contacts: {result.get('total', 0)}")
        print(f"Employees synced: {result.get('employees', 0)}")
        print(f"Clients synced: {result.get('clients', 0)}")
        print(f"Potential clients synced: {result.get('potential_clients', 0)}")
        
        errors = result.get('errors', [])
        if errors:
            print(f"\nErrors ({len(errors)}):")
            for err in errors[:5]:  # Show first 5 errors
                print(f"  - Person {err.get('person_id')}: {err.get('error')}")
        else:
            print("\n✓ No errors!")
        
    except Exception as e:
        print(f"✗ Sync failed: {e}")
        import traceback
        traceback.print_exc()

asyncio.run(test_sync())
