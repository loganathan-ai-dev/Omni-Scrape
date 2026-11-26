"""Snapshot pages from toscrape.com (public scraping sandboxes) into the holdout corpus.

Ground truth comes from the sandbox's known, stable markup. The snapshots are saved to the
repository so the offline suites stay reproducible. Run once:

    python -m benchmarks.corpus.snapshot
"""

import json
import time
import urllib.request

import lxml.html

from benchmarks.common import CORPUS_DIR, norm_text, parse_price

UA = "omniscrape-benchmark/0.2 (+https://toscrape.com sandbox snapshot)"
BOOK_PAGES = [
    "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
    "https://books.toscrape.com/catalogue/sapiens-a-brief-history-of-humankind_996/index.html",
    "https://books.toscrape.com/catalogue/the-requiem-red_995/index.html",
    "https://books.toscrape.com/catalogue/sharp-objects_997/index.html",
]
BOOK_LISTING = "https://books.toscrape.com/catalogue/page-2.html"
QUOTES_LISTING = "https://quotes.toscrape.com/page/2/"


def get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    time.sleep(1.0)  # be polite
    return data.decode("utf-8")


def save(doc_id: str, html: str, truth: dict) -> None:
    out = CORPUS_DIR / "holdout"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{doc_id}.html").write_text(html, encoding="utf-8")
    (out / f"{doc_id}.json").write_text(json.dumps(truth, indent=1), encoding="utf-8")


def main() -> None:
    for i, url in enumerate(BOOK_PAGES):
        html = get(url)
        root = lxml.html.fromstring(html)
        main_el = root.cssselect("div.product_main")[0]
        title = main_el.cssselect("h1")[0].text_content().strip()
        price_text = main_el.cssselect("p.price_color")[0].text_content().strip()
        stock = norm_text(main_el.cssselect("p.availability")[0].text_content())
        desc_el = root.cssselect("#product_description + p")
        save(f"snap_books_product_{i:02d}", html, {
            "type": "product", "url": url, "template": "toscrape_books", "structured_mode": "none",
            "fields": {"title": title, "price": parse_price(price_text), "currency": "GBP",
                       "availability": "InStock" if "in stock" in stock else "OutOfStock"},
            "main_text": "\n".join([title, desc_el[0].text_content().strip() if desc_el else ""]),
            "targets": {
                "title": {"selector": "div.product_main > h1", "text": title},
                "price": {"selector": "div.product_main > p.price_color", "text": price_text},
            },
        })
        print("saved", url)

    html = get(BOOK_LISTING)
    n = len(lxml.html.fromstring(html).cssselect("article.product_pod"))
    save("snap_books_listing_00", html, {
        "type": "listing", "url": BOOK_LISTING, "template": "toscrape_books", "n_cards": n,
        "selectors": {"cards": "article.product_pod", "card_titles": "article.product_pod h3 a",
                      "card_prices": "article.product_pod p.price_color", "card_links": "article.product_pod div.image_container a"},
        "expected_counts": {"cards": n, "card_titles": n, "card_prices": n, "card_links": n},
    })
    html = get(QUOTES_LISTING)
    n = len(lxml.html.fromstring(html).cssselect("div.quote"))
    save("snap_quotes_listing_00", html, {
        "type": "listing", "url": QUOTES_LISTING, "template": "toscrape_quotes", "n_cards": n,
        "selectors": {"cards": "div.quote", "card_titles": "div.quote span.text",
                      "card_prices": "div.quote small.author", "card_links": "div.quote span > a"},
        "expected_counts": {"cards": n, "card_titles": n, "card_prices": n, "card_links": n},
    })
    print("snapshots done")


if __name__ == "__main__":
    main()
