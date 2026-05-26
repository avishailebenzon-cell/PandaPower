import asyncio
from pandapower.core.supabase import get_supabase_client

async def check_routing():
    client = await get_supabase_client()
    
    # Check total jobs
    total = await client.table("jobs").select("count", count="exact").execute()
    print(f"Total jobs: {total.count}")
    
    # Check unassigned jobs
    unassigned = await client.table("jobs").select("count", count="exact").is_(
        "assigned_agent_code", None
    ).execute()
    print(f"Unassigned jobs: {unassigned.count}")
    
    # Check assigned jobs
    assigned = await client.table("jobs").select("count", count="exact").not_(
        "assigned_agent_code", "is", None
    ).execute()
    print(f"Assigned jobs: {assigned.count}")
    
    # Check recent routing logs
    recent_routing = await client.table("agent_logs").select("*").eq(
        "action", "route_job"
    ).order("created_at", desc=True).limit(10).execute()
    
    print(f"\nRecent routing logs (last 10):")
    for log in recent_routing.data:
        print(f"  - {log['created_at']}: {log.get('output_payload', {}).get('assigned_agent_code', 'N/A')}")
    
    # Show a few jobs with their assignments
    jobs = await client.table("jobs").select("id, job_title, assigned_agent_code, priority").limit(5).execute()
    print(f"\nSample of jobs:")
    for job in jobs.data:
        agent = job.get("assigned_agent_code") or "UNASSIGNED"
        priority = job.get("priority", 5)
        print(f"  - {job['job_title'][:40]:40} | Agent: {agent:10} | Priority: {priority}")

asyncio.run(check_routing())
