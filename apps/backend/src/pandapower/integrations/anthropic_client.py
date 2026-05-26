"""
Wrapper for Anthropic API client initialization
"""

from anthropic import Anthropic
from pandapower.core.config import settings


class AnthropicClient:
    """Wrapper class for Anthropic API client"""

    def __init__(self, api_key: str = None):
        """
        Initialize Anthropic client

        Args:
            api_key: API key for Anthropic. If not provided, uses ANTHROPIC_API_KEY from config.
        """
        self.api_key = api_key or settings.ANTHROPIC_API_KEY
        self.client = Anthropic(api_key=self.api_key)

    def __getattr__(self, name):
        """Delegate attribute access to the underlying Anthropic client"""
        return getattr(self.client, name)


def get_anthropic_client() -> Anthropic:
    """
    Get initialized Anthropic client with API key from config.

    Returns:
        Anthropic: Initialized client for API calls
    """
    return Anthropic(api_key=settings.ANTHROPIC_API_KEY)
