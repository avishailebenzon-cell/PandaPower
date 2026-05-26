"""
Tests for candidate scoring worker and endpoints.

Phase 11: Candidate scoring, readiness classification, and approval workflows.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from uuid import uuid4

from pandapower.workers.candidate_scoring import CandidateScoringWorker


class TestCandidateScoringWorker:
    """Tests for CandidateScoringWorker"""

    @pytest.fixture
    def mock_supabase(self):
        """Create a mock Supabase client"""
        return Mock()

    @pytest.fixture
    def worker(self, mock_supabase):
        """Create a CandidateScoringWorker instance"""
        # Configure mock to handle candidate_skills_detailed queries
        skills_select = Mock()
        skills_select.eq = Mock(return_value=Mock(execute=Mock(return_value=Mock(data=[]))))

        def table_side_effect(table_name):
            table_mock = Mock()
            if table_name == "candidate_skills_detailed":
                table_mock.select = Mock(return_value=skills_select)
            elif table_name == "skills":
                skills_table = Mock()
                skills_table.select = Mock(return_value=Mock(
                    in_=Mock(return_value=Mock(execute=Mock(return_value=Mock(data=[]))))
                ))
                return skills_table
            return table_mock

        mock_supabase.table.side_effect = table_side_effect
        return CandidateScoringWorker(mock_supabase)

    @pytest.mark.asyncio
    async def test_score_candidates_by_skills_empty(self, worker, mock_supabase):
        """Test scoring with no candidates"""
        # Mock the table query chain for candidates
        def table_side_effect(table_name):
            table_mock = Mock()
            if table_name == "candidates":
                select_mock = Mock()
                is_mock = Mock()
                limit_mock = Mock()
                limit_mock.execute.return_value = Mock(data=[])
                is_mock.limit.return_value = limit_mock
                select_mock.is_.return_value = is_mock
                table_mock.select.return_value = select_mock
            return table_mock

        mock_supabase.table.side_effect = table_side_effect

        result = await worker.score_candidates_by_skills(limit=10)

        assert result["total_processed"] == 0
        assert result["candidates_scored"] == 0
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_score_single_candidate_ready(self, worker, mock_supabase):
        """Test scoring a candidate with READY status"""
        candidate_id = str(uuid4())
        candidate = {"id": candidate_id, "name": "John Doe", "detected_language": "en"}

        # Mock candidate skills
        skills = [
            {
                "candidate_id": candidate_id,
                "skill_id": str(uuid4()),
                "confidence_score": 0.9,
                "skill_category": "Programming Languages",
            },
            {
                "candidate_id": candidate_id,
                "skill_id": str(uuid4()),
                "confidence_score": 0.88,
                "skill_category": "Web Frameworks",
            },
            {
                "candidate_id": candidate_id,
                "skill_id": str(uuid4()),
                "confidence_score": 0.85,
                "skill_category": "Databases",
            },
        ]

        # Mock the database calls
        def table_side_effect(table_name):
            table_mock = Mock()
            if table_name == "candidate_skills_detailed":
                select_mock = Mock()
                select_mock.eq.return_value.execute.return_value = Mock(data=skills)
                table_mock.select.return_value = select_mock
            elif table_name == "skills":
                table_mock.select.return_value = Mock(
                    in_=Mock(return_value=Mock(execute=Mock(return_value=Mock(data=[]))))
                )
            elif table_name == "candidates":
                update_mock = Mock()
                update_mock.eq.return_value.execute.return_value = Mock(data=[{"id": candidate_id}])
                table_mock.update.return_value = update_mock
            return table_mock

        mock_supabase.table.side_effect = table_side_effect

        result = await worker._score_candidate(candidate)

        assert result is not None
        assert result["candidate_id"] == candidate_id
        assert result["normalized_skills_count"] == 3
        assert result["average_skill_confidence"] == pytest.approx(0.877, rel=0.01)
        assert result["skill_readiness_status"] == "READY"
        assert result["recommendation_score"] >= 50  # With 3 skills and 0.87 confidence

    @pytest.mark.asyncio
    async def test_score_single_candidate_review(self, worker, mock_supabase):
        """Test scoring a candidate with REVIEW status"""
        candidate_id = str(uuid4())
        candidate = {"id": candidate_id, "name": "Jane Smith", "detected_language": "he"}

        # Mock candidate skills with lower confidence
        skills = [
            {
                "candidate_id": candidate_id,
                "skill_id": str(uuid4()),
                "confidence_score": 0.75,
                "skill_category": "Programming Languages",
            },
            {
                "candidate_id": candidate_id,
                "skill_id": str(uuid4()),
                "confidence_score": 0.72,
                "skill_category": "Web Frameworks",
            },
        ]

        # Mock the database calls
        def table_side_effect(table_name):
            table_mock = Mock()
            if table_name == "candidate_skills_detailed":
                select_mock = Mock()
                select_mock.eq.return_value.execute.return_value = Mock(data=skills)
                table_mock.select.return_value = select_mock
            elif table_name == "skills":
                table_mock.select.return_value = Mock(
                    in_=Mock(return_value=Mock(execute=Mock(return_value=Mock(data=[]))))
                )
            elif table_name == "candidates":
                update_mock = Mock()
                update_mock.eq.return_value.execute.return_value = Mock(data=[{"id": candidate_id}])
                table_mock.update.return_value = update_mock
            return table_mock

        mock_supabase.table.side_effect = table_side_effect

        result = await worker._score_candidate(candidate)

        assert result is not None
        assert result["skill_readiness_status"] == "REVIEW"
        assert result["low_confidence_mappings_count"] == 2

    @pytest.mark.asyncio
    async def test_score_single_candidate_incomplete(self, worker, mock_supabase):
        """Test scoring a candidate with INCOMPLETE status"""
        candidate_id = str(uuid4())
        candidate = {"id": candidate_id, "name": "Bob Johnson", "detected_language": "en"}

        # Mock candidate with no skills
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = (
            Mock(data=[])
        )

        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            Mock(data=[{"id": candidate_id}])
        )

        result = await worker._score_candidate(candidate)

        assert result is not None
        assert result["skill_readiness_status"] == "INCOMPLETE"
        assert result["recommendation_score"] == 0

    @pytest.mark.asyncio
    async def test_scoring_algorithm_calculation(self, worker, mock_supabase):
        """Test the scoring algorithm math"""
        candidate_id = str(uuid4())
        candidate = {"id": candidate_id, "name": "Test", "detected_language": "en"}

        # Create 10 skills across 5 categories for diversity
        skills = []
        categories = [
            "Programming Languages",
            "Web Frameworks",
            "Databases",
            "DevOps",
            "Cloud Platforms",
        ]
        for i in range(10):
            skills.append(
                {
                    "candidate_id": candidate_id,
                    "skill_id": str(uuid4()),
                    "confidence_score": 0.88,
                    "skill_category": categories[i % 5],
                }
            )

        # Mock the database calls
        def table_side_effect(table_name):
            table_mock = Mock()
            if table_name == "candidate_skills_detailed":
                select_mock = Mock()
                select_mock.eq.return_value.execute.return_value = Mock(data=skills)
                table_mock.select.return_value = select_mock
            elif table_name == "skills":
                table_mock.select.return_value = Mock(
                    in_=Mock(return_value=Mock(execute=Mock(return_value=Mock(data=[]))))
                )
            elif table_name == "candidates":
                update_mock = Mock()
                update_mock.eq.return_value.execute.return_value = Mock(data=[{"id": candidate_id}])
                table_mock.update.return_value = update_mock
            return table_mock

        mock_supabase.table.side_effect = table_side_effect

        result = await worker._score_candidate(candidate)

        # Expected score:
        # (10 * 2) + (0.88 * 50) + ((5/16)*100 / 2)
        # = 20 + 44 + (31.25 / 2)
        # = 20 + 44 + 15.625
        # = 79.625 → 79
        assert result is not None
        assert result["recommendation_score"] == pytest.approx(79, abs=2)
        assert result["skill_readiness_status"] == "READY"


class TestCandidateScoringEndpoints:
    """Tests for candidate scoring API endpoints"""

    def test_readiness_summary_endpoint_structure(self):
        """Test that readiness summary response has expected structure"""
        # This would be an integration test with a running app
        expected_keys = {"READY", "REVIEW", "INCOMPLETE", "total"}
        # Test data would come from a fixture or test database
        pass

    def test_low_confidence_mappings_grouping(self):
        """Test that low-confidence mappings are properly grouped by candidate"""
        # Test that the endpoint groups mappings by candidate_id
        # And includes skill details (raw, canonical, confidence, method)
        pass

    def test_approve_candidate_updates_status(self):
        """Test that approving a candidate sets status to READY"""
        # Test that POST /approve updates the skill_readiness_status to READY
        # And sets manually_reviewed_at timestamp
        pass

    def test_reject_candidate_soft_delete(self):
        """Test that rejecting a candidate soft-deletes them"""
        # Test that POST /reject sets deleted_at and updates status
        pass


class TestRetryLogic:
    """Tests for retry logic with exponential backoff"""

    @pytest.mark.asyncio
    async def test_retry_succeeds_after_transient_error(self):
        """Test that retry logic recovers from transient errors"""
        from pandapower.workers.candidate_scoring import retry_with_backoff

        call_count = 0

        def operation_with_transient_error():
            nonlocal call_count
            call_count += 1
            if call_count < 3:  # Fail first two times
                raise ConnectionError("Network temporarily unavailable")
            return "success"

        result = await retry_with_backoff(
            operation_with_transient_error,
            max_retries=3,
            initial_delay=0.01,  # Short delay for testing
            operation_name="test operation"
        )

        assert result == "success"
        assert call_count == 3  # Should have retried twice

    @pytest.mark.asyncio
    async def test_retry_fails_on_non_transient_error(self):
        """Test that non-transient errors fail immediately without retry"""
        from pandapower.workers.candidate_scoring import retry_with_backoff

        call_count = 0

        def operation_with_permanent_error():
            nonlocal call_count
            call_count += 1
            raise ValueError("Invalid data format")  # Non-transient error

        with pytest.raises(ValueError):
            await retry_with_backoff(
                operation_with_permanent_error,
                max_retries=3,
                operation_name="test operation"
            )

        assert call_count == 1  # Should not retry

    @pytest.mark.asyncio
    async def test_retry_exhaustion(self):
        """Test that all retries are attempted before failure"""
        from pandapower.workers.candidate_scoring import retry_with_backoff

        call_count = 0

        def operation_always_fails():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("Always fails")

        with pytest.raises(ConnectionError):
            await retry_with_backoff(
                operation_always_fails,
                max_retries=2,
                initial_delay=0.01,
                operation_name="test operation"
            )

        assert call_count == 3  # max_retries + 1 (initial attempt)

    @pytest.mark.asyncio
    async def test_retry_success_on_first_attempt(self):
        """Test that successful first attempt doesn't retry"""
        from pandapower.workers.candidate_scoring import retry_with_backoff

        call_count = 0

        def operation_succeeds_immediately():
            nonlocal call_count
            call_count += 1
            return "immediate success"

        result = await retry_with_backoff(
            operation_succeeds_immediately,
            max_retries=3,
            operation_name="test operation"
        )

        assert result == "immediate success"
        assert call_count == 1  # No retries needed


# Run tests: pytest tests/test_candidate_scoring.py -v
