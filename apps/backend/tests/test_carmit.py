"""Tests for Carmit Orchestrator (Phase 5)."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from pandapower.workers.carmit import CarmitOrchestrator
from pandapower.integrations.pipedrive import PipedriveClient


@pytest.fixture
def mock_supabase():
    """Mock Supabase client."""
    client = AsyncMock()
    return client


@pytest.fixture
def mock_claude():
    """Mock Claude API client."""
    client = MagicMock()
    client._make_request_with_retry = AsyncMock()
    client._extract_json = MagicMock()
    client.close = AsyncMock()
    return client


@pytest.fixture
def mock_pipedrive():
    """Mock Pipedrive client."""
    client = AsyncMock(spec=PipedriveClient)
    return client


@pytest.fixture
def carmit_orchestrator(mock_supabase, mock_claude, mock_pipedrive):
    """Create Carmit Orchestrator instance."""
    return CarmitOrchestrator(
        supabase_client=mock_supabase,
        anthropic_client=mock_claude,
        pipedrive_client=mock_pipedrive,
    )


@pytest.mark.asyncio
async def test_route_job_to_agent(carmit_orchestrator, mock_supabase, mock_claude):
    """Test job routing to best-fit agent."""
    # Setup mocks
    mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute = AsyncMock(
        return_value=MagicMock(
            data={
                "id": "job-123",
                "title": "Python Developer",
                "description": "Senior Python engineer",
                "required_skills": ["Python", "FastAPI", "PostgreSQL"],
            }
        )
    )

    mock_claude._make_request_with_retry.return_value = {
        "content": [{"text": '{"agent_code": "naama", "confidence": 0.85, "reasoning": "Python skills match"}'}]
    }

    mock_claude._extract_json.return_value = {
        "agent_code": "naama",
        "confidence": 0.85,
        "reasoning": "Python skills match",
    }

    # Test routing
    result = await carmit_orchestrator.route_job_to_agent("job-123")

    # Assertions
    assert result["assigned_agent_code"] == "naama"
    assert result["confidence"] == 0.85
    assert "naama" in result["assigned_agent_name"]
    assert "timestamp" in result


@pytest.mark.asyncio
async def test_check_quality_score_gate():
    """Test quality score gate."""
    orchestrator = CarmitOrchestrator(None, None, None)

    # Test passing gate
    match = {"match_score": 0.85}
    result = await orchestrator._check_quality_score_gate(match)
    assert result["passed"] is True

    # Test failing gate
    match = {"match_score": 0.55}
    result = await orchestrator._check_quality_score_gate(match)
    assert result["passed"] is False


@pytest.mark.asyncio
async def test_check_clearance_gate():
    """Test security clearance gate."""
    orchestrator = CarmitOrchestrator(None, None, None)

    # Test passing gate - candidate has sufficient clearance
    candidate = {"clearance_level": "secret"}
    job = {"required_clearance": "secret"}
    result = await orchestrator._check_clearance_gate(candidate, job)
    assert result["passed"] is True

    # Test failing gate - candidate has insufficient clearance
    candidate = {"clearance_level": "none"}
    job = {"required_clearance": "secret"}
    result = await orchestrator._check_clearance_gate(candidate, job)
    assert result["passed"] is False


@pytest.mark.asyncio
async def test_check_conflict_of_interest_gate():
    """Test conflict of interest detection."""
    orchestrator = CarmitOrchestrator(None, None, None)

    # Test no conflict
    candidate = {"current_company": "Company A"}
    job = {"company": "Company B"}
    result = await orchestrator._check_conflict_of_interest_gate(candidate, job)
    assert result["passed"] is True

    # Test conflict - candidate works at job's company
    candidate = {"current_company": "Company A"}
    job = {"company": "Company A"}
    result = await orchestrator._check_conflict_of_interest_gate(candidate, job)
    assert result["passed"] is False


@pytest.mark.asyncio
async def test_review_match_all_gates_pass(carmit_orchestrator, mock_supabase):
    """Test match review when all gates pass."""
    # Setup mocks
    mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute = AsyncMock(
        return_value=MagicMock(data={"id": "match-123", "candidate_id": "cand-1", "job_id": "job-1", "match_score": 0.85})
    )

    # Mock quality gate checks to all pass
    with patch.object(carmit_orchestrator, "_check_past_rejection_gate", return_value={"passed": True}):
        with patch.object(carmit_orchestrator, "_check_already_declined_gate", return_value={"passed": True}):
            with patch.object(carmit_orchestrator, "_check_conflict_of_interest_gate", return_value={"passed": True}):
                with patch.object(carmit_orchestrator, "_check_clearance_gate", return_value={"passed": True}):
                    with patch.object(carmit_orchestrator, "_check_quality_score_gate", return_value={"passed": True}):
                        result = await carmit_orchestrator.review_match("match-123")

    # Assertions
    assert result["new_state"] == "carmit_approved"
    assert result["decision"] == "approved"


@pytest.mark.asyncio
async def test_review_match_gate_fails(carmit_orchestrator, mock_supabase):
    """Test match review when a gate fails."""
    # Setup mocks
    mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute = AsyncMock(
        return_value=MagicMock(data={"id": "match-123", "candidate_id": "cand-1", "job_id": "job-1", "match_score": 0.55})
    )

    # Mock quality gate checks with one failure
    with patch.object(carmit_orchestrator, "_check_past_rejection_gate", return_value={"passed": True}):
        with patch.object(carmit_orchestrator, "_check_already_declined_gate", return_value={"passed": True}):
            with patch.object(carmit_orchestrator, "_check_conflict_of_interest_gate", return_value={"passed": True}):
                with patch.object(carmit_orchestrator, "_check_clearance_gate", return_value={"passed": True}):
                    with patch.object(
                        carmit_orchestrator,
                        "_check_quality_score_gate",
                        return_value={"passed": False, "reason": "Score too low"},
                    ):
                        result = await carmit_orchestrator.review_match("match-123")

    # Assertions
    assert result["new_state"] == "carmit_rejected"
    assert result["decision"] == "rejected"
    assert "quality_threshold" in result["reasoning"]


class TestPipedriveClient:
    """Tests for Pipedrive client."""

    @pytest.mark.asyncio
    async def test_get_contact_notes(self):
        """Test getting contact notes."""
        client = PipedriveClient("test-token", "https://api.pipedrive.com")

        with patch.object(client, "_make_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {
                "data": [
                    {"id": 1, "content": "Candidate declined offer"},
                    {"id": 2, "content": "Rejected for another role"},
                ]
            }

            result = await client.get_contact_notes("contact-123")
            assert len(result) == 2
            assert result[0]["content"] == "Candidate declined offer"

    @pytest.mark.asyncio
    async def test_write_note_to_deal(self):
        """Test writing note to deal."""
        client = PipedriveClient("test-token", "https://api.pipedrive.com")

        with patch.object(client, "_make_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"data": {"id": 1, "content": "Test note"}}

            result = await client.write_note_to_deal("deal-123", "Test note")
            assert result["id"] == 1
            assert result["content"] == "Test note"

    @pytest.mark.asyncio
    async def test_get_deal_rejections(self):
        """Test getting rejection notes from deal."""
        client = PipedriveClient("test-token", "https://api.pipedrive.com")

        with patch.object(client, "_make_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {
                "data": [
                    {"id": 1, "content": "Candidate rejected offer"},
                    {"id": 2, "content": "General feedback, no rejection"},
                ]
            }

            result = await client.get_deal_rejections("deal-123")
            # Should filter for rejection-related notes
            assert len(result) == 1
            assert "reject" in result[0]["content"].lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
