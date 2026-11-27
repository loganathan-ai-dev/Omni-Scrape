# Quick Start

Install first (see [[Installation]]): `pip install omni-scrape`.

## Scrape one page

```python
import omniscrape

page = omniscrape.scrape_sync("https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html")
page.product.title, page.product.price, page.product.currency   # ('A Light in the Attic', 51.77, 'GBP')
print(page.markdown)                                             # main content only, as clean Markdown
```

## Async and batch scraping

```python
import asyncio
import omniscrape

async def main():
    page = await omniscrape.scrape("https://quotes.toscrape.com/")
    print(page.title)           # page title
    print(page.markdown[:300])  # main-content Markdown, boilerplate removed
    print(page.links[:5])       # absolute links
    print(page.metadata)        # title, author, dates, site name, description, language

    pages = await omniscrape.scrape_many(
        ["https://quotes.toscrape.com/page/1/", "https://quotes.toscrape.com/page/2/"],
        concurrency=4,
        per_domain_concurrency=2,
    )

asyncio.run(main())
```

## Extract fields with a schema

```python
from omniscrape import Selector

page = Selector(html, url="https://shop.example/list")
page.css("div.card h3::text").getall()

item = page.extract({
    "title": "div.pdp h1::text",
    "price": {"selector": "div.pdp .price::text", "type": "price"},
    "tags": {"selector": "ul.tags li::text", "all": True},
})
```

More in [[Selectors-and-Extraction]].

## Crawl a site

```python
import asyncio
from omniscrape import CrawlEngine, JSONLStorage, LinkExtractor, Request, Spider

links = LinkExtractor(same_domain=True)

class Books(Spider):
    name = "books"
    start_urls = ["https://books.toscrape.com/"]
    concurrency = 8

    async def parse(self, response, selector):
        if selector.css("div.product_main"):
            yield {"title": selector.css("h1::text").get(), "price": selector.css("p.price_color::text").get()}
        for url in links.extract(selector, response.url):
            yield Request(url, meta={"from": response.url})   # arrives as response.meta in the callback

stats = asyncio.run(CrawlEngine(
    Books(), storage=JSONLStorage("books.jsonl"), max_pages=200, queue_path="books-queue.db",
).run())
```

More in [[Crawling-and-Storage]].

## From the command line

```bash
omniscrape get https://books.toscrape.com/                      # summary table
omniscrape get URL -f json > page.json                          # data on stdout, logs on stderr
omniscrape crawl https://books.toscrape.com/ --max-pages 100 -o books.jsonl --resume
omniscrape map https://example.com --search pricing
```

Every command is documented in [[CLI-Reference]].

## Next steps

- JavaScript-heavy pages, proxies, retries: [[Fetching-and-Stealth]]
- Markdown for LLMs and RAG: [[Markdown-and-Agents]]
- Give an AI agent scraping tools: [[MCP-Server]]
