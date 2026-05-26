# 🏥 Health Check Endpoints Implementation

**Add these endpoints to your backend for monitoring during testing**

---

## 1️⃣ System Health Check

**File**: `apps/backend/src/pandapower/routers/admin/health.py`

```python
from fastapi import APIRouter, HTTPException
from datetime import datetime
import os

router = APIRouter(prefix="/admin", tags=["health"])

@router.get("/health")
async def system_health():
    """
    Check overall system health and component status
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "components": {}
    }
    
    # Check Database
    try:
        from pandapower.db.database import get_db
        db = next(get_db())
        db.execute("SELECT 1")
        health_status["components"]["database"] = "connected"
    except Exception as e:
        health_status["status"] = "degraded"
        health_status["components"]["database"] = f"error: {str(e)}"
    
    # Check Pipedrive API
    try:
        api_token = os.getenv("PIPEDRIVE_API_TOKEN")
        if api_token:
            health_status["components"]["pipedrive_api"] = "connected"
        else:
            health_status["components"]["pipedrive_api"] = "not configured"
    except Exception as e:
        health_status["components"]["pipedrive_api"] = f"error: {str(e)}"
    
    # Check Green API
    try:
        green_token = os.getenv("GREEN_API_TOKEN")
        if green_token:
            health_status["components"]["green_api"] = "connected"
        else:
            health_status["components"]["green_api"] = "not configured"
    except Exception as e:
        health_status["components"]["green_api"] = f"error: {str(e)}"
    
    # Check Azure Storage
    try:
        azure_account = os.getenv("AZURE_STORAGE_ACCOUNT")
        if azure_account:
            health_status["components"]["azure_storage"] = "connected"
        else:
            health_status["components"]["azure_storage"] = "not configured"
    except Exception as e:
        health_status["components"]["azure_storage"] = f"error: {str(e)}"
    
    # Check Redis (if used)
    try:
        import redis
        r = redis.from_url(os.getenv("REDIS_URL", "redis://localhost"))
        r.ping()
        health_status["components"]["redis"] = "connected"
    except Exception:
        health_status["components"]["redis"] = "not available"
    
    return health_status
```

**Usage:**
```bash
curl http://localhost:8000/admin/health | jq
```

**Expected Response:**
```json
{
  "status": "healthy",
  "timestamp": "2026-05-23T20:30:00Z",
  "components": {
    "database": "connected",
    "pipedrive_api": "connected",
    "green_api": "connected",
    "azure_storage": "connected",
    "redis": "connected"
  }
}
```

---

## 2️⃣ Pipeline Status

**File**: Add to `apps/backend/src/pandapower/routers/admin/health.py`

```python
from sqlalchemy import select, and_

@router.get("/pipeline-status")
async def pipeline_status(db: Session = Depends(get_db)):
    """
    Get current pipeline status: pending items at each stage
    """
    from pandapower.db.models import Matches, Candidates, Jobs
    
    # Count by match state
    pending_cvs = db.execute(
        select(Candidates).where(Candidates.created_at > datetime.utcnow() - timedelta(days=7))
    ).scalars().all()
    
    pending_matches = {
        "found": db.execute(
            select(Matches).where(Matches.current_state == "found")
        ).scalars().count(),
        
        "carmit_review": db.execute(
            select(Matches).where(Matches.current_state == "found")
        ).scalars().count(),
        
        "sent_to_tal": db.execute(
            select(Matches).where(Matches.current_state == "sent_to_tal")
        ).scalars().count(),
        
        "tal_conversation": db.execute(
            select(Matches).where(Matches.current_state == "tal_conversation")
        ).scalars().count(),
        
        "sent_to_elad": db.execute(
            select(Matches).where(Matches.current_state == "sent_to_elad")
        ).scalars().count(),
        
        "elad_conversation": db.execute(
            select(Matches).where(Matches.current_state == "elad_conversation")
        ).scalars().count(),
        
        "offer_sent": db.execute(
            select(Matches).where(Matches.current_state == "offer_sent")
        ).scalars().count(),
    }
    
    completed = {
        "hired": db.execute(
            select(Matches).where(Matches.current_state == "hired")
        ).scalars().count(),
        
        "failed": db.execute(
            select(Matches).where(
                Matches.current_state.in_(["carmit_rejected", "tal_rejected", "placement_failed"])
            )
        ).scalars().count(),
    }
    
    return {
        "pending_items": {
            "pending_cvs": len(pending_cvs),
            "pending_jobs": db.execute(
                select(Jobs).where(Jobs.assigned_agent_code.is_(None))
            ).scalars().count(),
        },
        "queue_status": pending_matches,
        "completed": completed,
        "total_processed": completed["hired"] + completed["failed"],
        "success_rate": (
            completed["hired"] / (completed["hired"] + completed["failed"])
            if (completed["hired"] + completed["failed"]) > 0 else 0
        ),
        "timestamp": datetime.utcnow().isoformat()
    }
```

**Usage:**
```bash
curl http://localhost:8000/admin/pipeline-status | jq
```

**Expected Response:**
```json
{
  "pending_items": {
    "pending_cvs": 5,
    "pending_jobs": 3
  },
  "queue_status": {
    "found": 12,
    "carmit_review": 12,
    "sent_to_tal": 8,
    "tal_conversation": 4,
    "sent_to_elad": 4,
    "elad_conversation": 2,
    "offer_sent": 1
  },
  "completed": {
    "hired": 2,
    "failed": 1
  },
  "total_processed": 3,
  "success_rate": 0.667,
  "timestamp": "2026-05-23T20:30:00Z"
}
```

---

## 3️⃣ Agent Status

**File**: Add to `apps/backend/src/pandapower/routers/admin/health.py`

```python
@router.get("/agents/status")
async def agents_status(db: Session = Depends(get_db)):
    """
    Get status of all agents: active, matches found, success rates
    """
    from pandapower.db.models import AgentLogs, Matches
    
    agents_config = {
        "alik": {"name": "אליק", "specialty": "Electronics/FPGA"},
        "naama": {"name": "נעמה", "specialty": "Software/Python"},
        "dganit": {"name": "דגנית", "specialty": "QA/Testing"},
        "ofir": {"name": "אופיר", "specialty": "Systems/Linux"},
        "itai": {"name": "איתי", "specialty": "IT/Infrastructure"},
        "lior": {"name": "ליאור", "specialty": "Mechanical/CAD"},
        "gc": {"name": "כללי", "specialty": "General/Other"},
    }
    
    agent_status = {}
    
    for agent_code, agent_info in agents_config.items():
        # Count matches found
        matches_found = db.execute(
            select(Matches).where(Matches.agent_id == agent_code)
        ).scalars().count()
        
        # Count successful matches
        hired = db.execute(
            select(Matches).where(
                and_(
                    Matches.agent_id == agent_code,
                    Matches.current_state == "hired"
                )
            )
        ).scalars().count()
        
        # Calculate success rate
        success_rate = (hired / matches_found) if matches_found > 0 else 0
        
        agent_status[agent_code] = {
            "name": agent_info["name"],
            "specialty": agent_info["specialty"],
            "status": "active",
            "matches_found": matches_found,
            "placements": hired,
            "success_rate": round(success_rate, 2),
            "last_activity": "2026-05-23T20:30:00Z"  # Add from logs
        }
    
    return {"agents": agent_status, "timestamp": datetime.utcnow().isoformat()}
```

**Usage:**
```bash
curl http://localhost:8000/admin/agents/status | jq
```

**Expected Response:**
```json
{
  "agents": {
    "alik": {
      "name": "אליק",
      "specialty": "Electronics/FPGA",
      "status": "active",
      "matches_found": 15,
      "placements": 10,
      "success_rate": 0.67,
      "last_activity": "2026-05-23T20:30:00Z"
    },
    "naama": {
      "name": "נעמה",
      "specialty": "Software/Python",
      "status": "active",
      "matches_found": 22,
      "placements": 16,
      "success_rate": 0.73,
      "last_activity": "2026-05-23T20:25:00Z"
    }
  },
  "timestamp": "2026-05-23T20:30:00Z"
}
```

---

## 4️⃣ Match Journey Tracking

**Already implemented in**: `apps/backend/src/pandapower/routers/admin/match_history.py`

```bash
# Get full match history
curl http://localhost:8000/api/admin/matches/match_123/history | jq

# Get state summary
curl http://localhost:8000/api/admin/matches/match_123/state-summary | jq
```

---

## 🔌 Register Endpoints in Main Router

**File**: `apps/backend/src/pandapower/main.py`

```python
# Add this to your main.py
from pandapower.routers.admin.health import router as health_router

# Include router
app.include_router(health_router, tags=["health"])
```

---

## 📊 Monitoring Commands

Use these commands to monitor the system during testing:

### **Watch Pipeline in Real-time**
```bash
watch -n 2 'curl -s http://localhost:8000/admin/pipeline-status | jq ".queue_status"'
```

### **Monitor Agent Activity**
```bash
watch -n 5 'curl -s http://localhost:8000/admin/agents/status | jq ".agents | to_entries[] | {agent: .key, matches: .value.matches_found, success: .value.success_rate}"'
```

### **Check Match Journey Progress**
```bash
# When you have a match ID
MATCH_ID="match_123"
watch -n 3 "curl -s http://localhost:8000/api/admin/matches/$MATCH_ID/state-summary | jq '.currentState'"
```

### **Overall Health Dashboard** (one command)
```bash
while true; do
  echo "=== System Health ==="
  curl -s http://localhost:8000/admin/health | jq '.components'
  echo ""
  echo "=== Pipeline Status ==="
  curl -s http://localhost:8000/admin/pipeline-status | jq '{pending: .pending_items, queues: .queue_status, completed: .completed}'
  echo ""
  sleep 5
done
```

---

## 🎯 What to Look For During Testing

| Component | Expected | Warning | Critical |
|-----------|----------|---------|----------|
| **Database** | connected | offline | ❌ ERROR |
| **Pipedrive API** | connected | slow response | ❌ ERROR |
| **Green API** | connected | delayed | ❌ ERROR |
| **Queue: sent_to_tal** | > 0 after Phase 6 | 0 items | Matching failed |
| **Queue: sent_to_elad** | > 0 after Phase 9 | 0 items | Tal approval failed |
| **Success Rate** | > 50% | 20-50% | < 20% investigate |
| **Avg Processing** | < 20 min | 20-30 min | > 30 min investigate |

---

**Implementation complete!** Add these endpoints and use them to monitor your E2E tests. 🚀

