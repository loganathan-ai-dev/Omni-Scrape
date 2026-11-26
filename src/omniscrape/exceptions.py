"""OmniScrape hierarchical error taxonomy."""

from typing import Any, Optional


class OmniScrapeError(Exception):
    """Base exception for all OmniScrape errors."""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


# 1. Network & Transport Errors
class NetworkError(OmniScrapeError):
    """Base network/transport exception (DNS, connection drop, timeout)."""
    retryable: bool = True


class ConnectionTimeoutError(NetworkError):
    """Request exceeded timeout duration."""
    pass


class DNSResolutionError(NetworkError):
    """Host could not be resolved (not retried: retrying rarely helps)."""
    retryable: bool = False


class SSLHandshakeError(NetworkError):
    """SSL/TLS negotiation failure (not retried)."""
    retryable: bool = False


# 2. Anti-Bot & Access Control Errors
class BlockedError(OmniScrapeError):
    """Target site blocked access or required interactive challenge."""
    retryable: bool = True
    escalate_tier: bool = True


class AntiBot403Error(BlockedError):
    """HTTP 403 Forbidden with anti-bot fingerprint (Cloudflare, DataDome, etc.)."""
    pass


class TurnstileChallengeError(BlockedError):
    """Unsolved Cloudflare Turnstile challenge encountered."""
    pass


class RateLimitError(BlockedError):
    """HTTP 429 Too Many Requests."""

    def __init__(self, message: str, retry_after: Optional[float] = None, details: Optional[dict[str, Any]] = None):
        super().__init__(message, details)
        self.retry_after = retry_after


# 3. Server Errors (5xx)
class ServerError(OmniScrapeError):
    """Target server responded with 5xx status code."""
    retryable: bool = True

    def __init__(self, message: str, status_code: int = 500, details: Optional[dict[str, Any]] = None):
        super().__init__(message, details)
        self.status_code = status_code


# 4. Parsing & Extraction Errors
class ParseError(OmniScrapeError):
    """DOM, HTML, or schema extraction failure."""
    retryable: bool = False


class SelectorNotFoundError(ParseError):
    """Element could not be found with specified selector and adaptive healing failed."""
    pass


class SchemaValidationError(ParseError):
    """Extracted data does not match the target schema."""
    pass


# 5. Configuration & Resilience Errors
class ConfigError(OmniScrapeError):
    """Invalid user configuration, bad proxy, or missing credentials."""
    retryable: bool = False


class CircuitBreakerOpenError(OmniScrapeError):
    """Circuit breaker is open for the target domain."""
    retryable: bool = False
