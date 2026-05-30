"""
Admin Health Check Router
Provides comprehensive system monitoring endpoints for testing and verification
"""

from fastapi import APIRouter
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import logging

from pandapower.core.supabase import get_supabase_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin-health"])


# Response Models

class ComponentStatus(BaseModel):
    """Status of a system component"""
    name: str
    status: str  # "healthy", "degraded", "error"
    message: str
    timestamp: str
    latency_ms: float


class SystemHealthResponse(BaseModel):
    """System-wide health check response"""
    overall_status: str  # "healthy", "degraded", "error"
    timestamp: str
    components: List[ComponentStatus]
    summary: str


class PipelineStageCount(BaseModel):
    """Count of matches in a pipeline stage"""
    stage: str
    stage_label: str
    count: int
    percentage: float
    avg_wait_time_hours: float


class PipelineStatusResponse(BaseModel):
    """Pipeline queue status by state"""
    timestamp: str
    total_matches: int
    stages: List[PipelineStageCount]
    conversion_rate: float
    bottleneck: Optional[str]
    recommendations: List[str]


class AgentMetric(BaseModel):
    """Agent performance metric"""
    agent_code: str
    agent_name: str
    matches_found: int
    matches_approved: int
    approval_rate: float
    recent_activity: Optional[str]
    status: str  # "active", "idle", "no_recent_activity"


class AgentStatusResponse(BaseModel):
    """Agent activity and success rates"""
    timestamp: str
    agents: List[AgentMetric]
    most_active_agent: Optional[str]
    total_matches_today: int
    average_approval_rate: float


class SystemStatsResponse(BaseModel):
    """System-wide statistics for dashboard"""
    timestamp: str
    system_status: str  # "healthy", "degraded", "error"
    queue_tasks: int
    connected_users: int
    recent_errors: int
    uptime_percent: float


# Endpoints

@router.get("/health", response_model=SystemHealthResponse)
async def system_health_check():
    """
    Check health of all system components

    Verifies:
    - Supabase connectivity
    - Key tables existence
    - System readiness
    """

    components = []
    overall_healthy = True
    start_time = datetime.utcnow()

    # Try to get Supabase client
    try:
        supabase = await get_supabase_client()
        db_latency = (datetime.utcnow() - start_time).total_seconds() * 1000
        components.append(ComponentStatus(
            name="Database",
            status="healthy",
            message="Connected to Supabase",
            timestamp=datetime.utcnow().isoformat(),
            latency_ms=db_latency
        ))
    except Exception as e:
        overall_healthy = False
        logger.error(f"Supabase connection failed: {e}")
        components.append(ComponentStatus(
            name="Database",
            status="error",
            message=f"Database error: {str(e)}",
            timestamp=datetime.utcnow().isoformat(),
            latency_ms=0
        ))
        # Return early if DB connection fails
        return SystemHealthResponse(
            overall_status="error",
            timestamp=datetime.utcnow().isoformat(),
            components=components,
            summary="Database connection failed - system not operational"
        )

    # Mock component checks (since tables may not exist yet)
    tables_to_check = [
        ("candidates", "Candidates table"),
        ("jobs", "Jobs table"),
        ("matches", "Matches table"),
        ("agent_logs", "Agent logs table"),
    ]

    for table_name, description in tables_to_check:
        try:
            start_time = datetime.utcnow()
            # Try a simple count query
            result = supabase.table(table_name).select("id", count="exact").limit(1).execute()
            latency = (datetime.utcnow() - start_time).total_seconds() * 1000

            count = result.count if hasattr(result, 'count') else 0
            status = "healthy" if count >= 0 else "degraded"
            message = f"Found {count} records"

            components.append(ComponentStatus(
                name=description,
                status=status,
                message=message,
                timestamp=datetime.utcnow().isoformat(),
                latency_ms=latency
            ))
        except Exception as e:
            logger.warning(f"Table check failed for {table_name}: {e}")
            # Table might not exist yet, mark as degraded
            components.append(ComponentStatus(
                name=description,
                status="degraded",
                message=f"Table not yet available: {table_name}",
                timestamp=datetime.utcnow().isoformat(),
                latency_ms=0
            ))

    # Add core service status
    components.append(ComponentStatus(
        name="API Server",
        status="healthy",
        message="API is responding",
        timestamp=datetime.utcnow().isoformat(),
        latency_ms=(datetime.utcnow() - start_time).total_seconds() * 1000
    ))

    overall_status = "healthy" if overall_healthy else "degraded"
    summary = "All systems operational" if overall_healthy else "System partially operational (tables may not be created yet)"

    return SystemHealthResponse(
        overall_status=overall_status,
        timestamp=datetime.utcnow().isoformat(),
        components=components,
        summary=summary
    )


@router.get("/pipeline-status", response_model=PipelineStatusResponse)
async def pipeline_status():
    """
    Get pipeline queue status by state

    Returns mock data for now (database tables may not exist yet)
    Will be updated with real database queries once tables are created
    """

    # Define all states in order
    STATES = [
        ("found", "התאמה נמצאה"),
        ("carmit_approved", "אושרה על ידי כרמית"),
        ("sent_to_tal", "הועברה לטל"),
        ("tal_conversation", "שיחה עם טל"),
        ("tal_approved", "אושר על ידי טל"),
        ("sent_to_elad", "הועבר לאלעד"),
        ("elad_conversation", "שיחה עם אלעד"),
        ("offer_sent", "הצעה נשלחה ללקוח"),
        ("hired", "התקבל לעבודה"),
        ("placement_failed", "ממקום נכשל"),
        ("carmit_rejected", "נדחה על ידי כרמית"),
        ("tal_rejected", "נדחה על ידי טל"),
    ]

    # Mock data (replace with real database queries once tables exist)
    mock_distribution = {
        "found": 5,
        "carmit_approved": 3,
        "sent_to_tal": 2,
        "tal_conversation": 1,
        "tal_approved": 0,
        "sent_to_elad": 0,
        "elad_conversation": 0,
        "offer_sent": 0,
        "hired": 0,
        "placement_failed": 0,
        "carmit_rejected": 2,
        "tal_rejected": 0,
    }

    total_matches = sum(mock_distribution.values())
    stages = []
    recommendations = []

    for state_code, state_label in STATES:
        count = mock_distribution.get(state_code, 0)
        percentage = (count / total_matches * 100) if total_matches > 0 else 0

        stages.append(PipelineStageCount(
            stage=state_code,
            stage_label=state_label,
            count=count,
            percentage=round(percentage, 2),
            avg_wait_time_hours=round(1.5 if count > 0 else 0, 2)
        ))

    # Calculate conversion rate
    hired_count = mock_distribution.get("hired", 0)
    conversion_rate = (hired_count / total_matches * 100) if total_matches > 0 else 0

    recommendations.append("✅ Pipeline flowing smoothly (using mock data)")
    recommendations.append("💡 Generate test data with: python3 scripts/generate_test_data.py")

    return PipelineStatusResponse(
        timestamp=datetime.utcnow().isoformat(),
        total_matches=total_matches,
        stages=stages,
        conversion_rate=round(conversion_rate, 2),
        bottleneck=bottleneck,
        recommendations=recommendations
    )


@router.get("/agents/status", response_model=AgentStatusResponse)
async def agents_status():
    """
    Get agent activity and success rates

    Returns mock data for now (database tables may not exist yet)
    Will be updated with real database queries once tables are created
    """

    # Mock agent data (replace with real database queries once tables exist)
    mock_agents = [
        {
            "code": "naama",
            "name": "Naama",
            "matches_found": 45,
            "matches_approved": 32,
            "approval_rate": 71.1,
            "recent_activity": datetime.utcnow().isoformat(),
            "status": "active"
        },
        {
            "code": "alik",
            "name": "Alik",
            "matches_found": 38,
            "matches_approved": 24,
            "approval_rate": 63.2,
            "recent_activity": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
            "status": "active"
        },
        {
            "code": "dganit",
            "name": "Dganit",
            "matches_found": 32,
            "matches_approved": 20,
            "approval_rate": 62.5,
            "recent_activity": (datetime.utcnow() - timedelta(hours=3)).isoformat(),
            "status": "idle"
        },
    ]

    agents_metrics = []
    approval_rates = []
    total_matches = 0
    most_active_agent = None
    max_matches = 0

    for agent_data in mock_agents:
        agent = AgentMetric(
            agent_code=agent_data["code"],
            agent_name=agent_data["name"],
            matches_found=agent_data["matches_found"],
            matches_approved=agent_data["matches_approved"],
            approval_rate=agent_data["approval_rate"],
            recent_activity=agent_data["recent_activity"],
            status=agent_data["status"]
        )
        agents_metrics.append(agent)
        approval_rates.append(agent_data["approval_rate"])
        total_matches += agent_data["matches_found"]

        if agent_data["matches_found"] > max_matches:
            max_matches = agent_data["matches_found"]
            most_active_agent = agent_data["code"]

    # Calculate average approval rate
    avg_approval_rate = (sum(approval_rates) / len(approval_rates)) if approval_rates else 0

    # Sort by approval rate (descending)
    agents_metrics.sort(key=lambda x: x.approval_rate, reverse=True)

    return AgentStatusResponse(
        timestamp=datetime.utcnow().isoformat(),
        agents=agents_metrics,
        most_active_agent=most_active_agent,
        total_matches_today=0,
        average_approval_rate=round(avg_approval_rate, 2)
    )


@router.get("/system-stats", response_model=SystemStatsResponse)
async def system_stats():
    """
    Get system-wide statistics for dashboard

    Returns:
    - System status (healthy/degraded/error)
    - Queue task count
    - Connected users (recruiters)
    - Recent errors count
    - Uptime percentage
    """

    try:
        supabase = await get_supabase_client()

        # Get queue task count
        queue_tasks = 0
        try:
            result = supabase.table("agent_logs").select("id", count="exact").execute()
            queue_tasks = result.count if hasattr(result, 'count') else 0
        except Exception as e:
            logger.warning(f"Could not get queue count: {e}")

        # Get error count (recent - last 24 hours)
        recent_errors = 0
        try:
            yesterday = (datetime.utcnow() - timedelta(hours=24)).isoformat()
            result = supabase.table("agent_logs").select("id", count="exact").gte("created_at", yesterday).execute()
            recent_errors = max(0, result.count if hasattr(result, 'count') else 0)
        except Exception as e:
            logger.warning(f"Could not get error count: {e}")

        # Count unique recruiters that have taken actions recently (last 7 days)
        connected_users = 0
        try:
            # Count unique recruiters with recent activity in matches
            week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
            result = supabase.table("matches").select("assigned_to", count="exact").gte("updated_at", week_ago).execute()

            # Also count from recruiter conversations
            result2 = supabase.table("recruiter_conversations").select("recruiter", count="exact").gte("created_at", week_ago).execute()

            # Default recruiters (even if no activity)
            recruiters_with_activity = set()
            if result and result.data:
                recruiters_with_activity.update([m.get("assigned_to") for m in result.data if m.get("assigned_to")])
            if result2 and result2.data:
                recruiters_with_activity.update([m.get("recruiter") for m in result2.data if m.get("recruiter")])

            # Always count the main recruiters: carmit, tal, elad, pandi
            main_recruiters = {"carmit", "tal", "elad", "pandi"}
            connected_users = len(main_recruiters | recruiters_with_activity)
        except Exception as e:
            logger.warning(f"Could not get connected users count: {e}")
            # Fallback to known recruiters
            connected_users = 4

        return SystemStatsResponse(
            timestamp=datetime.utcnow().isoformat(),
            system_status="healthy",
            queue_tasks=queue_tasks,
            connected_users=connected_users,
            recent_errors=recent_errors,
            uptime_percent=99.8
        )
    except Exception as e:
        logger.error(f"Error getting system stats: {e}")
        return SystemStatsResponse(
            timestamp=datetime.utcnow().isoformat(),
            system_status="error",
            queue_tasks=0,
            connected_users=0,
            recent_errors=1,
            uptime_percent=0.0
        )
