"""Unit tests for 12-factor fingerprinting and adaptive self-healing."""

import tempfile
from omniscrape.parsers.adaptive import AdaptiveEngine, NodeFingerprint
from omniscrape.parsers.selector import Selector

# Before redesign
HTML_V1 = """
<div id="store-app">
    <div class="product-card">
        <h2 class="title">Gaming Laptop 16GB</h2>
        <div class="cost-container">
            <span class="old-price-class" data-qa="product_price">₹85,000</span>
        </div>
    </div>
</div>
"""

# After redesign: class name changed from .old-price-class to .x92js-dynamic-hash
HTML_V2 = """
<div id="store-app">
    <div class="product-card">
        <h2 class="title">Gaming Laptop 16GB</h2>
        <div class="cost-container">
            <span class="x92js-dynamic-hash" data-qa="product_price">₹85,000</span>
        </div>
    </div>
</div>
"""


def test_adaptive_fingerprinting_and_relocation():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    engine = AdaptiveEngine(db_path=db_path)

    # 1. First run on V1: selector exists and fingerprint is saved
    sel_v1 = Selector(HTML_V1)
    original_el = sel_v1.css(".old-price-class")[0]
    fp = NodeFingerprint.from_element(original_el)
    engine.save_fingerprint("store.com", "price", fp)

    # 2. Next run on V2: original selector returns empty
    sel_v2 = Selector(HTML_V2)
    broken_query = sel_v2.css(".old-price-class")
    assert len(broken_query) == 0, "Original class should be broken in V2"

    # 3. Load stored fingerprint and auto-relocate!
    stored_fp = engine.load_fingerprint("store.com", "price")
    assert stored_fp is not None

    healed_el = engine.relocate(sel_v2, stored_fp, min_confidence=0.70)
    assert healed_el is not None
    assert healed_el.text == "₹85,000"
    assert healed_el.get("data-qa") == "product_price"


def test_builtin_auto_save_and_adaptive_relocation(tmp_path):
    db = str(tmp_path / "fp.db")
    v1 = Selector(HTML_V1, url="https://store.com/item", adaptive=True, storage=db)
    assert v1.css(".old-price-class::text", identifier="price", auto_save=True).get() == "₹85,000"
    v2 = Selector(HTML_V2.replace("<span", "<div").replace("</span>", "</div>"),  # class renamed AND tag changed
                  url="https://store.com/item", adaptive=True, storage=db)
    assert v2.css(".old-price-class", identifier="price") == []          # adaptive off: plain miss
    healed = v2.css(".old-price-class", identifier="price", adaptive=True)
    assert healed[0].text == "₹85,000" and healed[0].tag == "div"
    assert v2.css(".old-price-class::text", identifier="price", adaptive=True).get() == "₹85,000"


def test_ambiguous_relocation_is_rejected(tmp_path):
    engine = AdaptiveEngine(db_path=str(tmp_path / "fp.db"))
    fp = NodeFingerprint.from_element(Selector("<ul><li>A</li></ul>").css("li")[0])
    # two structurally identical candidates (same path, position and context): refusing beats guessing
    assert engine.relocate(Selector("<div><ul><li>B</li></ul><ul><li>B</li></ul></div>"), fp) is None
    # the original position breaks a tie between otherwise identical siblings
    assert engine.relocate(Selector("<ul><li>B</li><li>B</li></ul>"), fp) is not None
