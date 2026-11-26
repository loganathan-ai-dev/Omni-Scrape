"""Escalation strategy engine for automatic fetcher upgrade."""

from typing import Optional
from omniscrape.fetchers.base import BaseFetcher
from omniscrape.fetchers.browser import DynamicFetcher
from omniscrape.fetchers.http import FastFetcher
from omniscrape.fetchers.stealth import StealthFetcher
from omniscrape.models import FetchResult, PageClassification, PageType, DefenseSystem
from omniscrape.observability.logging import get_logger

logger = get_logger("omniscrape.classifier.strategies")


class EscalationStrategy:
    """Manages automatic fetcher escalation when requests fail or encounter barriers."""

    @staticmethod
    def get_initial_fetcher(classification: PageClassification) -> BaseFetcher:
        if classification.page_type == PageType.ANTI_BOT:
            return StealthFetcher()
        elif classification.page_type == PageType.DYNAMIC_SPA:
            return DynamicFetcher()
        return FastFetcher()

    @staticmethod
    def should_escalate(result: FetchResult) -> Optional[str]:
        """Returns name of next fetcher tier to escalate to, or None."""
        if result.status_code in (403, 503) or result.defense_detected != DefenseSystem.NONE:
            if result.fetcher_tier < 3:
                return "StealthFetcher"

        # If empty body in Tier 1, escalate to JS rendering Tier 2
        if result.fetcher_tier == 1 and len(result.html.strip()) < 500 and result.status_code == 200:
            return "DynamicFetcher"

        return None
