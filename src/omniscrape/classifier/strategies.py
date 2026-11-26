"""Escalation strategy: decides whether a response should be re-fetched with a heavier tier.

Policy:
  * Tier 1 -> Tier 2 (JavaScript rendering) is automatic when the page is an empty client-side
    shell. This is a rendering need, not an access-control issue.
  * Escalating to Tier 3 (stealth) after a block/challenge happens ONLY when the caller passes
    ``allow_stealth=True``. By default a 403 or challenge is returned to the caller as an access
    restriction.
"""

from typing import Optional

from omniscrape.classifier.detector import detect_defense, looks_like_spa
from omniscrape.fetchers.base import BaseFetcher
from omniscrape.models import DefenseSystem, FetchResult, PageClassification, PageType
from omniscrape.observability.logging import get_logger

logger = get_logger("omniscrape.classifier.strategies")

_TIER_NAMES = {1: "FastFetcher", 2: "DynamicFetcher", 3: "StealthFetcher"}


def is_blocked(result: FetchResult) -> bool:
    if result.defense_detected != DefenseSystem.NONE:
        return True
    if result.status_code in (403, 503):
        return True
    return detect_defense(result.status_code, result.headers, result.html) != DefenseSystem.NONE


class EscalationStrategy:
    """Manages automatic fetcher escalation."""

    @staticmethod
    def next_tier(result: FetchResult, allow_stealth: bool = False) -> Optional[int]:
        """Return the tier to retry with, or None to keep this result."""
        if is_blocked(result):
            if allow_stealth and result.fetcher_tier < 3:
                logger.info(f"Access restricted for {result.url}; escalating to stealth tier (allow_stealth=True)")
                return 3
            if not allow_stealth:
                logger.warning(
                    f"Access restricted for {result.url} (HTTP {result.status_code}). "
                    "Returning the response; pass allow_stealth=True to opt into stealth escalation."
                )
            return None

        if result.fetcher_tier == 1 and result.status_code == 200 and looks_like_spa(result.html):
            return 2
        return None

    @staticmethod
    def should_escalate(result: FetchResult, allow_stealth: bool = False) -> Optional[str]:
        """Backward-compatible variant of ``next_tier`` returning a fetcher class name."""
        tier = EscalationStrategy.next_tier(result, allow_stealth=allow_stealth)
        return _TIER_NAMES.get(tier) if tier else None

    @staticmethod
    def initial_tier(classification: PageClassification, allow_stealth: bool = False) -> int:
        if classification.page_type == PageType.ANTI_BOT and allow_stealth:
            return 3
        if classification.page_type == PageType.DYNAMIC_SPA:
            return 2
        return 1

    @staticmethod
    def get_initial_fetcher(classification: PageClassification, allow_stealth: bool = False) -> BaseFetcher:
        from omniscrape.fetchers.registry import create_fetcher

        return create_fetcher(EscalationStrategy.initial_tier(classification, allow_stealth))
