# Selectors, Schemas & Extraction

OmniScrape provides both explicit CSS/XPath parsing via [`Selector`](../src/omniscrape/parsers/selector.py) and zero-config structured extraction for commerce, news, and category pages.

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

When you only need fast CSS selection (no XPath or `adaptive=True`), install `omniscrape[fast]` and pass `backend="selectolax"`:

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

---

## Zero-Config Structured Extraction

- **`extract_product(html, url)`**: Returns a [`Product`](../src/omniscrape/models.py) model combining JSON-LD (`@id` reference resolution), Microdata, RDFa, OpenGraph, Shopify JSON, and DOM fallbacks.
- **`extract_listings(html_or_root, url="", min_repetition=3)`**: Detects repeated cards on category/catalog/search pages and extracts `title`, `url`, `price`, `currency`, and `image`.
- **`extract_metadata(html, url="")`**: Extracts normalized page metadata (`title`, `author`, `published_date`, `modified_date`, `site_name`, `description`, `language`, `tags`).
- **`TableParser`** & normalizers (`parse_price`, `parse_date`, `parse_unit`).
