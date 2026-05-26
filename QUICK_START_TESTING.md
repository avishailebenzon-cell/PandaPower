# ⚡ Quick Start Testing - Run Now!

**Time to complete**: 30 minutes (manual) or 5 minutes (automated)

---

## 🚀 Option 1: Automated Quick Test (5 mins)

### Step 1: Start the System
```bash
# Terminal 1: Start Backend
cd apps/backend
python -m uvicorn src.pandapower.main:app --reload

# Terminal 2: Start Frontend
cd apps/frontend
npm run dev

# Terminal 3: Start Workers (Celery)
cd apps/backend
celery -A pandapower.workers.celery_app worker -l info
```

### Step 2: Run Health Checks
```bash
# Check system is running
curl -s http://localhost:8000/admin/health | jq

# Should return:
{
  "status": "healthy",
  "components": {
    "database": "connected",
    "pipedrive_api": "connected",
    "redis": "connected"
  }
}
```

### Step 3: Create Test Data
```bash
# Run the test data generator
python scripts/generate_test_data.py --cv-count=3 --job-count=2 --full-pipeline

# Creates:
# - 3 test CVs in Azure
# - 2 test jobs from Pipedrive
# - 3 test candidates
# - 2 test jobs
```

### Step 4: Monitor Pipeline
```bash
# Watch status updates in real-time
curl -s http://localhost:8000/admin/pipeline-status | jq --raw-output '.[]' | watch

# Refresh every 5 seconds to see:
# - CVs being parsed
# - Jobs being routed
# - Matches being created
# - Quality gates running
```

### Step 5: View Results in Dashboard
```
Open: http://localhost:5173/recruiting
- Check: Agent Departments see new matches
- Check: Work Dashboard shows activity
- Check: /admin/carmit shows pending reviews
```

---

## 📋 Option 2: Manual Step-by-Step Test (30 mins)

### **Test 1: CV Intake (5 mins)**

```bash
# 1. Create test PDF in your downloads
cat > ~/Downloads/test_cv.txt << 'SAMPLE'
John Doe
john@example.com
+972501234567

Senior Python Developer

Experience:
- 5 years Python development
- 3 years PostgreSQL
- 2 years AWS

Skills: Python, FastAPI, PostgreSQL, Docker, AWS
SAMPLE

# 2. Upload to Azure Email
# Simulate: Send email to pdf-intake@company.com with attachment

# 3. Trigger processing
curl -X POST http://localhost:8000/admin/cv/process-all \
  -H "Content-Type: application/json"

# 4. Verify in database
curl -s http://localhost:8000/admin/candidates | jq '.candidates[-1]'
```

### **Test 2: Job Intake from Pipedrive (5 mins)**

```bash
# 1. Create test job in Pipedrive
curl -X POST https://api.pipedrive.com/v1/deals \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "title": "Senior Python Developer",
    "pipeline_id": 1,
    "stage_id": 1,
    "custom_fields": {
      "required_skills": ["Python", "PostgreSQL"],
      "required_experience": 5,
      "client_name": "Acme Inc"
    }
  }'

# 2. Trigger sync
curl -X POST http://localhost:8000/admin/sync/pipedrive-jobs

# 3. Verify in database
curl -s http://localhost:8000/admin/jobs/latest | jq
```

### **Test 3: Carmit Routes Job (5 mins)**

```bash
# 1. Get job ID from previous step
JOB_ID="job_123"

# 2. Trigger routing
curl -X POST http://localhost:8000/admin/carmit/route-job/$JOB_ID \
  -H "Content-Type: application/json"

# 3. Verify assignment
curl -s http://localhost:8000/admin/jobs/$JOB_ID | jq '.assigned_agent_code'
# Expected: "naama" (Python specialist)
```

### **Test 4: Agent Matching (5 mins)**

```bash
# 1. Trigger matching for agent
curl -X POST http://localhost:8000/admin/agents/naama/match \
  -H "Content-Type: application/json" \
  -d '{"job_id": "job_123"}'

# 2. Wait 5 seconds
sleep 5

# 3. Check matches created
curl -s http://localhost:8000/admin/jobs/job_123/matches | jq '.matches'

# Expected: Array with matched candidates
```

### **Test 5: Carmit Quality Gates (10 mins)**

```bash
# 1. Get first match
MATCH_ID="match_123"

# 2. Trigger quality review
curl -X POST http://localhost:8000/admin/carmit/review-match/$MATCH_ID \
  -H "Content-Type: application/json"

# 3. Check result
curl -s http://localhost:8000/admin/matches/$MATCH_ID | jq '.current_state'
# Expected: "carmit_approved" (if gates passed)

# 4. View gate results
curl -s http://localhost:8000/api/admin/matches/$MATCH_ID/history | jq '.stateHistory[-1].details.gate_results'
```

### **Test 6: Send to Tal (10 mins)**

```bash
# 1. View match in Tal queue
curl -s http://localhost:8000/admin/carmit/pending-review | jq '.matches[0]'

# 2. Tal initiates conversation
curl -X POST http://localhost:8000/admin/pipedrive/recruiter-workflow/record-conversation/$MATCH_ID \
  -H "Content-Type: application/json" \
  -d '{
    "recruiter_name": "tal",
    "conversation_summary": "Good fit, interested in role"
  }'

# 3. Tal makes decision (approved)
curl -X POST http://localhost:8000/admin/pipedrive/recruiter-workflow/record-decision/$MATCH_ID \
  -H "Content-Type: application/json" \
  -d '{
    "recruiter_name": "tal",
    "decision": "accepted",
    "decision_reason": "Strong technical fit"
  }'

# 4. View match transitions to Elad
curl -s http://localhost:8000/api/admin/matches/$MATCH_ID/history | jq '.currentState'
# Expected: "sent_to_elad"
```

### **Test 7: Elad Placement (10 mins)**

```bash
# 1. View match in Elad queue
curl -s http://localhost:8000/admin/carmit/pending-review | jq '.matches[0]'

# 2. Elad sends to client
curl -X POST http://localhost:8000/admin/placement/send-candidate/$MATCH_ID \
  -H "Content-Type: application/json" \
  -d '{
    "send_method": "email",
    "client_email": "client@acme.com",
    "message": "Please find attached candidate profile"
  }'

# 3. View match journey
curl -s http://localhost:8000/api/admin/matches/$MATCH_ID/history | jq '.'
# Expected: Shows all 8+ states from found to offer_sent
```

### **Test 8: Final Outcome (5 mins)**

```bash
# 1. Record hiring outcome
curl -X POST http://localhost:8000/admin/placement/record-outcome/$MATCH_ID \
  -H "Content-Type: application/json" \
  -d '{
    "outcome": "hired",
    "notes": "Client accepted. Start: June 1, 2026"
  }'

# 2. View final timeline
curl -s http://localhost:8000/api/admin/matches/$MATCH_ID/history | jq '.stateHistory | length'
# Expected: 12+ states

# 3. Open in browser to see visual timeline
# Go to: http://localhost:5173/recruiting/tal
# Click "📍 מסלול" on the match to see journey
```

---

## 🧪 Quick Test Data Generator Script

```bash
cat > scripts/generate_test_data.py << 'SCRIPT'
#!/usr/bin/env python3
"""
Quick test data generator for E2E testing
Usage: python scripts/generate_test_data.py --cv-count=3 --job-count=2
"""

import json
import asyncio
from datetime import datetime
import random

class TestDataGenerator:
    def __init__(self):
        self.candidates = []
        self.jobs = []
        self.matches = []
    
    def generate_candidate(self, name: str, email: str, skills: list):
        """Generate test candidate"""
        return {
            "name": name,
            "email": email,
            "phone": f"+972{random.randint(5000000, 9999999)}",
            "key_skills": skills,
            "experience_years": random.randint(3, 10),
            "education": "B.Sc. Computer Science",
            "cv_text": f"Resume of {name}...",
            "parsed_at": datetime.utcnow().isoformat()
        }
    
    def generate_job(self, title: str, skills: list):
        """Generate test job"""
        return {
            "title": title,
            "description": f"We are looking for {title}",
            "required_skills": skills,
            "required_experience": 5,
            "pipedrive_deal_id": f"deal_{random.randint(1000, 9999)}",
            "assigned_agent_code": None,
            "status": "new"
        }
    
    def generate_dataset(self, num_candidates=3, num_jobs=2):
        """Generate test dataset"""
        print(f"Generating {num_candidates} candidates and {num_jobs} jobs...")
        
        test_candidates = [
            ("John Doe", "john@example.com", ["Python", "PostgreSQL", "AWS"]),
            ("Jane Smith", "jane@example.com", ["Java", "Spring", "Docker"]),
            ("Bob Johnson", "bob@example.com", ["Python", "FastAPI", "PostgreSQL"]),
        ]
        
        test_jobs = [
            ("Senior Python Developer", ["Python", "PostgreSQL", "AWS"]),
            ("Senior Backend Engineer", ["Java", "Spring", "Docker"]),
        ]
        
        self.candidates = [
            self.generate_candidate(name, email, skills)
            for name, email, skills in test_candidates[:num_candidates]
        ]
        
        self.jobs = [
            self.generate_job(title, skills)
            for title, skills in test_jobs[:num_jobs]
        ]
        
        print(f"✅ Generated {len(self.candidates)} candidates")
        print(f"✅ Generated {len(self.jobs)} jobs")
        
        return self.candidates, self.jobs
    
    def print_summary(self):
        """Print test data summary"""
        print("\n" + "="*50)
        print("📊 TEST DATA GENERATED")
        print("="*50)
        
        print("\n👥 CANDIDATES:")
        for cand in self.candidates:
            print(f"  - {cand['name']} ({cand['email']})")
            print(f"    Skills: {', '.join(cand['key_skills'])}")
        
        print("\n💼 JOBS:")
        for job in self.jobs:
            print(f"  - {job['title']}")
            print(f"    Required: {', '.join(job['required_skills'])}")
        
        print("\n" + "="*50)
        print("Next steps:")
        print("1. Navigate to http://localhost:5173/recruiting")
        print("2. Check Agent Departments for new matches")
        print("3. Go to /admin/carmit to review quality gates")
        print("4. Follow match journey through dashboard")
        print("="*50)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--cv-count", type=int, default=3)
    parser.add_argument("--job-count", type=int, default=2)
    parser.add_argument("--full-pipeline", action="store_true")
    args = parser.parse_args()
    
    generator = TestDataGenerator()
    candidates, jobs = generator.generate_dataset(args.cv_count, args.job_count)
    generator.print_summary()
    
    # Save to JSON for reference
    with open("test_data.json", "w") as f:
        json.dump({
            "candidates": candidates,
            "jobs": jobs,
            "generated_at": datetime.utcnow().isoformat()
        }, f, indent=2)
    
    print("\n💾 Saved to test_data.json")

SCRIPT

chmod +x scripts/generate_test_data.py
```

---

## 📊 Live Monitoring Dashboard

Open these in your browser while testing:

```
System Health:
http://localhost:8000/admin/health

Pipeline Status:
http://localhost:8000/admin/pipeline-status

Agent Status:
http://localhost:8000/admin/agents/status

Frontend Dashboard:
http://localhost:5173/recruiting

Admin Panel (Carmit):
http://localhost:5173/admin/carmit

Recruiter Panel (Tal):
http://localhost:5173/recruiting/tal

Recruiter Panel (Elad):
http://localhost:5173/recruiting/elad

Analytics:
http://localhost:5173/admin/analytics

Match Timeline:
http://localhost:5173 → Click match → "📍 מסלול" button
```

---

## ✅ Success Indicators During Test

As you run through the tests, look for these green indicators:

```
✅ CV uploaded and parsed
✅ Candidate created in database
✅ Job imported from Pipedrive
✅ Job routed to Naama (Python specialist)
✅ Match found by agent
✅ Match enters Carmit review queue
✅ All 5 quality gates PASS
✅ Match state: carmit_approved
✅ Match sent to Tal queue
✅ Tal initiates WhatsApp conversation
✅ Candidate fills form
✅ Tal approves candidate
✅ Match sent to Elad queue
✅ Elad sends to client
✅ Offer recorded as sent
✅ Client accepts → HIRED ✅
✅ Timeline shows all 12 states
```

---

## 🚨 If Something Breaks

### **Quick Diagnostics**

```bash
# Check server logs
tail -f logs/app.log

# Check database connection
curl http://localhost:8000/admin/health

# Check worker status
ps aux | grep celery

# Reset database (WARNING: deletes all data)
# python scripts/reset_db.py

# Check specific entity
curl http://localhost:8000/admin/candidates/latest
curl http://localhost:8000/admin/matches/latest
```

### **Common Problems**

| Problem | Fix |
|---------|-----|
| "Connection refused" | Start backend with `python -m uvicorn...` |
| "No module named 'pandapower'" | `pip install -e apps/backend` |
| "Pipedrive API error" | Check PIPEDRIVE_API_TOKEN in .env |
| "Database not initialized" | Run `alembic upgrade head` |
| "Green API failed" | Check GREEN_API_TOKEN in .env |

---

## 📝 Testing Checklist

Copy this and check off as you go:

```
E2E Testing Checklist - [Date]
================================

Phase 1: Setup
  ☐ Backend running (port 8000)
  ☐ Frontend running (port 5173)
  ☐ Workers running (Celery)
  ☐ Health check passes
  ☐ Test data generated

Phase 2: Input Stages
  ☐ CV parsed correctly
  ☐ Candidate created
  ☐ Job imported from Pipedrive
  ☐ Job routed to agent

Phase 3: Agent Stage
  ☐ Agent found matches
  ☐ Match score reasonable
  ☐ Match in Carmit queue

Phase 4: Quality Gates
  ☐ Gate 1 (Past Rejection): PASS
  ☐ Gate 2 (Already Declined): PASS
  ☐ Gate 3 (Conflict Check): PASS
  ☐ Gate 4 (Clearance): PASS
  ☐ Gate 5 (Score Threshold): PASS
  ☐ Match approved overall

Phase 5: Tal Screening
  ☐ Match in Tal queue
  ☐ Tal conversation initiated
  ☐ Candidate form submitted
  ☐ Tal approved candidate

Phase 6: Elad Placement
  ☐ Match in Elad queue
  ☐ Offer sent to client
  ☐ Pipedrive activity created

Phase 7: Final Outcome
  ☐ Client accepted
  ☐ Match marked as hired
  ☐ Timeline shows all states

Performance
  ☐ Total time < 30 minutes
  ☐ API responses < 1 second
  ☐ No database errors
  ☐ No API errors

Tester: ________________  Date: ____________
```

---

**Ready to start?** Choose Option 1 or 2 above and begin testing! 🚀

