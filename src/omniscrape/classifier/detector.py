"""Page-type and anti-bot defense classification.

Classification works on any fetched response (``classify_result``), so the main fetch path no
longer needs a separate probe request. ``PageClassifier.probe`` is kept for callers who want to
inspect a URL without fetching it through a fetcher.

Detection is used to *report* access restrictions. A detected defense is not, by itself, a
reason to escalate: stealth escalation is opt-in (see ``EscalationStrategy``).
"""

import re
import time
from typing import Mapping

from omniscrape.models import DefenseSystem, FetchResult, PageClassification, PageType
from omniscrape.observability.logging import get_logger

logger = get_logger("omniscrape.classifier")

BLOCK_STATUSES = {401, 403, 405, 429, 503}

SPA_INDICATORS = [
    re.compile(r'<div[^>]+id=["\'](?:root|__next|app|__nuxt)["\'][^>]*>\s*</div>', re.IGNORECASE),
    re.compile(r'<script[^>]*>\s*window\.__INITIAL_STATE__\s*=', re.IGNORECASE),
    re.compile(r'<script[^>]*>\s*window\.__NEXT_DATA__\s*=', re.IGNORECASE),
    re.compile(r'<noscript>[^<]*(?:enable|requires?)\s+javascript', re.IGNORECASE),
]

# Interstitial challenge pages (the whole page is the challenge).
_CF_INTERSTITIAL = re.compile(
    r"/cdn-cgi/challenge-platform|cf_chl_opt|<title>\s*(?:Just a moment|Attention Required! \| Cloudflare)",
    re.IGNORECASE,
)
# Also seen on ordinary pages that embed a Turnstile widget in a form; only meaningful on block statuses.
_CF_WIDGET = re.compile(r"challenges\.cloudflare\.com|cf-turnstile", re.IGNORECASE)
_DATADOME = re.compile(r"captcha-delivery\.com|geo\.captcha-delivery|datadome", re.IGNORECASE)
_PERIMETERX = re.compile(r"px-captcha|_pxhd|perimeterx|human\s*challenge", re.IGNORECASE)
_AKAMAI = re.compile(r"Reference\s*#\d+\.[0-9a-f]+|akamai", re.IGNORECASE)
_AWS_WAF = re.compile(r"aws-waf-token|awswaf", re.IGNORECASE)
_KASADA = re.compile(r"ips\.js|kpsdk", re.IGNORECASE)
_TAGS = re.compile(r"<script\b.*?</script>|<style\b.*?</style>|<[^>]+>", re.IGNORECASE | re.DOTALL)


def visible_text_length(html: str) -> int:
    """Approximate length of visible text (scripts, styles and tags stripped)."""
    return len(re.sub(r"\s+", " ", _TAGS.sub(" ", html or "")).strip())


def looks_like_spa(html: str, max_text: int = 300) -> bool:
    """True if the document is an empty client-rendered shell that needs JavaScript."""
    if not html or len(html.strip()) < 500:
        return True
    if visible_text_length(html) >= max_text:
        return False
    return any(p.search(html) for p in SPA_INDICATORS)


def detect_defense(status_code: int, headers: Mapping[str, str], body: str) -> DefenseSystem:
    """Identify an anti-bot system that is actively blocking or challenging this response.

    A CDN header alone (e.g. ``cf-ray`` on a normal 200 page) is NOT a detection: most of the
    web sits behind Cloudflare/Akamai and serves content normally.
    """
    body = body or ""
    head = body[:20000]
    blocked = status_code in BLOCK_STATUSES
    if not blocked:
        # Fast path for normal 2xx/3xx pages: only short interstitial/captcha shells can trigger on 200 OK.
        head_low = head.lower()
        has_cf = ("/cdn-cgi/challenge-platform" in head_low or "cf_chl_opt" in head_low
                  or "just a moment" in head_low or "attention required" in head_low)
        has_other = ("captcha-delivery.com" in head_low or "geo.captcha-delivery" in head_low
                     or "px-captcha" in head_low or "_pxhd" in head_low
                     or "kpsdk" in head_low or "ips.js" in head_low)
        if not has_cf and not has_other:
            return DefenseSystem.NONE
        if not has_cf and visible_text_length(head) < 1500:
            if _DATADOME.search(head):
                return DefenseSystem.DATADOME
            if _PERIMETERX.search(head):
                return DefenseSystem.PERIMETERX
            if _KASADA.search(head):
                return DefenseSystem.KASADA
        if not has_cf:
            return DefenseSystem.NONE

    h = {k.lower(): str(v).lower() for k, v in (headers or {}).items()}
    server = h.get("server", "")

    # Interstitials are sometimes served with 200, so that check stands alone. A Turnstile widget alone
    # (a protected login form on a normal page) is not a block.
    if _CF_INTERSTITIAL.search(head) and (blocked or visible_text_length(head) < 2000):
        return DefenseSystem.CLOUDFLARE
    if not blocked:
        return DefenseSystem.NONE
    if _CF_WIDGET.search(head):
        return DefenseSystem.CLOUDFLARE

    if "cloudflare" in server or "cf-ray" in h or "cf-mitigated" in h:
        return DefenseSystem.CLOUDFLARE
    if "x-datadome" in h or any(k.startswith("x-dd-") for k in h) or _DATADOME.search(head):
        return DefenseSystem.DATADOME
    if _PERIMETERX.search(head):
        return DefenseSystem.PERIMETERX
    if any(k.startswith("x-kpsdk") for k in h) or (status_code == 429 and _KASADA.search(head)):
        return DefenseSystem.KASADA
    if "x-amzn-waf-action" in h or _AWS_WAF.search(head):
        return DefenseSystem.AWS_WAF
    if "akamaighost" in server or (status_code == 403 and _AKAMAI.search(head)):
        return DefenseSystem.AKAMAI
    return DefenseSystem.NONE


def classify_result(result: FetchResult) -> PageClassification:
    """Classify an already-fetched response."""
    notes: list[str] = []
    defense = result.defense_detected
    if defense == DefenseSystem.NONE:
        defense = detect_defense(result.status_code, result.headers, result.html)

    if defense != DefenseSystem.NONE or result.status_code in (403, 503):
        notes.append(f"Access restricted (HTTP {result.status_code}, defense={defense.value})")
        return PageClassification(
            url=result.url,
            page_type=PageType.ANTI_BOT,
            defense_system=defense,
            confidence=0.9,
            probe_latency_ms=result.latency_ms,
            recommended_fetcher="StealthFetcher",
            notes=notes,
        )

    if result.status_code == 200 and looks_like_spa(result.html):
        notes.append("Empty client-rendered shell detected")
        return PageClassification(
            url=result.url,
            page_type=PageType.DYNAMIC_SPA,
            defense_system=defense,
            confidence=0.85,
            probe_latency_ms=result.latency_ms,
            recommended_fetcher="DynamicFetcher",
            notes=notes,
        )

    return PageClassification(
        url=result.url,
        page_type=PageType.STATIC,
        defense_system=defense,
        confidence=0.9,
        probe_latency_ms=result.latency_ms,
        recommended_fetcher="FastFetcher",
        notes=notes,
    )


class PageClassifier:
    """Probes a URL to discover the required fetcher tier and any blocking defense."""

    async def probe(self, url: str, timeout: float = 10.0) -> PageClassification:
        from curl_cffi.requests import AsyncSession

        start_time = time.perf_counter()
        try:
            async with AsyncSession(impersonate="chrome") as session:
                resp = await session.get(url, timeout=timeout, allow_redirects=True)
            latency_ms = (time.perf_counter() - start_time) * 1000
            result = FetchResult(
                url=str(resp.url),
                status_code=resp.status_code,
                headers=dict(resp.headers),
                html=resp.text or "",
                latency_ms=round(latency_ms, 2),
            )
            return classify_result(result)
        except Exception as exc:
            latency_ms = (time.perf_counter() - start_time) * 1000
            return PageClassification(
                url=url,
                page_type=PageType.UNKNOWN,
                defense_system=DefenseSystem.NONE,
                confidence=0.2,
                probe_latency_ms=round(latency_ms, 2),
                recommended_fetcher="FastFetcher",
                notes=[f"Probe exception: {exc}"],
            )

    # Backward-compatible attribute aliases
    SPA_INDICATORS = SPA_INDICATORS
    TURNSTILE_INDICATOR = re.compile(r'class=["\'][^"\']*cf-turnstile[^"\']*["\']', re.IGNORECASE)
    DATADOME_INDICATOR = re.compile(r"datadome\.js|dd\.js", re.IGNORECASE)

