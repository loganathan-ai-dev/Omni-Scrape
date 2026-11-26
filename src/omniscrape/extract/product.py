"""Zero-config product extraction (no per-site selectors).

Layers, each filling only what earlier layers left empty:
  1. JSON-LD / Microdata / RDFa ``Product`` (offers, AggregateOffer, priceSpecification, ratings)
  2. OpenGraph / product:* meta tags
  3. Embedded storefront JSON (e.g. Shopify ``ProductJson``)
  4. DOM heuristics: title near the top of the product area; price candidates scored by
     class/id hints, strike-through and "was/MRP" context, distance from the title, and
     whether they sit in related-product carousels; labelled brand/SKU/stock/rating text.
"""

import json
import re
from typing import Any, Optional, Union

from omniscrape.content.extract import detect_title, norm
from omniscrape.models import Product
from omniscrape.normalizers.currency import parse_money
from omniscrape.parsers.structured import as_root, extract_structured, find_items, first_text

PRODUCT_TYPES = {"Product", "ProductGroup", "IndividualProduct", "ProductModel", "Book", "Vehicle", "Car",
                 "SomeProducts", "MenuItem"}
PRICE_RE = re.compile(
    r"(?:(?P<sym>US\$|A\$|C\$|NZ\$|HK\$|S\$|R\$|[$€£¥₹₩₽₺₪₫฿₱]|Rs\.?|INR|USD|EUR|GBP|JPY|AUD|CAD|CHF|SEK|NOK|DKK|PLN|BRL|MXN)"
    r"\s?(?P<num1>\d{1,3}(?:[.,\s]\d{2,3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?))"
    r"|(?:(?P<num2>\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)\s?"
    r"(?P<sym2>€|£|zł|kr|Kč|₹|EUR|USD|GBP|PLN|SEK|NOK|DKK|CHF|INR))",
    re.IGNORECASE,
)
GOOD_PRICE = re.compile(r"price|amount|cost|money|sale|offer|current|final|\bnow\b|our-?price|deal|buy|purchase", re.I)
# whole words only: "old" must not match utility classes like "font-semibold"
BAD_PRICE = re.compile(r"(?<![a-z])(old|was|regular|compare|compare-?at|strike|strikethrough|list-?price|mrp|original|"
                       r"before|retail|rrp|saving|savings|discount|per-?unit|unit-?price|shipping|delivery|"
                       r"installment|emi|monthly|basis|crossed)(?![a-z])", re.I)
BAD_LABEL = re.compile(r"(m\.?r\.?p|was|list price|you save|save|rrp|retail|regular|original|typical|from)\W*$", re.I)
BAD_SECTION = re.compile(r"related|recommend|similar|carousel|upsell|cross-?sell|also-?like|you-?may|minicart|"
                         r"mini-?cart|cart-?drawer|bundle|accessor|sponsored|recently|viewed|footer|header|nav|"
                         r"breadcrumb|sidebar|grid-product|product-?(list|grid|card)|tile", re.I)
PRODUCT_AREA = re.compile(r"product|detail|summary|buy-?box|purchase|offer|price-?box|pdp|item-?info|core", re.I)
TITLE_HINT = re.compile(r"product[-_ ]?(title|name)|item[-_ ]?(title|name)|productTitle|\bp?title\b|\bname\b", re.I)
STOCK_RE = re.compile(r"\b(out of stock|sold out|unavailable|currently unavailable|in stock|available now|"
                      r"only \d+ left|\d+ in stock|ships in|pre-?order|back-?order|available)\b", re.I)
SKU_RE = re.compile(r"\b(?:sku|item\s*(?:code|no\.?|number|#)|product\s*(?:code|id)|article\s*(?:no\.?|number)|"
                    r"part\s*(?:no\.?|number)|mpn|model\s*(?:no\.?|number)?|style\s*(?:no\.?|#))\s*[:#]?\s*"
                    r"([A-Za-z0-9][A-Za-z0-9._/-]{1,40})", re.I)
BRAND_LABEL_RE = re.compile(r"^\s*(?:brand|manufacturer|make|by)\s*[:\-]\s*(.{2,60})$", re.I)
RATING_RE = re.compile(r"(\d(?:[.,]\d)?)\s*(?:out of|/|of)\s*5\b|(\d(?:[.,]\d)?)\s*stars?\b|rated\s*(\d(?:[.,]\d)?)", re.I)
REVIEWS_RE = re.compile(r"([\d][\d,.\s]*)\s*(?:customer\s+)?(?:reviews?|ratings?|reseñas|avis|bewertungen)\b", re.I)


def _hint(el: Any) -> str:
    return f"{el.get('class', '')} {el.get('id', '')} {el.get('itemprop', '')} {el.get('data-testid', '')}"


def _ancestors_hint(el: Any, levels: int = 6) -> str:
    out = []
    for i, a in enumerate(el.iterancestors()):
        if i >= levels:
            break
        out.append(_hint(a))
        out.append(a.tag if isinstance(a.tag, str) else "")
    return " ".join(out)


_SPLIT_PRICE_GAP = re.compile(r"(?<=[₹$€£¥.,])\s+(?=\d)|(?<=\d)\s+(?=[.,]\s*\d)")
PRICE_LABEL_RE = re.compile(r"(?i)\b(?:price|our price|sale price|now)\s*[:\-]?\s*(\d{1,3}(?:[.,]\d{2,3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)\b")


def _price_text(el: Any) -> str:
    """Element text with element boundaries kept (no "M341" + "1.850,60" fusion), but split prices
    such as <span>₹</span><span>7,799</span><span>.</span><span>00</span> rejoined."""
    text = " ".join(" ".join(el.itertext()).split())
    while True:
        joined = _SPLIT_PRICE_GAP.sub("", text)
        if joined == text:
            return text
        text = joined


def _in_repeated_block(el: Any, levels: int = 5, min_repeats: int = 3) -> bool:
    """True if el sits inside a run of look-alike siblings (product cards, carousels, grids)."""
    node = el
    for _ in range(levels):
        parent = node.getparent()
        if parent is None:
            return False
        key = (node.tag, node.get("class", ""))
        same = sum(1 for sib in parent if isinstance(sib.tag, str) and (sib.tag, sib.get("class", "")) == key)
        if same >= min_repeats and node.tag not in ("tr", "td", "li", "p", "span", "option", "body", "html"):
            return True
        node = parent
    return False


def _availability(value: Any) -> Optional[str]:
    text = (first_text(value) or "").lower().replace(" ", "")
    if not text:
        return None
    if any(k in text for k in ("outofstock", "soldout", "discontinued", "unavailable")):
        return "OutOfStock"
    if "preorder" in text or "presale" in text:
        return "PreOrder"
    if "backorder" in text:
        return "BackOrder"
    if "instock" in text or "limitedavailability" in text or "onlinesonly" in text or "available" in text or \
            re.search(r"\d+instock|only\d+left|shipsin", text):
        return "InStock"
    return None


def _float(value: Any) -> Optional[float]:
    text = first_text(value)
    if text is None:
        return None
    amount, _ = parse_money(text)
    return amount


class ProductExtractor:
    def __init__(self, root: Any, url: str, structured: dict[str, Any]):
        self.root = root
        self.url = url
        self.s = structured
        self.data: dict[str, Any] = {"metadata": {"sources": {}}}

    def put(self, key: str, value: Any, source: str) -> None:
        if value in (None, "", [], {}) or self.data.get(key) not in (None, "", [], {}):
            return
        self.data[key] = value
        self.data["metadata"]["sources"][key] = source

    # ------------------------------------------------------------------ layer 1
    def from_structured(self) -> None:
        for item in find_items(self.s, PRODUCT_TYPES):
            src = "structured"
            if item.get("hasVariant") and not item.get("offers"):
                variants = item["hasVariant"] if isinstance(item["hasVariant"], list) else [item["hasVariant"]]
                item = {**variants[0], **{k: v for k, v in item.items() if k != "hasVariant"}} if variants and isinstance(variants[0], dict) else item
            self.put("title", first_text(item.get("name")), src)
            self.put("sku", first_text(item.get("sku") or item.get("mpn") or item.get("productID")), src)
            self.put("brand", first_text(item.get("brand") or item.get("manufacturer")), src)
            self.put("description", first_text(item.get("description")), src)
            images = item.get("image")
            if images:
                imgs = images if isinstance(images, list) else [images]
                self.put("images", [first_text(i) for i in imgs if first_text(i)], src)
            rating = item.get("aggregateRating")
            if isinstance(rating, dict):
                self.put("rating", _float(rating.get("ratingValue")), src)
                count = rating.get("reviewCount") or rating.get("ratingCount")
                if count is not None:
                    try:
                        self.put("review_count", int(float(str(first_text(count)).replace(",", ""))), src)
                    except ValueError:
                        pass
            offers = item.get("offers")
            for offer in offers if isinstance(offers, list) else [offers]:
                if not isinstance(offer, dict):
                    continue
                spec = offer.get("priceSpecification")
                spec = spec[0] if isinstance(spec, list) and spec else spec
                price = offer.get("price") or offer.get("lowPrice") or (spec or {}).get("price") if isinstance(spec, (dict, type(None))) else offer.get("price")
                self.put("price", _float(price), src)
                self.put("currency", first_text(offer.get("priceCurrency") or (spec or {}).get("priceCurrency") if isinstance(spec, (dict, type(None))) else offer.get("priceCurrency")), src)
                self.put("availability", _availability(offer.get("availability")), src)
                if self.data.get("price") is not None:
                    break

    # ------------------------------------------------------------------ layer 2
    def from_meta(self) -> None:
        og = self.s["opengraph"]
        is_product = "product" in str(og.get("og:type", "")).lower() or any(k.startswith("product:") for k in og)
        if is_product:
            self.put("title", og.get("og:title"), "opengraph")
        self.put("price", _float(og.get("product:price:amount") or og.get("og:price:amount")), "opengraph")
        self.put("currency", og.get("product:price:currency") or og.get("og:price:currency"), "opengraph")
        self.put("brand", og.get("product:brand"), "opengraph")
        self.put("availability", _availability(og.get("product:availability") or og.get("og:availability")), "opengraph")
        img = og.get("og:image")
        if img:
            self.put("images", img if isinstance(img, list) else [img], "opengraph")
        self.put("description", og.get("og:description") or self.s["meta"].get("description"), "meta")

    # ------------------------------------------------------------------ layer 3
    def from_embedded_json(self) -> None:
        for script in self.root.iter("script"):
            if (script.get("type") or "").lower() != "application/json":
                continue
            ident = f"{script.get('id', '')} {script.get('data-product-json', '')}".lower()
            if "product" not in ident:
                continue
            try:
                data = json.loads(script.text or "")
            except ValueError:
                continue
            if not isinstance(data, dict):
                continue
            data = data.get("product", data)
            self.put("title", first_text(data.get("title") or data.get("name")), "embedded-json")
            self.put("brand", first_text(data.get("vendor") or data.get("brand")), "embedded-json")
            variants = data.get("variants") or []
            if variants and isinstance(variants[0], dict):
                v = variants[0]
                price = v.get("price")
                if isinstance(price, int) and price >= 100 and "." not in str(price):
                    price = price / 100  # Shopify stores minor units
                self.put("price", _float(price), "embedded-json")
                self.put("sku", first_text(v.get("sku")), "embedded-json")
                if "available" in v:
                    self.put("availability", "InStock" if v["available"] else "OutOfStock", "embedded-json")

    # ------------------------------------------------------------------ layer 4
    def title_element(self) -> Optional[Any]:
        title = self.data.get("title")
        h1s = [h for h in self.root.iter("h1") if 3 <= len(norm(h.text_content())) <= 300]
        if title:
            for el in self.root.iter():
                if isinstance(el.tag, str) and el.tag not in ("title", "script", "meta") and \
                        norm(el.text_content()).casefold() == title.casefold():
                    return el
        if h1s:
            return h1s[0]
        for el in self.root.iter():
            if not isinstance(el.tag, str) or el.tag in ("title", "script", "style", "a"):
                continue
            if TITLE_HINT.search(_hint(el)) and not BAD_SECTION.search(_ancestors_hint(el)):
                text = norm(el.text_content())
                if 3 <= len(text) <= 250 and not PRICE_RE.fullmatch(text):
                    return el
        return None

    def heuristics(self) -> None:
        order = {el: i for i, el in enumerate(self.root.iter())}
        title_el = self.title_element()
        if title_el is not None:
            self.put("title", norm(title_el.text_content()), "dom")
        if not self.data.get("title"):
            self.put("title", detect_title(self.root, self.s), "dom-title")
        title_pos = order.get(title_el, 0) if title_el is not None else 0

        if self.data.get("price") is None:
            best = self._best_price(order, title_pos)
            if best:
                amount, currency = best
                self.put("price", amount, "dom")
                self.put("currency", currency, "dom")

        area = self._product_area(title_el)
        # itertext keeps element boundaries, so "TK-1200" and a following "Only 3 left" never fuse
        texts = [(el, " ".join(" ".join(el.itertext()).split())) for el in area.iter() if isinstance(el.tag, str)
                 and el.tag not in ("script", "style") and not BAD_SECTION.search(_hint(el))]
        short = [(el, t) for el, t in texts if 0 < len(t) <= 120]

        if not self.data.get("availability"):
            for el in area.iter():
                if isinstance(el.tag, str) and el.get("itemprop") == "availability":
                    self.put("availability", _availability(el.get("href") or el.get("content")), "dom")
            for el, t in short:
                if re.search(r"stock|avail|inventory", _hint(el), re.I) or len(t) <= 40:
                    m = STOCK_RE.search(t)
                    if m:
                        self.put("availability", _availability(m.group(1)), "dom")
                        break
        if not self.data.get("sku"):
            for el, t in short:
                m = SKU_RE.search(t)
                if m and not re.fullmatch(r"(?i)n/?a", m.group(1)):
                    self.put("sku", m.group(1).rstrip(".,"), "dom")
                    break
        if not self.data.get("brand"):
            self._brand(area, short)
        if self.data.get("rating") is None:
            for el in area.iter():
                if not isinstance(el.tag, str):
                    continue
                for attr in ("title", "aria-label", "data-rating"):
                    v = el.get(attr)
                    if v:
                        m = RATING_RE.search(v) or (re.fullmatch(r"\d(?:\.\d)?", v.strip()) if attr == "data-rating" else None)
                        if m:
                            val = next(g for g in (m.groups() if m.groups() else (m.group(0),)) if g)
                            self.put("rating", float(val.replace(",", ".")), "dom")
                            break
                if self.data.get("rating") is not None:
                    break
            if self.data.get("rating") is None:
                for el, t in short:
                    m = RATING_RE.search(t)
                    if m:
                        self.put("rating", float(next(g for g in m.groups() if g).replace(",", ".")), "dom")
                        break
        if self.data.get("review_count") is None:
            for el, t in short:
                m = REVIEWS_RE.search(t)
                if m:
                    digits = re.sub(r"[^\d]", "", m.group(1))
                    if digits:
                        self.put("review_count", int(digits), "dom")
                        break

    def _product_area(self, title_el: Optional[Any]) -> Any:
        """Smallest ancestor of the title that looks like the product block (or the body)."""
        if title_el is None:
            body = self.root.find(".//body")
            return body if body is not None else self.root
        node = title_el
        for anc in title_el.iterancestors():
            node = anc
            if PRODUCT_AREA.search(_hint(anc)) and len(norm(anc.text_content())) > 200:
                return anc
            if anc.tag in ("main", "body"):
                return anc
        return node

    def _best_price(self, order: dict[Any, int], title_pos: int) -> Optional[tuple[float, Optional[str]]]:
        candidates = []
        for el in self.root.iter():
            if not isinstance(el.tag, str) or el.tag in ("script", "style", "title", "option", "head", "meta"):
                continue
            text = _price_text(el)
            if not text or len(text) > 140:
                continue
            matches = list(PRICE_RE.finditer(text)) or list(PRICE_LABEL_RE.finditer(text))  # "Price: 7,799"
            for m in matches:
                literal = m.group(0) if m.re is PRICE_RE else m.group(1)
                # skip if a child element already contains this whole match (the child is the better anchor)
                if any(isinstance(c.tag, str) and literal in _price_text(c) for c in el):
                    continue
                amount, currency = parse_money(literal)
                if amount is None or amount <= 0:
                    continue
                score = 0.0
                own, anc = _hint(el), _ancestors_hint(el)
                if GOOD_PRICE.search(own):
                    score += 30
                elif GOOD_PRICE.search(anc):
                    score += 15
                if BAD_PRICE.search(own) or BAD_PRICE.search(anc[:200]):
                    score -= 40
                if el.tag in ("s", "del", "strike") or any(a.tag in ("s", "del", "strike") for a in el.iterancestors()):
                    score -= 60
                if BAD_LABEL.search(text[: m.start()]):
                    score -= 45
                if BAD_SECTION.search(anc):
                    score -= 50
                if _in_repeated_block(el):
                    score -= 40
                if PRODUCT_AREA.search(anc):
                    score += 10
                pos = order.get(el, 0)
                distance = pos - title_pos
                score += 25 if 0 <= distance <= 40 else 12 if 0 <= distance <= 150 else -10 if distance < 0 else 0
                candidates.append((score, -pos, amount, currency))
        if not candidates:
            return None
        score, _, amount, currency = max(candidates)
        return (amount, currency) if score > -20 else None

    def _brand(self, area: Any, short: list[tuple[Any, str]]) -> None:
        for el in area.iter():
            if isinstance(el.tag, str) and el.get("itemprop") == "brand":
                self.put("brand", norm(el.get("content") or el.text_content()), "dom")
                return
        for row in area.iter("tr"):
            cells = [norm(c.text_content()) for c in row if isinstance(c.tag, str) and c.tag in ("th", "td")]
            if len(cells) >= 2 and re.fullmatch(r"(?i)brand|manufacturer|make|brand name", cells[0]):
                self.put("brand", cells[1], "dom")
                return
        for dt in area.iter("dt"):
            dd = dt.getnext()
            if dd is not None and dd.tag == "dd" and re.fullmatch(r"(?i)brand|manufacturer", norm(dt.text_content()).rstrip(":")):
                self.put("brand", norm(dd.text_content()), "dom")
                return
        for el, t in short:
            m = BRAND_LABEL_RE.match(t)
            if m:
                self.put("brand", m.group(1).strip(), "dom")
                return
        for el, t in short:
            m = re.match(r"(?i)^visit the (.{2,50}?) store$", t)
            if m:
                self.put("brand", m.group(1), "dom")
                return
            if re.search(r"vendor|brand|maker", _hint(el), re.I) and 1 < len(t) <= 60 and not PRICE_RE.search(t):
                self.put("brand", re.sub(r"(?i)^(brand|by)\s*:?\s*", "", t), "dom")
                return

    def build(self) -> Optional[Product]:
        self.from_structured()
        self.from_meta()
        self.from_embedded_json()
        self.heuristics()
        if not self.data.get("title"):
            return None
        if self.data.get("currency"):
            self.data["currency"] = str(self.data["currency"]).upper()
        availability = self.data.get("availability") or "unknown"
        return Product(
            url=self.url,
            title=self.data["title"],
            price=self.data.get("price"),
            currency=self.data.get("currency"),
            brand=self.data.get("brand"),
            sku=self.data.get("sku"),
            rating=self.data.get("rating"),
            review_count=self.data.get("review_count"),
            availability=availability,
            in_stock=availability not in ("OutOfStock",),
            images=self.data.get("images") or [],
            description=self.data.get("description"),
            metadata=self.data["metadata"],
        )


def extract_product(html_or_root: Union[str, Any], url: str = "", structured: Optional[dict[str, Any]] = None) -> Optional[Product]:
    root = as_root(html_or_root)
    return ProductExtractor(root, url, structured or extract_structured(root, url)).build()
