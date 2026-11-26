"""Dynamic page and anti-bot defense classifier."""

import re
import time
from typing import Optional
from curl_cffi.requests import AsyncSession
from omniscrape.models import PageClassification, PageType, DefenseSystem
from omniscrape.observability.logging import get_logger

logger = get_logger("omniscrape.classifier")


class PageClassifier:
    """Probes a URL to discover required fetcher tier and detected anti-bot systems."""

    SPA_INDICATORS = [
        re.compile(r'<div[^>]+id=["\'](?:root|__next|app|__nuxt)["\'][^>]*>\s*</div>', re.IGNORECASE),
        re.compile(r'<div[^>]+id=["\']root["\']>\s*</div>', re.IGNORECASE),
        re.compile(r'<script[^>]*>window\.__INITIAL_STATE__\s*=', re.IGNORECASE),
        re.compile(r'<script[^>]*>window\.__NEXT_DATA__\s*=', re.IGNORECASE),
    ]

    TURNSTILE_INDICATOR = re.compile(r'class=["\'][^"\']*cf-turnstile[^"\']*["\']', re.IGNORECASE)
    DATADOME_INDICATOR = re.compile(r'datadome\.js|dd\.js', re.IGNORECASE)

    async def probe(self, url: str, timeout: float = 10.0) -> PageClassification:
        start_time = time.perf_counter()
        notes = []

        try:
            async with AsyncSession(impersonate="chrome124") as session:
                resp = await session.get(url, timeout=timeout, allow_redirects=True)
                latency_ms = (time.perf_counter() - start_time) * 1000

                headers_lower = {k.lower(): v.lower() for k, v in resp.headers.items()}
                status = resp.status_code
                body = resp.text or ""

                defense = DefenseSystem.NONE
                # Check headers
                if "cf-ray" in headers_lower or "server" in headers_lower and "cloudflare" in headers_lower["server"]:
                    defense = DefenseSystem.CLOUDFLARE
                    notes.append("Cloudflare headers detected")
                elif "x-datadome" in headers_lower or any(k.startswith("x-dd-") for k in headers_lower):
                    defense = DefenseSystem.DATADOME
                    notes.append("DataDome headers detected")

                # Check body for challenges
                if self.TURNSTILE_INDICATOR.search(body) or "challenges.cloudflare.com" in body:
                    defense = DefenseSystem.CLOUDFLARE
                    notes.append("Turnstile challenge found in DOM")
                    return PageClassification(
                        url=url,
                        page_type=PageType.ANTI_BOT,
                        defense_system=defense,
                        confidence=0.95,
                        probe_latency_ms=round(latency_ms, 2),
                        recommended_fetcher="StealthFetcher",
                        notes=notes,
                    )

                if status in (403, 503):
                    notes.append(f"HTTP {status} returned on initial probe")
                    return PageClassification(
                        url=url,
                        page_type=PageType.ANTI_BOT,
                        defense_system=defense,
                        confidence=0.90,
                        probe_latency_ms=round(latency_ms, 2),
                        recommended_fetcher="StealthFetcher",
                        notes=notes,
                    )

                # Check for SPA empty skeleton
                is_spa = any(pattern.search(body) for pattern in self.SPA_INDICATORS)
                text_len = len(re.sub(r'<[^>]+>', '', body).strip())
                if is_spa and text_len < 300:
                    notes.append("Empty SPA container skeleton detected")
                    return PageClassification(
                        url=url,
                        page_type=PageType.DYNAMIC_SPA,
                        defense_system=defense,
                        confidence=0.85,
                        probe_latency_ms=round(latency_ms, 2),
                        recommended_fetcher="DynamicFetcher",
                        notes=notes,
                    )

                # If static with sufficient content
                return PageClassification(
                    url=url,
                    page_type=PageType.STATIC,
                    defense_system=defense,
                    confidence=0.90,
                    probe_latency_ms=round(latency_ms, 2),
                    recommended_fetcher="FastFetcher",
                    notes=notes,
                )

        except Exception as exc:
            latency_ms = (time.perf_counter() - start_time) * 1000
            notes.append(f"Probe exception: {exc}")
            return PageClassification(
                url=url,
                page_type=PageType.UNKNOWN,
                defense_system=DefenseSystem.NONE,
                confidence=0.2,
                probe_latency_ms=round(latency_ms, 2),
                recommended_fetcher="FastFetcher",
                notes=notes,
            )
