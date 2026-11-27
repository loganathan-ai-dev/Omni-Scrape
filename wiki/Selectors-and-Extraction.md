# Selectors, Schemas & Extraction

OmniScrape provides both explicit CSS/XPath parsing via [`Selector`](https://github.com/loganathan-ai-dev/Omni-Scrape/blob/main/src/omniscrape/parsers/selector.py) and zero-config structured extraction for commerce, news, and category pages.

---

## CSS & XPath Parsing

`Selector` wraps `lxml.html` by default with Scrapy/Scrapling-compatible pseudo-elements and chaining:

```python
from omniscrape import Selector

sel = Selector(html, url="https://shop.example/list")

titles = sel.css("div.card h3::text").getall()
first_href = sel.css("div.card a::attr(href)").get()
prices = sel.css("span.price").re(r"\$([\d.,]+)")
sku_title = sel.xpath("//div[@data-sku='B2']/h3/text()").get()
```

### Opt-In `selectolax` Backend

When you only need fast CSS selection (no XPath or `adaptive=True`), install `omni-scraper[fast]` (`pip install "omni-scraper[fast]"`) and pass `backend="selectolax"`:

```python
fast_sel = Selector(html, url="https://shop.example/list", backend="selectolax")
fast_titles = fast_sel.css("div.card h3::text").getall()
```

---

## Element Navigation & Similarity

Every `Element` returned by `sel.css(...)` supports:
- **Properties & attributes**: `.tag`, `.text`, `.own_text`, `.html`, `.attrib`, `.get("href")`, `.has_class("active")`, `.urljoin(href)`, `.json()`
- **Regex**: `.re(pattern)`, `.re_first(pattern, default=None)`
- **Tree traversal**: `.parent`, `.children`, `.next`, `.previous`, `.siblings`, `.ancestors`, `.find_ancestor(pred)`
- **Discovery**: `.find_all(...)`, `.find(...)`, `.find_similar(threshold=0.6)`, `sel.find_by_text(...)`, `sel.find_by_regex(...)`
- **Selector synthesis**: `.generate_css_selector()`, `.generate_xpath()`

---

## Declarative `Selector.extract(schema)`

Extract clean Python dicts using inline schema definitions and built-in normalizers:

```python
item = sel.extract({
    "title": "div.pdp h1::text",
    "price": {"selector": "div.pdp .price::text", "type": "price"},
    "rating": {"selector": ".rating::attr(data-score)", "type": "float", "default": 0.0},
    "released": {"selector": "time::attr(datetime)", "type": "date"},
    "tags": {"selector": "ul.tags li::text", "all": True},
})
```

Supported `"type"` normalizers: `"price"`, `"date"`, `"unit"`, `"int"`, `"float"`, `"bool"`, `"str"`.

The same schema format works from the command line: `omniscrape extract URL --schema schema.json` (see [[CLI-Reference]]).

---

## Self-Healing Adaptive Selectors

`AdaptiveEngine` stores 12+ structural, path, attribute, sibling, and content signals per element in SQLite and relocates elements when markup changes (while rejecting genuinely ambiguous ties):

```python
# Baseline run: capture fingerprint
s1 = Selector(html_v1, url="https://shop.example/item/1", adaptive=True, storage="fingerprints.db")
s1.css(".price-current", identifier="price", auto_save=True)

# Redesigned HTML: original CSS breaks -> relocated automatically
s2 = Selector(html_v2, url="https://shop.example/item/1", adaptive=True, storage="fingerprints.db")
el = s2.css(".price-current", identifier="price", adaptive=True)[0]
print(el.text)
```

See [[Benchmarks]] for how this performs against a mutation corpus (a self-generated one, so read the caveats).

---

## Zero-Config Structured Extraction

- **`extract_product(html, url)`**: Returns a [`Product`](https://github.com/loganathan-ai-dev/Omni-Scrape/blob/main/src/omniscrape/models.py) model combining JSON-LD (`@id` reference resolution), Microdata, RDFa, OpenGraph, Shopify JSON, and DOM fallbacks.
- **`extract_listings(html_or_root, url="", min_repetition=3)`**: Detects repeated cards on category/catalog/search pages and extracts `title`, `url`, `price`, `currency`, and `image`.
- **`extract_metadata(html, url="")`**: Extracts normalized page metadata (`title`, `author`, `published_date`, `modified_date`, `site_name`, `description`, `language`, `tags`).
- **`TableParser`** & normalizers (`parse_price`, `parse_date`, `parse_unit`).

---

## See also

- [[Markdown-and-Agents]]: turn pages into LLM-ready Markdown.
- [[Crawling-and-Storage]]: use `selector.extract(...)` inside a spider.

## Any Page Type: Recipes, Events, Jobs, Reviews, FAQ, Contacts, Pagination

Every `scrape()` result now says what kind of page it is and carries everything zero-config extraction found:

```python
import omniscrape

page = await omniscrape.scrape(url)
page.content_type      # product | article | recipe | event | job | listing | faq | organization | other
ents = page.entities
ents.recipe            # Recipe: ingredients, instructions, prep/cook/total minutes, servings, calories, rating
ents.events            # [Event]: start/end date, status, attendance mode, location, organizer, price, ticket URL
ents.jobs              # [JobPosting]: company, location, remote, employment type, salary min/max/currency/period
ents.reviews           # [Review]: author, rating, title, body, date (+ ents.rating, ents.rating_count)
ents.faq               # [FAQItem]: question, answer (FAQPage markup or <details> accordions)
ents.organization      # Organization: name, logo, emails, phones, address, social profiles
ents.breadcrumbs       # [Breadcrumb]: name, url
ents.next_page         # next page of results (rel=next, "Next" buttons, numbered pagers)
ents.tables            # data tables as lists of row dicts
```

The same functions work on HTML you already have: `extract_entities(html, url)`, `detect_content_type(html, url)`,
`extract_recipe`, `extract_events`, `extract_jobs`, `extract_reviews`, `extract_faq`, `extract_organization`,
`extract_breadcrumbs`, `find_next_page` and `extract_tables` (source: [`extract/entities.py`](https://github.com/loganathan-ai-dev/Omni-Scrape/blob/main/src/omniscrape/extract/entities.py)).

- Structured data (JSON-LD, Microdata, RDFa) is read first; DOM fallbacks cover breadcrumb `<nav>`s, `<details>`
  FAQs, `mailto:`/`tel:` links and visible emails, pagers and data tables.
- "Next post" / "Next article" links are not treated as pagination.
- Page-type detection uses structured data when present, otherwise page signals (repeated item links and prices
  for listings, a priced product for product pages, article text). On the 143 labelled benchmark pages it matches
  the labels on 141.
- `scrape()` only reports `product` on product pages (or pages with Product markup) and no `article` on product or
  listing pages, so heuristic false positives no longer leak into results.
