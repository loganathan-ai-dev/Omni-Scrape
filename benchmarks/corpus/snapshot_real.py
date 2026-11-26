"""Snapshot permission-friendly real-world pages into the holdout corpus, with site-specific labels.

Ground truth comes from each source's own stable markup (site-specific selectors), never from
OmniScrape's generic extractors, so the holdout stays an independent test. Every URL is checked
against robots.txt and requests are spaced out.

Sources and licences:
  webscraper.io test e-commerce site  - built for scraping practice
  scrapeme.live                       - WooCommerce demo built for scraping practice
  peps.python.org                     - PEPs are public domain / CC0
  go.dev/blog                         - CC BY 4.0
  blog.rust-lang.org                  - MIT / Apache-2.0
  gov.uk news                         - Open Government Licence v3.0

Run once (network):  python -m benchmarks.corpus.snapshot_real
"""

import json
import re
import time
import urllib.request
import urllib.robotparser
from datetime import datetime
from typing import Any, Callable, Optional
from urllib.parse import urljoin, urlsplit

import lxml.html

from benchmarks.common import CORPUS_DIR, parse_price
from benchmarks.corpus.adaptive_cases import make_selector

UA = "omniscrape-benchmark/0.2 (corpus snapshot)"
DELAY = 1.2
BLOCK_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "pre", "td", "th", "dt", "dd", "figcaption", "blockquote"}
_robots: dict[str, urllib.robotparser.RobotFileParser] = {}


def get(url: str) -> Optional[str]:
    base = f"{urlsplit(url).scheme}://{urlsplit(url).netloc}"
    if base not in _robots:
        rp = urllib.robotparser.RobotFileParser(base + "/robots.txt")
        rp.read()
        _robots[base] = rp
    if not _robots[base].can_fetch(UA, url):
        print("  robots.txt disallows, skipping:", url)
        return None
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode("utf-8", "replace")
    time.sleep(DELAY)
    return html


def text(el: Any) -> str:
    return " ".join(el.text_content().split())


def block_text(root: Any, skip: Callable[[Any], bool] = lambda e: False) -> list[str]:
    """Text of leaf-level block elements under root, in document order, without double counting."""
    blocks = [e for e in root.iter() if isinstance(e.tag, str) and e.tag in BLOCK_TAGS and not skip(e)]
    chosen = set(blocks)
    out = []
    for e in blocks:
        if any(d in chosen for d in e.iterdescendants()):
            continue  # its children are captured individually
        t =" ".join(e.text_content().replace("¶", " ").split())
        if t:
            out.append(t)
    return out


def iso_date(s: str) -> Optional[str]:
    s = s.strip().replace("Sept.", "Sep.")
    for fmt in ("%d-%b-%Y", "%d %B %Y", "%b. %d, %Y", "%B %d, %Y", "%Y-%m-%d", "%b %d, %Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def structured_mode(root: Any) -> str:
    for s in root.cssselect('script[type="application/ld+json"]'):
        if "Product" in (s.text or "") or "Article" in (s.text or ""):
            return "jsonld"
    if root.cssselect('[itemtype*="schema.org/Product"], [itemtype*="schema.org/Article"]'):
        return "microdata"
    if root.cssselect('meta[property="og:title"]'):
        return "og_only"
    return "none"


def targets_for(root: Any, els: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for name, el in els.items():
        if el is None:
            continue
        sel = make_selector(root, el)
        if sel:
            out[name] = {"selector": sel, "text": text(el)}
    return out


def save(doc_id: str, html: str, truth: dict[str, Any]) -> None:
    out = CORPUS_DIR / "holdout"
    out.mkdir(parents=True, exist_ok=True)
    truth.setdefault("real_world", True)
    (out / f"{doc_id}.html").write_text(html, encoding="utf-8")
    (out / f"{doc_id}.json").write_text(json.dumps(truth, indent=1, ensure_ascii=False), encoding="utf-8")
    print("  saved", doc_id, "|", truth["fields"].get("title", "")[:60])


# ----------------------------------------------------------------------------- products
def webscraper(n: int = 6) -> None:
    listing = "https://webscraper.io/test-sites/e-commerce/allinone/computers/laptops"
    root = lxml.html.fromstring(get(listing) or "<html/>")
    links = [urljoin(listing, a.get("href")) for a in root.cssselect("a.title")]
    # spread across the listing for variety
    for i, url in enumerate(links[:: max(1, len(links) // n)][:n]):
        html = get(url)
        if not html:
            continue
        r = lxml.html.fromstring(html)
        title_el, price_el = r.cssselect("h4.title")[0], r.cssselect("h4.price")[0]
        reviews = r.cssselect(".ratings p")
        review_count = int(re.search(r"\d+", text(reviews[0])).group(0)) if reviews else None
        desc = r.cssselect(".description")
        fields = {"title": text(title_el), "price": parse_price(text(price_el)), "currency": "USD"}
        if review_count is not None:
            fields["review_count"] = review_count
        save(f"snap_wsio_product_{i:02d}", html, {
            "type": "product", "url": url, "template": "webscraper_testsite", "structured_mode": structured_mode(r),
            "fields": fields, "main_text": "\n".join([fields["title"], text(desc[0]) if desc else ""]),
            "targets": targets_for(r, {"title": title_el, "price": price_el}),
        })


def scrapeme(n: int = 6) -> None:
    listing = "https://scrapeme.live/shop/"
    root = lxml.html.fromstring(get(listing) or "<html/>")
    links = [urljoin(listing, a.get("href")) for a in root.cssselect("li.product a.woocommerce-LoopProduct-link")]
    for i, url in enumerate(links[::2][:n]):
        html = get(url)
        if not html:
            continue
        r = lxml.html.fromstring(html)
        title_el = r.cssselect("h1.product_title")[0]
        price_els = r.cssselect(".summary p.price ins .amount") or r.cssselect(".summary p.price .amount")
        stock = r.cssselect(".summary .stock")
        sku = r.cssselect(".sku")
        short = r.cssselect("div.woocommerce-product-details__short-description")
        fields = {"title": text(title_el), "price": parse_price(text(price_els[0])), "currency": "GBP"}
        if sku and text(sku[0]) not in ("", "N/A"):
            fields["sku"] = text(sku[0])
        if stock:
            fields["availability"] = "OutOfStock" if "out of stock" in text(stock[0]).lower() else "InStock"
        save(f"snap_scrapeme_product_{i:02d}", html, {
            "type": "product", "url": url, "template": "woocommerce_scrapeme", "structured_mode": structured_mode(r),
            "fields": fields, "main_text": "\n".join([fields["title"], text(short[0]) if short else ""]),
            "targets": targets_for(r, {"title": title_el, "price": price_els[0], "stock": stock[0] if stock else None}),
        })


# ----------------------------------------------------------------------------- articles
def peps() -> None:
    for i, num in enumerate(["0008", "0257", "0484", "0572", "0634"]):
        url = f"https://peps.python.org/pep-{num}/"
        html = get(url)
        if not html:
            continue
        r = lxml.html.fromstring(html)
        content = r.cssselect("section#pep-content")[0]
        title = text(r.cssselect("h1.page-title")[0])
        meta = {text(dt).rstrip(":"): text(dd) for dt, dd in zip(content.cssselect("dl.rfc2822 dt"), content.cssselect("dl.rfc2822 dd"))}
        first_author = re.sub(r"\s*<[^>]*>", "", meta.get("Author", "")).split(",")[0].strip()
        header = content.cssselect("dl.rfc2822")
        toc = content.cssselect("details, #contents, nav")
        skip_roots = set(header + toc)

        def skip(e: Any, roots=skip_roots) -> bool:
            return e in roots or any(a in roots for a in e.iterancestors())

        body = [b for b in block_text(content, skip) if b != title]
        fields = {"title": title, "author": first_author}
        if meta.get("Created") and iso_date(meta["Created"]):
            fields["published_date"] = iso_date(meta["Created"])
        save(f"snap_pep_article_{i:02d}", html, {
            "type": "article", "url": url, "template": "python_peps", "structured_mode": structured_mode(r),
            "fields": fields, "main_text": "\n".join([title, *body]),
        })


def go_blog(n: int = 5) -> None:
    index = "https://go.dev/blog/all"
    root = lxml.html.fromstring(get(index) or "<html/>")
    links = [urljoin(index, a.get("href")) for a in root.cssselect("p.blogtitle a")][:n]
    for i, url in enumerate(links):
        html = get(url)
        if not html:
            continue
        r = lxml.html.fromstring(html)
        article = r.cssselect("div.Article")[0]
        title = text(article.cssselect("h1")[-1])
        author_el = article.cssselect("p.author")
        author_text = author_el[0].text_content() if author_el else ""
        m = re.search(r"\d{1,2} [A-Z][a-z]+ \d{4}", author_text)
        names = re.sub(r"\d{1,2} [A-Z][a-z]+ \d{4}", "", author_text).strip()
        first_author = re.split(r",| and ", names)[0].strip() if names else None

        def skip(e: Any) -> bool:
            if e.get("class") in ("author", "Article-nav") or e.tag in ("h1",):
                return True
            return any((a.get("class") or "") in ("author", "Article-nav") for a in e.iterancestors())

        body = [b for b in block_text(article, skip) if not b.startswith(("Next article:", "Previous article:"))]
        fields = {"title": title}
        if first_author:
            fields["author"] = first_author
        if m:
            fields["published_date"] = iso_date(m.group(0))
        save(f"snap_goblog_article_{i:02d}", html, {
            "type": "article", "url": url, "template": "go_blog", "structured_mode": structured_mode(r),
            "fields": fields, "main_text": "\n".join([title, *body]),
        })


def rust_blog(n: int = 4) -> None:
    index = "https://blog.rust-lang.org/"
    root = lxml.html.fromstring(get(index) or "<html/>")
    links = [urljoin(index, a.get("href")) for a in root.cssselect("table.post-list a, td a")]
    links = [l for l in dict.fromkeys(links) if re.search(r"/\d{4}/\d{2}/\d{2}/", l)][:n]
    for i, url in enumerate(links):
        html = get(url)
        if not html:
            continue
        r = lxml.html.fromstring(html)
        post = r.cssselect("div.post")[0]
        meta_el = r.cssselect(".publish-date-author")
        meta_txt = text(meta_el[0]) if meta_el else ""
        date_part, _, author_part = meta_txt.partition("·")
        title_el = (r.cssselect("h2") or [None])[0]
        title = text(title_el) if title_el is not None else ""
        first_author = re.split(r",| and | on behalf of ", author_part.strip())[0].strip() if author_part else None
        body = [b for b in block_text(post) if b != title]
        fields = {"title": title}
        if first_author:
            fields["author"] = first_author
        if iso_date(date_part):
            fields["published_date"] = iso_date(date_part)
        save(f"snap_rustblog_article_{i:02d}", html, {
            "type": "article", "url": url, "template": "rust_blog", "structured_mode": structured_mode(r),
            "fields": fields, "main_text": "\n".join([title, *body]),
        })


def govuk(n: int = 5) -> None:
    search = "https://www.gov.uk/search/news-and-communications"
    root = lxml.html.fromstring(get(search) or "<html/>")
    links = [a.get("href") for a in root.cssselect("a.govuk-link")]
    links = [urljoin("https://www.gov.uk/", l) for l in dict.fromkeys(links) if l and l.startswith("/government/news/")][:n]
    for i, url in enumerate(links):
        html = get(url)
        if not html:
            continue
        r = lxml.html.fromstring(html)
        title = text(r.cssselect("h1")[0])
        dates = [iso_date(text(dd)) for dd in r.cssselect(".gem-c-metadata dd")]
        dates = [d for d in dates if d]
        bodies = r.cssselect("div.govspeak")
        if not bodies:
            print("  no govspeak body, skipping", url)
            continue
        body = block_text(bodies[0])
        fields = {"title": title}
        if dates:
            fields["published_date"] = dates[0]
        save(f"snap_govuk_article_{i:02d}", html, {
            "type": "article", "url": url, "template": "govuk_news", "structured_mode": structured_mode(r),
            "fields": fields, "main_text": "\n".join([title, *body]),
        })


def main() -> None:
    for name, fn in [("webscraper.io", webscraper), ("scrapeme.live", scrapeme), ("PEPs", peps),
                     ("Go blog", go_blog), ("Rust blog", rust_blog), ("GOV.UK", govuk)]:
        print(f"== {name}")
        try:
            fn()
        except Exception as exc:  # keep going; report what failed
            print(f"  FAILED: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
