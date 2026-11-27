"""Zero-config extraction for every kind of page: recipes, events, jobs, reviews, FAQ, contacts, breadcrumbs,
pagination, tables and page-type detection."""

import json

from omniscrape import (
    build_scrape_result,
    detect_content_type,
    extract_breadcrumbs,
    extract_entities,
    extract_events,
    extract_faq,
    extract_jobs,
    extract_organization,
    extract_recipe,
    extract_reviews,
    extract_tables,
    find_next_page,
)
from omniscrape.models import FetchResult


def page(*jsonld, body: str = "", head: str = "") -> str:
    scripts = "".join(f'<script type="application/ld+json">{json.dumps(d)}</script>' for d in jsonld)
    return f"<html><head><title>T</title>{head}{scripts}</head><body>{body}</body></html>"


RECIPE = {
    "@context": "https://schema.org", "@type": "Recipe", "name": "Masala Dosa",
    "author": {"@type": "Person", "name": "Asha"}, "image": ["/img/dosa.jpg", {"url": "https://cdn.test/d2.jpg"}],
    "recipeIngredient": ["2 cups rice", "1 cup urad dal, soaked"],
    "recipeInstructions": [
        {"@type": "HowToSection", "name": "Batter", "itemListElement": [
            {"@type": "HowToStep", "text": "Grind the rice."}, {"@type": "HowToStep", "text": "Ferment overnight."}]},
        {"@type": "HowToStep", "text": "Spread on a hot pan."},
    ],
    "prepTime": "PT8H", "cookTime": "PT20M", "totalTime": "PT8H20M", "recipeYield": ["4", "4 servings"],
    "nutrition": {"@type": "NutritionInformation", "calories": "210 kcal"},
    "recipeCuisine": "South Indian", "recipeCategory": ["Breakfast"], "keywords": "dosa, crepe",
    "aggregateRating": {"@type": "AggregateRating", "ratingValue": "4.8", "ratingCount": "120"},
}

EVENT = {
    "@context": "https://schema.org", "@type": "MusicEvent", "name": "Jazz Night",
    "startDate": "2026-12-05T19:30:00+05:30", "endDate": "2026-12-05T23:00:00+05:30",
    "eventStatus": "https://schema.org/EventScheduled",
    "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
    "location": {"@type": "Place", "name": "Blue Frog", "address": {
        "@type": "PostalAddress", "streetAddress": "1 MG Road", "addressLocality": "Chennai", "addressCountry": "IN"}},
    "organizer": {"@type": "Organization", "name": "City Jazz Club"},
    "offers": {"@type": "Offer", "price": "999", "priceCurrency": "INR", "url": "/tickets/42"},
}

JOB = {
    "@context": "https://schema.org", "@type": "JobPosting", "title": "Senior Python Engineer",
    "description": "<p>Build <b>scrapers</b>.</p>", "datePosted": "2026-11-01", "validThrough": "2026-12-31",
    "employmentType": ["FULL_TIME", "CONTRACTOR"],
    "hiringOrganization": {"@type": "Organization", "name": "Bettr Labs"},
    "jobLocationType": "TELECOMMUTE",
    "jobLocation": {"@type": "Place", "address": {"@type": "PostalAddress", "addressLocality": "Bengaluru",
                                                  "addressRegion": "KA", "addressCountry": "IN"}},
    "baseSalary": {"@type": "MonetaryAmount", "currency": "INR", "value": {
        "@type": "QuantitativeValue", "minValue": 2400000, "maxValue": 3600000, "unitText": "YEAR"}},
}


def test_recipe_from_json_ld():
    r = extract_recipe(page(RECIPE), "https://food.test/dosa")
    assert r.title == "Masala Dosa" and r.author == "Asha"
    assert r.ingredients == ["2 cups rice", "1 cup urad dal, soaked"]  # commas inside an ingredient are kept
    assert r.instructions == ["Grind the rice.", "Ferment overnight.", "Spread on a hot pan."]
    assert (r.prep_time_minutes, r.cook_time_minutes, r.total_time_minutes) == (480, 20, 500)
    assert r.servings == "4 servings" and r.calories == "210 kcal" and r.cuisine == "South Indian"
    assert r.keywords == ["dosa", "crepe"] and (r.rating, r.review_count) == (4.8, 120)
    assert r.images == ["https://food.test/img/dosa.jpg", "https://cdn.test/d2.jpg"]


def test_recipe_from_microdata():
    html = """<html><body><div itemscope itemtype="https://schema.org/Recipe">
      <h1 itemprop="name">Lemon Rice</h1>
      <span itemprop="recipeIngredient">1 cup rice</span><span itemprop="recipeIngredient">1 lemon</span>
      <meta itemprop="totalTime" content="PT25M">
      <div itemprop="recipeInstructions">Cook rice. Add lemon.</div></div></body></html>"""
    r = extract_recipe(html, "https://food.test/lemon")
    assert r.title == "Lemon Rice" and r.ingredients == ["1 cup rice", "1 lemon"] and r.total_time_minutes == 25


def test_event_with_place_address_and_offer():
    (e,) = extract_events(page(EVENT), "https://events.test/jazz")
    assert e.title == "Jazz Night" and e.start_date.startswith("2026-12-05T19:30")
    assert e.status == "EventScheduled" and e.attendance_mode == "OfflineEventAttendanceMode"
    assert e.location_name == "Blue Frog" and e.address == "1 MG Road, Chennai, IN"
    assert e.organizer == "City Jazz Club" and (e.price, e.currency) == (999.0, "INR")
    assert e.ticket_url == "https://events.test/tickets/42"


def test_job_posting_salary_remote_and_html_description():
    (j,) = extract_jobs(page(JOB), "https://jobs.test/1")
    assert j.title == "Senior Python Engineer" and j.company == "Bettr Labs"
    assert j.remote is True and j.location == "Bengaluru, KA, IN"
    assert j.employment_type == "FULL_TIME, CONTRACTOR"
    assert (j.salary_min, j.salary_max, j.salary_currency, j.salary_period) == (2400000, 3600000, "INR", "YEAR")
    assert j.description == "Build scrapers."


def test_reviews_and_aggregate_rating_nested_in_product():
    product = {"@type": "Product", "name": "Kettle", "aggregateRating": {"ratingValue": 4.2, "reviewCount": 37},
               "review": [{"@type": "Review", "author": {"name": "Ravi"}, "reviewBody": "Boils fast.",
                           "reviewRating": {"ratingValue": 5, "bestRating": 5}, "datePublished": "2026-10-01"},
                          {"@type": "Review", "author": "Meena", "reviewBody": "Loud.",
                           "reviewRating": {"ratingValue": 2}}]}
    reviews, rating, count = extract_reviews(page(product))
    assert [(r.author, r.rating, r.body) for r in reviews] == [("Ravi", 5.0, "Boils fast."), ("Meena", 2.0, "Loud.")]
    assert reviews[0].best_rating == 5.0 and reviews[0].date == "2026-10-01"
    assert (rating, count) == (4.2, 37)


def test_faq_from_faqpage_and_from_details_accordion():
    faq = {"@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": "Is it free?", "acceptedAnswer": {"@type": "Answer", "text": "<p>Yes, MIT.</p>"}},
        {"@type": "Question", "name": "Python?", "acceptedAnswer": {"@type": "Answer", "text": "3.11+"}}]}
    items = extract_faq(page(faq))
    assert [(i.question, i.answer) for i in items] == [("Is it free?", "Yes, MIT."), ("Python?", "3.11+")]

    html = page(body="<details><summary>Shipping?</summary><p>3 days.</p></details>"
                     "<details><summary>Returns?</summary><p>30 days.</p></details>")
    assert [(i.question, i.answer) for i in extract_faq(html)] == [("Shipping?", "3 days."), ("Returns?", "30 days.")]


def test_breadcrumbs_from_json_ld_sorted_by_position_and_from_dom():
    crumbs = {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 2, "name": "Shoes", "item": "/shoes"},
        {"@type": "ListItem", "position": 1, "name": "Home", "item": {"@id": "https://shop.test/"}},
        {"@type": "ListItem", "position": 3, "name": "Running"}]}
    got = extract_breadcrumbs(page(crumbs), "https://shop.test/shoes/running")
    assert [(c.name, c.url) for c in got] == [("Home", "https://shop.test/"),
                                              ("Shoes", "https://shop.test/shoes"), ("Running", None)]

    html = page(body='<nav aria-label="Breadcrumb"><ol><li><a href="/">Home</a></li>'
                     '<li><a href="/docs">Docs</a></li><li>Install</li></ol></nav>')
    got = extract_breadcrumbs(html, "https://site.test/docs/install")
    assert [(c.name, c.url) for c in got] == [("Home", "https://site.test/"), ("Docs", "https://site.test/docs"),
                                              ("Install", None)]


def test_organization_contacts_from_markup_links_and_text():
    org = {"@type": "Restaurant", "name": "Saravana", "telephone": "+91 44 1234 5678",
           "address": {"@type": "PostalAddress", "streetAddress": "12 Anna Salai", "addressLocality": "Chennai"},
           "sameAs": ["https://www.instagram.com/saravana"], "logo": "/logo.png"}
    html = page(org, body='<a href="mailto:hello@saravana.test?subject=hi">Mail</a>'
                          '<a href="tel:+914400000000">Call</a>'
                          '<a href="https://twitter.com/saravana">Twitter</a>'
                          '<a href="https://twitter.com/intent/tweet?text=x">Share</a>'
                          '<p>Catering: events@saravana.test</p><img src="logo@2x.png">')
    o = extract_organization(html, "https://saravana.test/contact")
    assert o.name == "Saravana" and o.address == "12 Anna Salai, Chennai"
    assert o.emails == ["hello@saravana.test", "events@saravana.test"]
    assert o.phones == ["+91 44 1234 5678", "+914400000000"]
    assert o.social_profiles == ["https://www.instagram.com/saravana", "https://twitter.com/saravana"]
    assert o.logo == "https://saravana.test/logo.png"


def test_organization_is_none_without_markup_or_contacts():
    assert extract_organization(page(body="<p>Just text</p>")) is None


def test_find_next_page_variants():
    base = "https://blog.test/page/2"
    assert find_next_page(page(head='<link rel="next" href="/page/3">'), base) == "https://blog.test/page/3"
    assert find_next_page(page(body='<a href="?p=3" aria-label="Next page">›</a>'), base) == "https://blog.test/page/2?p=3"
    pager = ('<nav class="pagination"><a href="/page/1">1</a><span aria-current="page">2</span>'
             '<a href="/page/3">3</a><a href="/page/4">4</a></nav>')
    assert find_next_page(page(body=pager), base) == "https://blog.test/page/3"
    assert find_next_page(page(body='<ul class="pager"><li><a href="/page/3">»</a></li></ul>'), base) == \
        "https://blog.test/page/3"
    # "Next post" goes to another article, not the next page of results.
    assert find_next_page(page(body='<a href="/post/9">Next post: Hello</a>'), base) is None
    assert find_next_page(page(body='<a href="#">Next</a>'), base) is None


def test_tables_skip_layout_and_single_row_tables():
    html = page(body="<table><tr><td><table><tr><th>a</th><th>b</th></tr><tr><td>1</td><td>2</td></tr></table>"
                     "</td></tr></table><table><tr><td>only</td><td>row</td></tr></table>")
    assert extract_tables(html) == [[{"a": "1", "b": "2"}]]


def test_detect_content_type_for_each_kind():
    assert detect_content_type(page(RECIPE)) == "recipe"
    assert detect_content_type(page(EVENT)) == "event"
    assert detect_content_type(page(JOB)) == "job"
    assert detect_content_type(page(JOB, dict(JOB, title="Two"))) == "listing"
    assert detect_content_type(page({"@type": "FAQPage", "mainEntity": []})) == "faq"
    assert detect_content_type(page({"@type": "NewsArticle", "headline": "x"})) == "article"
    assert detect_content_type(page({"@type": "Product", "name": "x", "offers": {"price": "1"}})) == "product"
    assert detect_content_type(page({"@type": "CollectionPage"})) == "listing"
    assert detect_content_type(page({"@type": "ContactPage"})) == "organization"
    assert detect_content_type(page(body="<p>hello</p>"), "https://x.test/") == "other"
    cards = "".join(f'<div class="card"><a href="/p/{i}"><img src="/i{i}.jpg"><h3>Item {i}</h3></a>'
                    f'<span class="price">$1{i}.00</span></div>' for i in range(10))
    assert detect_content_type(page(body=f'<div class="grid">{cards}</div>'), "https://shop.test/") == "listing"


def test_detect_content_type_matches_corpus_labels():
    """Page-type detection against the 143 hand-labelled benchmark pages (articles, products, listings)."""
    import glob
    import os

    root = os.path.join(os.path.dirname(__file__), "..", "..", "benchmarks", "corpus", "data")
    total = correct = 0
    for meta_path in glob.glob(os.path.join(root, "*", "*.json")):
        with open(meta_path, encoding="utf-8") as fh:
            label = json.load(fh)
        if not isinstance(label, dict) or label.get("type") not in ("article", "product", "listing"):
            continue
        with open(meta_path[:-5] + ".html", encoding="utf-8", errors="replace") as fh:
            html = fh.read()
        res = build_scrape_result(FetchResult(url=label["url"], status_code=200, html=html))
        expected = label["type"]
        got = res.content_type
        total += 1
        correct += got == expected or (expected == "article" and got == "recipe")
        if expected != "product":
            assert res.product is None, f"{meta_path}: false-positive product on a {expected} page"
    assert total == 143
    assert correct >= 140, f"only {correct}/{total} pages classified correctly"


def test_scrape_result_carries_entities_and_content_type():
    html = page(RECIPE, body='<nav aria-label="breadcrumb"><a href="/">Home</a> › <a href="/r">Recipes</a></nav>'
                             '<a rel="next" href="/dosa?page=2">Next</a>')
    res = build_scrape_result(FetchResult(url="https://food.test/dosa", status_code=200, html=html))
    assert res.content_type == "recipe"
    assert res.entities.recipe.title == "Masala Dosa"
    assert res.entities.next_page == "https://food.test/dosa?page=2"
    assert res.entities.rating == 4.8
    dumped = res.model_dump(mode="json")
    assert dumped["entities"]["recipe"]["ingredients"][0] == "2 cups rice"


def test_extract_entities_on_plain_page_is_empty():
    ents = extract_entities(page(body="<p>nothing structured here</p>"), "https://x.test/")
    assert ents.recipe is None and not ents.events and not ents.jobs and not ents.faq
    assert ents.organization is None and ents.next_page is None and not ents.tables
