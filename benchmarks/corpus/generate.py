"""Seeded synthetic corpus generator with exact ground truth.

Pages are built from two disjoint English vocabularies: CONTENT words (main content) and
BOILERPLATE words (navigation, footers, sidebars, related links, comments, ads). This makes
main-content quality measurable: recall over the known main text, and leakage as the share of
boilerplate-vocabulary tokens in the output.

Splits:
  dev      templates: bem, utility, hashed            (tune extractors on these only)
  holdout  templates: legacy_table, html5_microdata, nextjs  (+ toscrape snapshots, handwritten)

Usage: python -m benchmarks.corpus.generate [--seed 1337]
"""

import argparse
import html as htmllib
import json
import random
from dataclasses import dataclass, field
from typing import Any, Callable

from benchmarks.common import CORPUS_DIR

CONTENT_WORDS = """
river mountain engine signal harvest copper lantern meadow orbit canvas thunder garden
pattern quarry silver timber voyage marble pepper falcon glacier compass ember velvet
harbor prism saddle tunnel violet whistle anchor beacon cedar dune fabric granite hollow
island jasmine kettle ledger mosaic nectar oyster pillar quartz ripple summit tundra
umber valley willow yarrow zephyr almond basil cobalt delta ferry gravel hazel indigo
juniper kiln lagoon maple nickel olive pebble quill raven sable thistle walnut alpine
bramble cinder drizzle estuary fennel geyser heron ivory jetty kelp lichen mango nutmeg
orchid paprika radish saffron tangerine vapor wren acorn birch canyon dahlia fjord
grove husk iris jungle knoll lotus moss nebula onyx poplar reef sequoia tide upland
verdant wheat amber bison coral dusk elm flint garnet heath inlet jade krill lark
mesa nimbus opal plume quince rust spruce topaz urchin vine wisp yew zinc aurora
brisk crisp deft eager fierce gentle humble keen lively mellow nimble placid quaint
robust serene sturdy tender vivid witty zealous ancient bold calm dense faint grand
hidden lofty mighty noble polished rapid silent swift tranquil vast warm golden
analyze balance calibrate distill evaluate forge gather illuminate kindle measure
navigate observe polish refine sculpt temper unveil weave cultivate bloom drift
""".split()

BOILERPLATE_WORDS = """
account login signup subscribe newsletter privacy cookies careers shipping returns
support contact sitemap terms conditions sponsored advertisement promoted trending
popular recommended related share tweet follow facebook instagram youtube linkedin
copyright reserved affiliate partners investors press help faq wishlist checkout
basket coupon discount voucher deals clearance outlet membership rewards loyalty
notifications settings preferences dashboard logout register download app store
accessibility feedback survey chat agent livechat hotline helpdesk ticket refund
warranty tracking delivery dispatch courier invoice billing payment paypal visa
mastercard unsubscribe inbox digest weekly daily alerts breaking headlines topics
categories archives tags authors editorial masthead ombudsman licensing syndication
comments reply upvote downvote report moderator guidelines community forum thread
""".split()

STOPWORDS = "the a an of and to in with for on at by from as is was are this that its".split()

BRANDS = ["Nordvik", "Altara", "Kestrel", "Brightline", "Oakhaven", "Veloria", "Tessaro", "Quorra"]
NOUNS = ["Office Chair", "Desk Lamp", "Backpack", "Headphones", "Kettle", "Blender", "Monitor Arm",
         "Water Bottle", "Keyboard", "Rice Cooker", "Running Shoes", "Tent", "Cookware Set", "Air Purifier"]
ADJECTIVES = ["Ergonomic", "Compact", "Wireless", "Insulated", "Ultralight", "Premium", "Classic", "Smart"]
AUTHORS = ["Amara Okafor", "Lucas Brennan", "Priya Raman", "Mateo Silva", "Hana Kobayashi", "Elif Demir",
           "Noah Lindqvist", "Zara Haddad"]
CURRENCIES = [("USD", "$", "en"), ("EUR", "€", "eu"), ("GBP", "£", "en"), ("INR", "₹", "in")]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December"]
STRUCTURED_MODES = ["jsonld", "microdata", "og_only", "none"]

assert not set(CONTENT_WORDS) & set(BOILERPLATE_WORDS), "vocabularies must be disjoint"


def esc(s: Any) -> str:
    return htmllib.escape(str(s), quote=True)


@dataclass
class Gen:
    rng: random.Random

    def sentence(self, vocab: list[str], n: tuple[int, int] = (8, 16)) -> str:
        words = []
        for i in range(self.rng.randint(*n)):
            words.append(self.rng.choice(STOPWORDS) if i % 3 == 1 else self.rng.choice(vocab))
        s = " ".join(words)
        return s[0].upper() + s[1:] + "."

    def paragraph(self, vocab: list[str], sentences: tuple[int, int] = (3, 6)) -> str:
        return " ".join(self.sentence(vocab) for _ in range(self.rng.randint(*sentences)))

    def phrase(self, vocab: list[str], n: tuple[int, int] = (2, 4)) -> str:
        return " ".join(self.rng.choice(vocab) for _ in range(self.rng.randint(*n))).title()

    def b_phrase(self, n: tuple[int, int] = (1, 3)) -> str:
        return self.phrase(BOILERPLATE_WORDS, n)

    def hexid(self, n: int = 6) -> str:
        return "".join(self.rng.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(n))


# ----------------------------------------------------------------------------- data models
def format_price(amount: float, cur: tuple[str, str, str]) -> str:
    code, sym, style = cur
    if style == "eu":
        s = f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{s} {sym}"
    if style == "in":
        whole = int(round(amount))
        s = str(whole)
        if len(s) > 3:
            head, tail = s[:-3], s[-3:]
            groups = []
            while len(head) > 2:
                groups.insert(0, head[-2:])
                head = head[:-2]
            if head:
                groups.insert(0, head)
            s = ",".join(groups) + "," + tail
        return f"{sym}{s}"
    return f"{sym}{amount:,.2f}"


def make_product(g: Gen, idx: int) -> dict[str, Any]:
    cur = CURRENCIES[idx % len(CURRENCIES)]
    amount = round(g.rng.uniform(9, 2500), 2)
    if cur[0] == "INR":
        amount = float(int(amount * 83))
    brand = g.rng.choice(BRANDS)
    title = f"{brand} {g.rng.choice(ADJECTIVES)} {g.rng.choice(NOUNS)} {g.rng.choice('XKMRT')}{g.rng.randint(100, 999)}"
    specs = {g.phrase(CONTENT_WORDS, (1, 2)): g.phrase(CONTENT_WORDS, (1, 3)) for _ in range(g.rng.randint(4, 9))}
    in_stock = g.rng.random() > 0.2
    return {
        "title": title,
        "price": amount,
        "price_text": format_price(amount, cur),
        "currency": cur[0],
        "brand": brand,
        "sku": f"{brand[:3].upper()}-{g.rng.randint(10000, 99999)}",
        "rating": round(g.rng.uniform(2.5, 5.0), 1),
        "review_count": g.rng.randint(0, 4000),
        "availability": "InStock" if in_stock else "OutOfStock",
        "images": [f"/img/{g.hexid(10)}.jpg" for _ in range(g.rng.randint(1, 4))],
        "description": " ".join(g.paragraph(CONTENT_WORDS) for _ in range(g.rng.randint(1, 3))),
        "specs": specs,
    }


def make_article(g: Gen) -> dict[str, Any]:
    year, month, day = g.rng.randint(2019, 2026), g.rng.randint(1, 12), g.rng.randint(1, 28)
    blocks: list[tuple[str, Any]] = []
    for i in range(g.rng.randint(6, 18)):
        if i and i % 4 == 0:
            blocks.append(("h2", g.phrase(CONTENT_WORDS, (2, 5))))
        blocks.append(("p", g.paragraph(CONTENT_WORDS)))
        if i == 2:
            blocks.append(("ul", [g.sentence(CONTENT_WORDS, (4, 8)) for _ in range(g.rng.randint(3, 6))]))
        if i == 5 and g.rng.random() < 0.5:
            rows = [[g.phrase(CONTENT_WORDS, (1, 2)) for _ in range(3)] for _ in range(g.rng.randint(2, 5))]
            blocks.append(("table", rows))
    return {
        "title": g.phrase(CONTENT_WORDS, (4, 9)),
        "author": g.rng.choice(AUTHORS),
        "date_iso": f"{year:04d}-{month:02d}-{day:02d}",
        "date_human": g.rng.choice([
            f"{MONTHS[month - 1]} {day}, {year}",
            f"{day} {MONTHS[month - 1][:3]} {year}",
            f"{year:04d}-{month:02d}-{day:02d}",
        ]),
        "blocks": blocks,
    }


def article_main_text(a: dict[str, Any]) -> str:
    parts = [a["title"]]
    for kind, val in a["blocks"]:
        if kind in ("h2", "p"):
            parts.append(val)
        elif kind == "ul":
            parts.extend(val)
        elif kind == "table":
            parts.extend(" ".join(r) for r in val)
    return "\n".join(parts)


# ----------------------------------------------------------------------------- templates
@dataclass
class Template:
    name: str
    split: str
    semantic: bool
    cls: dict[str, str] = field(default_factory=dict)  # role -> class attribute
    listing_selectors: dict[str, str] = field(default_factory=dict)

    def c(self, role: str) -> str:
        v = self.cls.get(role, "")
        return f' class="{v}"' if v else ""

    def tag(self, role: str, default: str = "div") -> str:
        semantic = {"header": "header", "nav": "nav", "main": "main", "footer": "footer",
                    "aside": "aside", "article": "article"}
        return semantic.get(role, default) if self.semantic else default


def bem() -> Template:
    roles = {k: f"site-{k}" for k in ["header", "nav", "main", "footer", "aside", "article", "cookie"]}
    roles.update({
        "title": "product__title", "price": "product__price", "brand": "product__brand",
        "sku": "product__sku", "rating": "product__rating", "stock": "product__stock",
        "desc": "product__description", "specs": "product__specs", "gallery": "product__gallery",
        "grid": "listing__grid", "card": "listing__card", "card_title": "listing__card-title",
        "card_price": "listing__card-price", "card_link": "listing__card-link",
        "byline": "article__byline", "date": "article__date", "body": "article__body",
        "headline": "article__headline", "related": "related-items", "buy": "product__buy",
    })
    return Template("bem", "dev", True, roles, {
        "cards": "div.listing__card", "card_titles": "div.listing__card h3.listing__card-title",
        "card_prices": "div.listing__card span.listing__card-price", "card_links": "a.listing__card-link",
    })


def utility() -> Template:
    roles = {
        "header": "flex items-center justify-between px-6 py-4 bg-white shadow", "nav": "hidden md:flex gap-4",
        "main": "container mx-auto px-4", "footer": "mt-16 bg-gray-900 text-gray-300 py-10",
        "aside": "w-full lg:w-1/3 space-y-4", "article": "prose lg:prose-xl", "cookie": "fixed bottom-0 inset-x-0 p-4",
        "title": "text-3xl font-bold tracking-tight", "price": "text-2xl font-semibold text-emerald-600",
        "brand": "text-sm uppercase text-gray-500", "sku": "text-xs text-gray-400", "rating": "flex items-center gap-1",
        "stock": "text-sm font-medium", "desc": "mt-4 text-gray-700 leading-7", "specs": "mt-6 divide-y",
        "gallery": "grid grid-cols-4 gap-2", "grid": "grid grid-cols-2 md:grid-cols-4 gap-6",
        "card": "rounded-xl border p-4 hover:shadow-lg", "card_title": "mt-2 text-base font-medium",
        "card_price": "mt-1 font-semibold", "card_link": "block", "byline": "text-sm text-gray-600",
        "date": "text-sm text-gray-500", "body": "mt-8 space-y-6", "headline": "text-4xl font-extrabold",
        "related": "mt-12 grid grid-cols-3 gap-4", "buy": "mt-6 w-full rounded-lg bg-black px-4 py-3 text-white",
    }
    return Template("utility", "dev", False, roles, {
        "cards": "div.rounded-xl.border", "card_titles": "div.rounded-xl.border h3",
        "card_prices": "div.rounded-xl.border span.font-semibold", "card_links": "div.rounded-xl.border a.block",
    })


def hashed(rng: random.Random) -> Template:
    def h() -> str:
        return f"sc-{''.join(rng.choice('abcdefghijklmnop') for _ in range(6))} css-{rng.randint(1000, 9999)}"
    roles = {k: h() for k in ["header", "nav", "main", "footer", "aside", "article", "cookie", "title", "price",
                              "brand", "sku", "rating", "stock", "desc", "specs", "gallery", "grid", "card",
                              "card_title", "card_price", "card_link", "byline", "date", "body", "headline",
                              "related", "buy"]}
    first = {k: v.split()[0] for k, v in roles.items()}
    return Template("hashed", "dev", True, roles, {
        "cards": f"div.{first['card']}", "card_titles": f"div.{first['card']} h3",
        "card_prices": f"div.{first['card']} span.{first['card_price']}", "card_links": f"a.{first['card_link']}",
    })


def legacy_table() -> Template:
    roles = {"title": "ptitle", "price": "pprice", "brand": "pbrand", "sku": "psku", "rating": "prate",
             "stock": "pstock", "desc": "pdesc", "specs": "pspecs", "card": "item", "card_title": "itemname",
             "card_price": "itemprice", "card_link": "itemlink", "byline": "by", "date": "dt", "body": "content",
             "headline": "headline", "related": "related", "buy": "buybtn", "grid": "items"}
    return Template("legacy_table", "holdout", False, roles, {
        "cards": "td.item", "card_titles": "td.item font.itemname", "card_prices": "td.item b.itemprice",
        "card_links": "a.itemlink",
    })


def html5_microdata() -> Template:
    roles = {"title": "name", "price": "price-tag", "brand": "maker", "sku": "code", "rating": "stars",
             "stock": "stock", "desc": "about", "specs": "facts", "grid": "catalog", "card": "tile",
             "card_title": "tile-name", "card_price": "tile-price", "card_link": "tile-link", "byline": "author",
             "date": "published", "body": "story", "headline": "story-title", "related": "more", "buy": "add"}
    return Template("html5_microdata", "holdout", True, roles, {
        "cards": "li.tile", "card_titles": "li.tile h2.tile-name", "card_prices": "li.tile data.tile-price",
        "card_links": "a.tile-link",
    })


def nextjs(rng: random.Random) -> Template:
    def h(prefix: str) -> str:
        return f"{prefix}_{''.join(rng.choice('ABCDEFGHabcdefgh0123456789') for _ in range(5))}"
    roles = {k: h(k.title().replace("_", "")) for k in ["header", "nav", "main", "footer", "aside", "article",
                                                         "title", "price", "brand", "sku", "rating", "stock",
                                                         "desc", "specs", "gallery", "grid", "card", "card_title",
                                                         "card_price", "card_link", "byline", "date", "body",
                                                         "headline", "related", "buy"]}
    return Template("nextjs", "holdout", True, roles, {
        "cards": f"article.{roles['card']}", "card_titles": f"article.{roles['card']} p.{roles['card_title']}",
        "card_prices": f"article.{roles['card']} div.{roles['card_price']}", "card_links": f"a.{roles['card_link']}",
    })


# ----------------------------------------------------------------------------- boilerplate
def nav_html(t: Template, g: Gen) -> str:
    links = "".join(f'<li><a href="/{g.hexid(5)}">{esc(g.b_phrase())}</a></li>' for _ in range(g.rng.randint(8, 14)))
    if t.name == "legacy_table":
        return f'<table width="100%" bgcolor="#003366"><tr><td><font color="white">{links.replace("<li>", " | ").replace("</li>", "")}</font></td></tr></table>'
    return (f'<{t.tag("header")}{t.c("header")}><a href="/" class="logo">{esc(g.b_phrase((1, 1)))}</a>'
            f'<{t.tag("nav")}{t.c("nav")}><ul>{links}</ul></{t.tag("nav")}>'
            f'<form action="/search"><input name="q" placeholder="{esc(g.b_phrase())}"></form></{t.tag("header")}>')


def cookie_html(t: Template, g: Gen) -> str:
    return f'<div{t.c("cookie")} id="cookie-consent"><p>{esc(g.sentence(BOILERPLATE_WORDS))}</p><button>{esc(g.b_phrase((1, 2)))}</button></div>'


def footer_html(t: Template, g: Gen) -> str:
    cols = ""
    for _ in range(4):
        items = "".join(f'<li><a href="/{g.hexid(4)}">{esc(g.b_phrase())}</a></li>' for _ in range(g.rng.randint(5, 9)))
        cols += f"<div><h4>{esc(g.b_phrase((1, 2)))}</h4><ul>{items}</ul></div>"
    body = f"{cols}<p>{esc(g.sentence(BOILERPLATE_WORDS))}</p>"
    if t.name == "legacy_table":
        return f'<table width="100%"><tr><td align="center"><font size="1">{body}</font></td></tr></table>'
    return f'<{t.tag("footer")}{t.c("footer")}>{body}</{t.tag("footer")}>'


def sidebar_html(t: Template, g: Gen) -> str:
    items = "".join(f'<li><a href="/{g.hexid(6)}">{esc(g.phrase(BOILERPLATE_WORDS, (3, 7)))}</a></li>' for _ in range(8))
    ad = f'<div class="ad-slot"><span>{esc(g.b_phrase((1, 1)))}</span><p>{esc(g.sentence(BOILERPLATE_WORDS))}</p></div>'
    news = f'<div class="newsletter"><h3>{esc(g.b_phrase())}</h3><p>{esc(g.sentence(BOILERPLATE_WORDS))}</p><input type="email"><button>{esc(g.b_phrase((1, 1)))}</button></div>'
    return f'<{t.tag("aside")}{t.c("aside")}><h3>{esc(g.b_phrase())}</h3><ol>{items}</ol>{ad}{news}</{t.tag("aside")}>'


def comments_html(g: Gen) -> str:
    out = "".join(
        f'<div class="comment"><b>{esc(g.b_phrase((1, 2)))}</b><p>{esc(g.paragraph(BOILERPLATE_WORDS, (1, 3)))}</p>'
        f'<a href="#">{esc(g.b_phrase((1, 1)))}</a></div>'
        for _ in range(g.rng.randint(2, 7))
    )
    return f'<section class="comments"><h3>{esc(g.b_phrase())}</h3>{out}</section>'


def related_products_html(t: Template, g: Gen, idx: int) -> str:
    cards = ""
    for j in range(g.rng.randint(3, 6)):
        p = make_product(g, idx + j + 1)
        cards += f'<div class="mini-card"><a href="/p/{g.hexid(6)}">{esc(p["title"])}</a><span class="mini-price">{esc(p["price_text"])}</span></div>'
    return f'<section{t.c("related")}><h3>{esc(g.b_phrase())}</h3>{cards}</section>'


def page(t: Template, g: Gen, title: str, head_extra: str, body: str, html_attrs: str = "") -> str:
    return (f'<!DOCTYPE html><html lang="en"{html_attrs}><head><meta charset="utf-8"><title>{esc(title)}</title>'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">{head_extra}'
            f'<link rel="stylesheet" href="/static/{g.hexid(8)}.css"><script src="/static/{g.hexid(8)}.js" defer></script>'
            f"</head><body>{body}</body></html>")


# ----------------------------------------------------------------------------- page builders
def product_page(t: Template, g: Gen, idx: int, url: str) -> tuple[str, dict[str, Any]]:
    p = make_product(g, idx)
    mode = "microdata" if t.name == "html5_microdata" else STRUCTURED_MODES[idx % len(STRUCTURED_MODES)]
    md = mode == "microdata"

    def ip(name: str) -> str:
        return f' itemprop="{name}"' if md else ""

    head = ""
    if mode in ("jsonld", "og_only", "microdata"):
        head += (f'<meta property="og:title" content="{esc(p["title"])}"><meta property="og:type" content="product">'
                 f'<meta property="og:image" content="{esc(p["images"][0])}">')
    if mode == "og_only":
        head += (f'<meta property="product:price:amount" content="{p["price"]:.2f}">'
                 f'<meta property="product:price:currency" content="{p["currency"]}">'
                 f'<meta property="product:brand" content="{esc(p["brand"])}">')
    if mode == "jsonld":
        ld = {"@context": "https://schema.org", "@type": "Product", "name": p["title"], "sku": p["sku"],
              "brand": {"@type": "Brand", "name": p["brand"]}, "image": p["images"], "description": p["description"][:200],
              "aggregateRating": {"@type": "AggregateRating", "ratingValue": p["rating"], "reviewCount": p["review_count"]},
              "offers": {"@type": "Offer", "price": f'{p["price"]:.2f}', "priceCurrency": p["currency"],
                         "availability": f'https://schema.org/{p["availability"]}'}}
        head += f'<script type="application/ld+json">{json.dumps(ld)}</script>'

    specs_rows = "".join(f"<tr><th>{esc(k)}</th><td>{esc(v)}</td></tr>" for k, v in p["specs"].items())
    gallery = "".join(f'<img src="{esc(src)}" alt="{esc(p["title"])}"{ip("image")}>' for src in p["images"])
    stock_text = "In stock" if p["availability"] == "InStock" else "Out of stock"
    offer_open = '<div itemprop="offers" itemscope itemtype="https://schema.org/Offer">' if md else "<div>"
    price_inner = esc(p["price_text"])
    md_price = (f'<meta itemprop="price" content="{p["price"]:.2f}"><meta itemprop="priceCurrency" content="{p["currency"]}">'
                f'<link itemprop="availability" href="https://schema.org/{p["availability"]}">') if md else ""
    breadcrumb = (f'<div class="breadcrumbs"><a href="/">{esc(g.b_phrase((1, 1)))}</a> &rsaquo; '
                  f'<a href="/c/{g.hexid(4)}">{esc(g.b_phrase((1, 2)))}</a></div>')

    if t.name == "legacy_table":
        core = (f'<table width="960" cellpadding="4"><tr><td valign="top" width="40%">{gallery}</td><td valign="top">'
                f'<font size="5" class="{t.cls["title"]}"><b>{esc(p["title"])}</b></font><br>'
                f'<font class="{t.cls["brand"]}">by {esc(p["brand"])}</font><br>'
                f'<font size="4" color="#B12704" class="{t.cls["price"]}">{price_inner}</font><br>'
                f'<small class="{t.cls["sku"]}">Item code: {esc(p["sku"])}</small><br>'
                f'<span class="{t.cls["rating"]}">{p["rating"]} out of 5 ({p["review_count"]} ratings)</span><br>'
                f'<b class="{t.cls["stock"]}">{stock_text}</b><br><input type="submit" class="{t.cls["buy"]}" value="Add">'
                f'<p class="{t.cls["desc"]}">{esc(p["description"])}</p>'
                f'<table class="{t.cls["specs"]}" border="1">{specs_rows}</table></td></tr></table>')
    else:
        title_tag = "h1"
        scope = ' itemscope itemtype="https://schema.org/Product"' if md else ""
        core = (f'{breadcrumb}<{t.tag("main")}{t.c("main")}>'
                f'<div{scope} class="product">'
                f'<div{t.c("gallery")}>{gallery}</div><div class="details">'
                f'<{title_tag}{t.c("title")}{ip("name")}>{esc(p["title"])}</{title_tag}>'
                f'<div{t.c("brand")}>Brand: <span{ip("brand")}>{esc(p["brand"])}</span></div>'
                f'{offer_open}<span{t.c("price")}>{price_inner}</span>{md_price}</div>'
                f'<div{t.c("sku")}>SKU: <span{ip("sku")}>{esc(p["sku"])}</span></div>'
                f'<div{t.c("rating")}><span>{p["rating"]}</span> / 5 · <span>{p["review_count"]} reviews</span></div>'
                f'<div{t.c("stock")}>{stock_text}</div>'
                f'<button{t.c("buy")} data-action="add-to-cart">Add to cart</button>'
                f'<div{t.c("desc")}{ip("description")}><p>{esc(p["description"])}</p></div>'
                f'<table{t.c("specs")}><tbody>{specs_rows}</tbody></table></div></div>'
                f'{related_products_html(t, g, idx)}</{t.tag("main")}>')
    body = nav_html(t, g) + core + footer_html(t, g) + cookie_html(t, g)
    if t.name == "nextjs":
        data = json.dumps({"props": {"pageProps": {"sku": p["sku"], "slug": g.hexid(8)}}, "page": "/p/[slug]"})
        body = f'<div id="__next">{body}</div><script id="__NEXT_DATA__" type="application/json">{data}</script>'
    html = page(t, g, f'{p["title"]} | {g.b_phrase((1, 1))}', head, body)
    truth = {
        "type": "product", "url": url, "template": t.name, "structured_mode": mode,
        "fields": {k: p[k] for k in ["title", "price", "currency", "brand", "sku", "rating", "review_count", "availability"]},
        "main_text": "\n".join([p["title"], p["description"], *[f"{k} {v}" for k, v in p["specs"].items()]]),
        "targets": {
            "title": {"role": "title", "text": p["title"]},
            "price": {"role": "price", "text": p["price_text"]},
            "sku": {"role": "sku", "text": f'SKU: {p["sku"]}' if t.name != "legacy_table" else f'Item code: {p["sku"]}'},
            "stock": {"role": "stock", "text": stock_text},
        },
        "classes": t.cls,
    }
    return html, truth


def article_page(t: Template, g: Gen, idx: int, url: str) -> tuple[str, dict[str, Any]]:
    a = make_article(g)
    mode = STRUCTURED_MODES[idx % len(STRUCTURED_MODES)]
    head = ""
    if mode in ("jsonld", "og_only", "microdata"):
        head += (f'<meta property="og:title" content="{esc(a["title"])}"><meta property="og:type" content="article">'
                 f'<meta property="article:published_time" content="{a["date_iso"]}T08:00:00Z">'
                 f'<meta name="author" content="{esc(a["author"])}">')
    if mode == "jsonld":
        ld = {"@context": "https://schema.org", "@type": ["NewsArticle", "Article"] if idx % 2 else "BlogPosting",
              "headline": a["title"], "datePublished": f'{a["date_iso"]}T08:00:00Z',
              "author": [{"@type": "Person", "name": a["author"]}]}
        head += f'<script type="application/ld+json">{json.dumps(ld)}</script>'
    md = mode == "microdata"

    body_parts = []
    for kind, val in a["blocks"]:
        if kind == "h2":
            body_parts.append(f"<h2>{esc(val)}</h2>")
        elif kind == "p":
            body_parts.append(f"<p>{esc(val)}</p>")
        elif kind == "ul":
            body_parts.append("<ul>" + "".join(f"<li>{esc(x)}</li>" for x in val) + "</ul>")
        elif kind == "table":
            body_parts.append("<table>" + "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>" for r in val) + "</table>")
        if kind == "p" and g.rng.random() < 0.15:
            body_parts.append(f'<div class="inline-promo"><a href="/{g.hexid(5)}">{esc(g.phrase(BOILERPLATE_WORDS, (3, 6)))}</a></div>')
    body_html = "".join(body_parts)
    share = "".join(f'<a href="#" class="share">{esc(w)}</a>' for w in ["Share", "Tweet", "Facebook"])
    md_scope = ' itemscope itemtype="https://schema.org/Article"' if md else ""
    ip_head = ' itemprop="headline"' if md else ""
    ip_author = ' itemprop="author"' if md else ""
    ip_date = f' itemprop="datePublished" datetime="{a["date_iso"]}"' if md else f' datetime="{a["date_iso"]}"'

    if t.name == "legacy_table":
        core = (f'<table width="100%"><tr><td width="70%" valign="top" class="{t.cls["body"]}">'
                f'<font size="6" class="{t.cls["headline"]}"><b>{esc(a["title"])}</b></font><br>'
                f'<font size="2"><span class="{t.cls["byline"]}">By {esc(a["author"])}</span> - '
                f'<span class="{t.cls["date"]}">{esc(a["date_human"])}</span></font>{body_html}{comments_html(g)}</td>'
                f'<td valign="top">{sidebar_html(t, g)}</td></tr></table>')
    else:
        core = (f'<div class="layout"><{t.tag("main")}{t.c("main")}><{t.tag("article")}{t.c("article")}{md_scope}>'
                f'<h1{t.c("headline")}{ip_head}>{esc(a["title"])}</h1>'
                f'<div class="meta"><span{t.c("byline")}>By <a href="/author/{g.hexid(4)}"{ip_author}>{esc(a["author"])}</a></span> · '
                f'<time{t.c("date")}{ip_date}>{esc(a["date_human"])}</time></div>'
                f'<div class="share-bar">{share}</div><div{t.c("body")}>{body_html}</div></{t.tag("article")}>'
                f'{comments_html(g)}</{t.tag("main")}>{sidebar_html(t, g)}</div>')
    body = nav_html(t, g) + core + footer_html(t, g) + cookie_html(t, g)
    if t.name == "nextjs":
        body = f'<div id="__next">{body}</div><script id="__NEXT_DATA__" type="application/json">{{"page":"/blog/[slug]"}}</script>'
    html = page(t, g, a["title"], head, body)
    truth = {
        "type": "article", "url": url, "template": t.name, "structured_mode": mode,
        "fields": {"title": a["title"], "author": a["author"], "published_date": a["date_iso"]},
        "main_text": article_main_text(a),
    }
    return html, truth


def listing_page(t: Template, g: Gen, idx: int, url: str, n_cards: int) -> tuple[str, dict[str, Any]]:
    cards = []
    for j in range(n_cards):
        p = make_product(g, idx * 1000 + j)
        href = f"/p/{g.hexid(8)}"
        if t.name == "legacy_table":
            cards.append(f'<td class="{t.cls["card"]}"><a class="{t.cls["card_link"]}" href="{href}"><img src="{p["images"][0]}"></a><br>'
                         f'<font class="{t.cls["card_title"]}">{esc(p["title"])}</font><br><b class="{t.cls["card_price"]}">{esc(p["price_text"])}</b></td>')
        elif t.name == "html5_microdata":
            cards.append(f'<li class="tile"><a class="tile-link" href="{href}"><img src="{p["images"][0]}" alt=""></a>'
                         f'<h2 class="tile-name">{esc(p["title"])}</h2><data class="tile-price" value="{p["price"]}">{esc(p["price_text"])}</data></li>')
        elif t.name == "nextjs":
            cards.append(f'<article class="{t.cls["card"]}"><a class="{t.cls["card_link"]}" href="{href}"><img src="{p["images"][0]}"></a>'
                         f'<p class="{t.cls["card_title"]}">{esc(p["title"])}</p><div class="{t.cls["card_price"]}">{esc(p["price_text"])}</div></article>')
        else:
            cards.append(f'<div{t.c("card")}><a{t.c("card_link")} href="{href}"><img src="{p["images"][0]}" alt=""></a>'
                         f'<h3{t.c("card_title")}>{esc(p["title"])}</h3><span{t.c("card_price")}>{esc(p["price_text"])}</span>'
                         f'<button data-sku="{p["sku"]}">Add</button></div>')
    if t.name == "legacy_table":
        rows = "".join("<tr>" + "".join(cards[i:i + 4]) + "</tr>" for i in range(0, len(cards), 4))
        grid = f'<table class="{t.cls["grid"]}" width="100%">{rows}</table>'
    elif t.name == "html5_microdata":
        grid = f'<ul class="catalog">{"".join(cards)}</ul>'
    else:
        grid = f'<div{t.c("grid")}>{"".join(cards)}</div>'
    pager = "".join(f'<a href="?page={k}">{k}</a>' for k in range(1, 8))
    body = nav_html(t, g) + f'<{t.tag("main")}{t.c("main")}><h1>{esc(g.b_phrase())}</h1>{grid}<div class="pager">{pager}</div></{t.tag("main")}>' + footer_html(t, g)
    html = page(t, g, g.b_phrase(), "", body)
    truth = {"type": "listing", "url": url, "template": t.name, "n_cards": n_cards,
             "selectors": t.listing_selectors,
             "expected_counts": {"cards": n_cards, "card_titles": n_cards, "card_prices": n_cards, "card_links": n_cards}}
    return html, truth


# ----------------------------------------------------------------------------- main
PLAN = {"dev": {"product": 8, "article": 8, "listing": [24, 96, 240]},
        "holdout": {"product": 6, "article": 6, "listing": [48, 800]}}


def generate(seed: int = 1337) -> dict[str, int]:
    rng = random.Random(seed)
    g = Gen(rng)
    templates: dict[str, list[Template]] = {
        "dev": [bem(), utility(), hashed(random.Random(seed + 1))],
        "holdout": [legacy_table(), html5_microdata(), nextjs(random.Random(seed + 2))],
    }
    counts: dict[str, int] = {}
    for split, temps in templates.items():
        out = CORPUS_DIR / split
        if out.exists():  # regenerate synthetic pages; keep snapshots (snap_*) and handwritten (hand_*)
            for p in out.iterdir():
                if not p.name.startswith(("snap_", "hand_")):
                    p.unlink()
        out.mkdir(parents=True, exist_ok=True)
        builders: list[tuple[str, Callable[..., tuple[str, dict[str, Any]]], Any]] = []
        for t in temps:
            for i in range(PLAN[split]["product"]):
                builders.append((f"{t.name}_product_{i:02d}", product_page, (t, i)))
            for i in range(PLAN[split]["article"]):
                builders.append((f"{t.name}_article_{i:02d}", article_page, (t, i)))
            for i, n in enumerate(PLAN[split]["listing"]):
                builders.append((f"{t.name}_listing_{i:02d}", listing_page, (t, i, n)))
        for doc_id, fn, args in builders:
            url = f"https://{args[0].name.replace('_', '-')}.bench.local/{doc_id}"
            if fn is listing_page:
                html, truth = fn(args[0], g, args[1], url, args[2])
            else:
                html, truth = fn(args[0], g, args[1], url)
            (out / f"{doc_id}.html").write_text(html, encoding="utf-8")
            (out / f"{doc_id}.json").write_text(json.dumps(truth, indent=1), encoding="utf-8")
        counts[split] = len(builders)
    (CORPUS_DIR / "vocab.json").write_text(json.dumps({"boilerplate": BOILERPLATE_WORDS, "content": CONTENT_WORDS}), encoding="utf-8")
    return counts


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=1337)
    args = ap.parse_args()
    counts = generate(args.seed)
    print(f"Generated corpus in {CORPUS_DIR}: {counts}")


if __name__ == "__main__":
    main()

