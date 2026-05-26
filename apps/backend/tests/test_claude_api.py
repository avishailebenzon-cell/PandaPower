"""Tests for Claude API client."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json

from pandapower.integrations.claude_api import AnthropicClient


@pytest.fixture
def claude_client():
    """Create a Claude API client for testing."""
    return AnthropicClient(api_key="test-key-12345")


class TestAnthropicClient:
    """Test AnthropicClient class."""

    def test_init(self, claude_client):
        """Test client initialization."""
        assert claude_client.api_key == "test-key-12345"
        assert claude_client.model == "claude-3-5-sonnet-20241022"

    def test_get_token_count(self, claude_client):
        """Test token counting."""
        text = "Hello world" * 100  # ~1200 chars
        tokens = claude_client.get_token_count(text)
        # Rough estimate: ~4 chars per token + 100 buffer
        assert tokens > 200
        assert tokens < 500

    def test_build_extraction_prompt(self, claude_client):
        """Test prompt building."""
        raw_text = "John Doe, john@example.com, +972-54-1234567"
        language = "en"

        system, user = claude_client._build_extraction_prompt(raw_text, language)

        # Verify system prompt
        assert "expert" in system.lower() and "parser" in system.lower()
        assert "return only valid json" in system.lower()

        # Verify user prompt
        assert raw_text in user
        assert language in user
        assert "extracted_fields" in user
        assert "confidence_scores" in user

    def test_extract_json_valid(self, claude_client):
        """Test JSON extraction with valid JSON."""
        response = """
        Here's the extracted data:
        {
            "extracted_fields": {"name": "John Doe"},
            "confidence_scores": {"name": 0.95}
        }
        """

        result = claude_client._extract_json(response)

        assert result["extracted_fields"]["name"] == "John Doe"
        assert result["confidence_scores"]["name"] == 0.95

    def test_extract_json_invalid(self, claude_client):
        """Test JSON extraction with invalid JSON."""
        response = "{invalid json here}"

        with pytest.raises(ValueError, match="Invalid JSON"):
            claude_client._extract_json(response)

    def test_extract_json_no_json(self, claude_client):
        """Test JSON extraction with no JSON."""
        response = "This is just plain text without any JSON"

        with pytest.raises(ValueError, match="No JSON found"):
            claude_client._extract_json(response)

    @pytest.mark.asyncio
    async def test_parse_cv_structured_success(self, claude_client):
        """Test successful CV parsing."""
        mock_response = {
            "content": [
                {
                    "text": json.dumps({
                        "extracted_fields": {
                            "name": "אנה ניקול",
                            "email": "anna@example.com",
                            "phone": "+972544123456",
                            "skills": ["Python", "JavaScript"],
                            "experience": [],
                            "education": [],
                            "clearance_level": None,
                            "geographical_location": "Tel Aviv",
                            "university_1st_degree": None,
                            "university_2nd_degree": None,
                        },
                        "confidence_scores": {
                            "name": 0.98,
                            "email": 0.96,
                            "phone": 0.90,
                            "skills": 0.85,
                            "experience": 0.0,
                            "education": 0.0,
                            "clearance_level": 0.0,
                            "geographical_location": 0.80,
                            "university_1st_degree": 0.0,
                            "university_2nd_degree": 0.0,
                        },
                        "extraction_notes": "Test extraction"
                    })
                }
            ],
            "usage": {
                "input_tokens": 1000,
                "output_tokens": 500,
            }
        }

        with patch.object(claude_client, '_make_request_with_retry', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            result = await claude_client.parse_cv_structured(
                "Test CV content",
                "en"
            )

            assert result["extracted_fields"]["name"] == "אנה ניקול"
            assert result["extracted_fields"]["email"] == "anna@example.com"
            assert result["confidence_scores"]["name"] == 0.98
            assert result["api_response_tokens"]["total_tokens"] == 1500

    @pytest.mark.asyncio
    async def test_parse_cv_structured_invalid_json(self, claude_client):
        """Test CV parsing with invalid JSON response."""
        mock_response = {
            "content": [{"text": "{invalid json}"}],
            "usage": {"input_tokens": 100, "output_tokens": 50}
        }

        with patch.object(claude_client, '_make_request_with_retry', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            with pytest.raises(ValueError):
                await claude_client.parse_cv_structured("Test CV", "en")

    @pytest.mark.asyncio
    async def test_parse_cv_structured_no_content(self, claude_client):
        """Test CV parsing with empty response."""
        mock_response = {
            "content": [],
            "usage": {"input_tokens": 100, "output_tokens": 0}
        }

        with patch.object(claude_client, '_make_request_with_retry', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            with pytest.raises(ValueError, match="No content"):
                await claude_client.parse_cv_structured("Test CV", "en")
