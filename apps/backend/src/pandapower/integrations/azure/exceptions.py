class AzureGraphError(Exception):
    """Base exception for Azure Graph integration."""

    pass


class AzureAuthError(AzureGraphError):
    """Raised when authentication fails."""

    pass


class AzureThrottledError(AzureGraphError):
    """Raised when Azure throttles requests (429)."""

    def __init__(self, message: str, retry_after: int | None = None):
        self.retry_after = retry_after
        super().__init__(message)
