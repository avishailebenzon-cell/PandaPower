#!/usr/bin/env python3
"""
Test Data Generator for PandaPower
Generates complete test data for 12-phase E2E testing
Usage: python3 generate_test_data.py [--verbose] [--limit 5]
"""

import sys
import os
import asyncio
import json
from datetime import datetime, timedelta
from typing import Optional
import argparse

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from pandapower.core import settings
from pandapower.db.database import get_db, get_async_session
from pandapower.db.models import (
    Candidates, Jobs, Matches, Agents, AgentLogs,
    MatchStateHistory, Organizations
)
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession


class TestDataGenerator:
    """Generates complete test data for E2E testing"""

    def __init__(self, verbose: bool = False, limit: int = 5):
        self.verbose = verbose
        self.limit = limit
        self.created_ids = {
            'candidates': [],
            'jobs': [],
            'matches': [],
            'agents': [],
            'organizations': []
        }

    def log(self, message: str):
        """Print if verbose"""
        if self.verbose:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

    async def cleanup_test_data(self, session: AsyncSession):
        """Clean up previous test data"""
        self.log("Cleaning up previous test data...")

        await session.execute(delete(MatchStateHistory))
        await session.execute(delete(Matches))
        await session.execute(delete(Jobs))
        await session.execute(delete(Candidates))
        await session.execute(delete(Organizations))

        await session.commit()
        self.log("✅ Cleanup complete")

    async def create_organizations(self, session: AsyncSession) -> list:
        """Create test organizations"""
        self.log("Creating organizations...")

        orgs_data = [
            {
                "name": "תא"כ לימור",
                "description": "חברת טכנולוגיה",
                "country": "ישראל",
                "industry": "Software"
            },
            {
                "name": "גודאל סיסטמס",
                "description": "בדיקות מערכות",
                "country": "ישראל",
                "industry": "QA"
            },
            {
                "name": "כללי האגוד",
                "description": "שירותים פיננסיים",
                "country": "ישראל",
                "industry": "Finance"
            }
        ]

        orgs = []
        for org_data in orgs_data:
            org = Organizations(**org_data)
            session.add(org)
            orgs.append(org)

        await session.flush()
        self.created_ids['organizations'] = [org.id for org in orgs]
        self.log(f"✅ Created {len(orgs)} organizations")
        return orgs

    async def create_candidates(self, session: AsyncSession, count: int) -> list:
        """Create test candidates"""
        self.log(f"Creating {count} candidates...")

        candidates = []
        for i in range(1, count + 1):
            candidate = Candidates(
                name=f"מועמד {i} - {['דוד', 'שרה', 'משה', 'רחל', 'יהודה'][i % 5]} {['כהן', 'לוי', 'משה', 'גרין', 'שלום'][i % 5]}",
                email=f"candidate{i}@test.example.com",
                phone=f"+972501234{100+i}",
                location="תל אביב",
                headline=f"{'Senior' if i % 3 == 0 else 'Mid-level' if i % 3 == 1 else 'Junior'} Software Engineer",
                key_skills=["Python", "JavaScript", "React", "SQL"] if i % 2 == 0 else ["Java", "Spring Boot", "Docker", "Kubernetes"],
                security_clearance_level="None",
                years_of_experience=2 + (i % 8),
                cv_text=f"Sample CV for candidate {i}",
                cv_parsed_data={
                    "experience_years": 2 + (i % 8),
                    "skills": ["Python", "JavaScript"] if i % 2 == 0 else ["Java", "Spring"],
                    "education": "B.Sc. Computer Science"
                },
                raw_cv_url=f"https://storage.example.com/cv_{i}.pdf",
                intake_method="email",
                match_score=0.5 + (i * 0.05) % 0.5,
                is_active=True
            )
            session.add(candidate)
            candidates.append(candidate)

        await session.flush()
        self.created_ids['candidates'] = [c.id for c in candidates]
        self.log(f"✅ Created {len(candidates)} candidates")
        return candidates

    async def create_jobs(self, session: AsyncSession, org_ids: list, count: int) -> list:
        """Create test jobs"""
        self.log(f"Creating {count} jobs...")

        jobs = []
        job_titles = [
            "Senior Python Developer",
            "QA Engineer",
            "Full Stack Engineer",
            "DevOps Engineer",
            "Backend Engineer"
        ]

        for i in range(1, count + 1):
            job = Jobs(
                title=job_titles[i % len(job_titles)],
                description=f"Test job {i}",
                location="תל אביב",
                required_skills=["Python", "Docker"] if i % 2 == 0 else ["Java", "SQL"],
                experience_level="3-5 years" if i % 2 == 0 else "5+ years",
                organization_id=org_ids[i % len(org_ids)],
                required_clearance_level="None",
                status="active",
                created_by="test_system",
                salary_range="100,000-150,000",
                job_type="Full-time"
            )
            session.add(job)
            jobs.append(job)

        await session.flush()
        self.created_ids['jobs'] = [j.id for j in jobs]
        self.log(f"✅ Created {len(jobs)} jobs")
        return jobs

    async def create_matches(
        self,
        session: AsyncSession,
        candidates: list,
        jobs: list,
        agent_id: str
    ) -> list:
        """Create test matches in 'found' state"""
        self.log(f"Creating matches for {len(candidates)} x {len(jobs)}...")

        matches = []
        match_count = min(len(candidates), len(jobs), 10)  # Limit to 10 matches

        for i in range(match_count):
            match = Matches(
                candidate_id=candidates[i].id,
                job_id=jobs[i % len(jobs)].id,
                assigned_agent_code=agent_id,
                match_score=0.7 + (i * 0.02) % 0.2,
                current_state="found",
                status="active",
                quality_gates={}
            )
            session.add(match)
            matches.append(match)

        await session.flush()
        self.created_ids['matches'] = [m.id for m in matches]
        self.log(f"✅ Created {len(matches)} matches in 'found' state")
        return matches

    async def create_agents(self, session: AsyncSession) -> list:
        """Get or create test agents"""
        self.log("Setting up agents...")

        # Get existing agents
        result = await session.execute(select(Agents))
        agents = result.scalars().all()

        if not agents:
            self.log("Creating new agents...")
            agent_codes = ["naama", "alik", "dganit"]
            agents = []
            for code in agent_codes:
                agent = Agents(
                    code=code,
                    name=f"Agent {code}",
                    title="Recruitment Agent",
                    avatar=f"https://avatar.example.com/{code}.jpg",
                    description=f"Test agent {code}"
                )
                session.add(agent)
                agents.append(agent)
            await session.flush()

        self.log(f"✅ Using {len(agents)} agents")
        return agents

    async def run(self, session: AsyncSession):
        """Run complete test data generation"""
        print("\n" + "="*60)
        print("🐼 PandaPower Test Data Generator")
        print("="*60 + "\n")

        self.log(f"Generating test data (limit: {self.limit} candidates)")

        # 1. Cleanup
        await self.cleanup_test_data(session)

        # 2. Create agents
        agents = await self.create_agents(session)
        agent_code = agents[0].code

        # 3. Create organizations
        orgs = await self.create_organizations(session)
        org_ids = [org.id for org in orgs]

        # 4. Create candidates
        candidates = await self.create_candidates(session, self.limit)

        # 5. Create jobs
        jobs = await self.create_jobs(session, org_ids, self.limit)

        # 6. Create matches
        matches = await self.create_matches(session, candidates, jobs, agent_code)

        # Commit all changes
        await session.commit()

        # Print summary
        print("\n" + "="*60)
        print("✅ Test Data Generated Successfully!")
        print("="*60)
        print(f"\nCreated:")
        print(f"  - {len(candidates)} Candidates")
        print(f"  - {len(jobs)} Jobs")
        print(f"  - {len(matches)} Matches (in 'found' state)")
        print(f"  - {len(orgs)} Organizations")
        print(f"  - {len(agents)} Agents")

        print(f"\n📊 Test Data Summary:")
        print(f"  Agent Code: {agent_code}")
        print(f"  First Candidate: {candidates[0].name} (ID: {candidates[0].id})")
        print(f"  First Job: {jobs[0].title} (ID: {jobs[0].id})")
        print(f"  First Match: {candidates[0].name} → {jobs[0].title} (ID: {matches[0].id})")

        print(f"\n🧪 Ready for testing! Your test data is ready.")
        print(f"   Use match ID: {matches[0].id} for manual testing")

        # Print curl commands for quick testing
        print(f"\n📋 Quick Test Commands:")
        print(f"\n1. Check match history:")
        print(f"   curl http://localhost:8000/api/admin/matches/{matches[0].id}/history")

        print(f"\n2. Check pipeline status:")
        print(f"   curl http://localhost:8000/admin/pipeline-status")

        print(f"\n3. Check system health:")
        print(f"   curl http://localhost:8000/admin/health")

        print(f"\n4. Check agents status:")
        print(f"   curl http://localhost:8000/admin/agents/status")

        print("\n" + "="*60 + "\n")


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Generate test data for PandaPower E2E testing"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--limit", "-l", type=int, default=5, help="Number of candidates to create")
    parser.add_argument("--cleanup-only", action="store_true", help="Only cleanup, don't create new data")

    args = parser.parse_args()

    # Get async session
    async_session = get_async_session()

    async with async_session() as session:
        generator = TestDataGenerator(verbose=args.verbose, limit=args.limit)

        if args.cleanup_only:
            await generator.cleanup_test_data(session)
            print("\n✅ Cleanup complete. Database reset.\n")
        else:
            await generator.run(session)


if __name__ == "__main__":
    asyncio.run(main())
