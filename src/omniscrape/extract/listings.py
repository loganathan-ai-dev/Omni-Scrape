"""Zero-config listing / category page card extraction."""

import re
from typing import Any, Optional, Union
from urllib.parse import urljoin

from omniscrape.normalizers.currency import parse_money
from omniscrape.parsers.density import DensityAnalyzer
from omniscrape.parsers.selector import Selector
from omniscrape.parsers.structured import as_root

_PRICE_RE = re.compile(r"(?:[$€£¥₹]|US\$|A\$|C\$|Rs\.?|USD|EUR|GBP|INR)\s*[\d,.]+|[\d,.]+\s*(?:€|£|₹|USD|EUR|GBP|INR)", re.I)


def extract_listings(
    html_or_root: Union[str, bytes, Any],
    url: str = "",
    *,
    min_repetition: int = 3,
) -> list[dict[str, Any]]:
    """Extract structured items from repeated cards on category, catalog, or search pages."""
    root = Selector(html_or_root, url=url).root if isinstance(html_or_root, (str, bytes)) else as_root(html_or_root)
    cards = DensityAnalyzer(root=root).detect_repeated_cards(min_repetition=min_repetition)
    if not cards:
        return []

    items: list[dict[str, Any]] = []
    for card in cards:
        title_el = (
            card.css_first("h1, h2, h3, h4")
            or card.css_first("[class*='title'], [class*='name']")
            or card.css_first("a[title]")
            or card.css_first("a[href]")
        )
        title = (title_el.get("title") or title_el.text).strip() if title_el is not None else ""
        if not title:
            continue

        link_el = card.css_first("a[href]")
        href = link_el.get("href") if link_el is not None else None
        item_url = urljoin(url, href.strip()) if href else None

        price: Optional[float] = None
        currency: Optional[str] = None
        price_el = card.css_first("[class*='price'], [data-price], [itemprop='price']")
        if price_el is not None:
            price, currency = parse_money(price_el.get("content") or price_el.text)
        if price is None:
            m = _PRICE_RE.search(card.text)
            if m:
                price, currency = parse_money(m.group(0))

        img_el = card.css_first("img[src], img[data-src]")
        img_raw = (img_el.get("src") or img_el.get("data-src")) if img_el is not None else None
        image = urljoin(url, img_raw.strip()) if img_raw and not img_raw.startswith("data:") else None

        entry: dict[str, Any] = {"title": title}
        if item_url:
            entry["url"] = item_url
        if price is not None:
            entry["price"] = price
            if currency:
                entry["currency"] = currency
        if image:
            entry["image"] = image
        items.append(entry)
    return items
