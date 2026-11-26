"""Selector API parity (Parsel/Scrapling style)."""

import re

from omniscrape.parsers.selector import Selector

HTML = """<html><body>
<div class="grid">
  <div class="card featured" data-sku="A1"><h3>Lamp</h3><span class="price">$10.00</span><a href="/p/a1">View</a></div>
  <div class="card" data-sku="B2"><h3>Desk</h3><span class="price">$120.50</span><a href="/p/b2">View</a></div>
  <div class="card" data-sku="C3"><h3>Chair</h3><span class="price">$75.00</span><a href="/p/c3">View</a></div>
</div>
<p id="note">Prices include <b>VAT</b> today.</p>
<script type="application/json" id="data">{"count": 3}</script>
</body></html>"""


def test_pseudo_elements_get_getall_and_regex():
    sel = Selector(HTML, url="https://shop.example/list")
    assert sel.css("div.card h3::text").getall() == ["Lamp", "Desk", "Chair"]
    assert sel.css("div.card a::attr(href)").get() == "/p/a1"
    assert sel.css("span.price").re(r"\$([\d.]+)") == ["10.00", "120.50", "75.00"]
    assert sel.css("span.price::text").re_first(r"[\d.]+") == "10.00"
    assert sel.css(".missing::text").get(default="none") == "none"
    assert sel.css("h3::text, span.price::text").getall()[:2] == ["Lamp", "$10.00"]


def test_xpath_strings_chaining_and_compat():
    sel = Selector(HTML)
    assert sel.xpath("//div[@data-sku='B2']/h3/text()").get() == "Desk"
    assert sel.xpath("count(//div[contains(@class,'card')])").get() == "3.0"
    cards = sel.css("div.card")
    assert len(cards) == 3 and isinstance(cards, list)          # still a list (backward compatible)
    assert cards.css("h3::text").getall() == ["Lamp", "Desk", "Chair"]
    assert cards[0].get("data-sku") == "A1"                    # Element.get keeps attribute semantics
    assert cards[0].text.startswith("Lamp")
    assert sel.css("div[unclosed") == []                       # invalid selectors return an empty list


def test_navigation_find_and_similar():
    sel = Selector(HTML, url="https://shop.example/list")
    first = sel.css_first("div.card")
    assert first.next.css("h3::text").get() == "Desk"
    assert first.next.previous == first
    assert len(first.siblings) == 2
    assert sel.find("div", class_="card", data_sku="C3").css("h3::text").get() == "Chair"
    assert [e.css("h3::text").get() for e in sel.find_all("div", class_="card", text=re.compile("Desk|Chair"))] == ["Desk", "Chair"]
    similar = first.find_similar()
    assert {e.get("data-sku") for e in similar} == {"B2", "C3"}
    assert sel.css_first("#note").own_text == "Prices include today."
    assert sel.css_first("#data").json() == {"count": 3}
    assert first.css_first("a").urljoin("/p/a1") == "https://shop.example/p/a1"


def test_selector_generation_round_trips():
    sel = Selector(HTML)
    target = sel.css("div.card")[2].css_first("span.price")
    css = target.generate_css_selector()
    assert sel.css(css)[0] == target
    assert sel.xpath(target.generate_xpath())[0] == target
