"""Zero-config extraction for every common kind of page, beyond products and articles.

Structured data (JSON-LD, Microdata, RDFa) is read first because sites publish it for search engines and it is
the most reliable signal; DOM fallbacks cover pages that have none (breadcrumbs, FAQ accordions, contact links,
pagination, data tables).

    >>> from omniscrape import extract_entities, detect_content_type
    >>> ents = extract_entities(html, url)
    >>> ents.recipe.ingredients, ents.jobs[0].salary_min, ents.next_page
"""

import itertools
import re
from typing import Any, Iterator, Optional, Union
from urllib.parse import urljoin, urlsplit

import lxml.html

from omniscrape.models import (
    Breadcrumb,
    Event,
    FAQItem,
    JobPosting,
    Organization,
    PageEntities,
    Recipe,
    Review,
)
from omniscrape.parsers.structured import as_root, extract_structured, first_text, type_names

# ----------------------------------------------------------------------------- generic helpers
_ORG_TYPES = {
    "Organization", "Corporation", "LocalBusiness", "NGO", "EducationalOrganization", "GovernmentOrganization",
    "MedicalOrganization", "NewsMediaOrganization", "OnlineStore", "OnlineBusiness", "Store", "Restaurant",
    "Hotel", "LodgingBusiness", "FoodEstablishment", "ProfessionalService", "LegalService", "Dentist",
    "Physician", "MedicalClinic", "AutoDealer", "RealEstateAgent", "FinancialService", "SportsClub",
    "HealthAndBeautyBusiness", "HomeAndConstructionBusiness", "EntertainmentBusiness", "TravelAgency",
    "CollegeOrUniversity", "School", "Library", "Museum",
}
_SOCIAL_HOSTS = (
    "facebook.com", "twitter.com", "x.com", "linkedin.com", "instagram.com", "youtube.com", "github.com",
    "tiktok.com", "pinterest.com", "threads.net", "mastodon.social", "bsky.app", "t.me", "wa.me",
)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,24}")
_NOT_EMAIL_SUFFIX = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js")
_DURATION_RE = re.compile(r"^P(?:(\d+(?:\.\d+)?)D)?(?:T(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?)?$", re.I)
_NEXT_TEXT = {"next", "next page", "next ›", "next »", "next >", "next →", "›", "»", "→", ">", "older posts",
              "older entries", "more results", "load more"}


def _prepare(html_or_root: Union[str, bytes, Any], url: str,
             structured: Optional[dict[str, Any]]) -> tuple[Any, dict[str, Any]]:
    root = as_root(html_or_root)
    if structured is None:
        structured = extract_structured(root, url)
    return root, structured


def _walk(value: Any, depth: int = 0) -> Iterator[dict[str, Any]]:
    """Every dict with an ``@type`` in a structured-data tree (nested entities included)."""
    if depth > 8:
        return
    if isinstance(value, list):
        for v in value:
            yield from _walk(v, depth + 1)
    elif isinstance(value, dict):
        if value.get("@type"):
            yield value
        for k, v in value.items():
            if not k.startswith("@") and isinstance(v, (dict, list)):
                yield from _walk(v, depth + 1)


def _identity(item: dict[str, Any]) -> Any:
    """De-duplication key: the JSON-LD/microdata ``@id`` when present (resolved references are *copies* of the
    referenced item), otherwise the object itself."""
    ident = item.get("@id")
    return ("@id", ident) if isinstance(ident, str) and ident else ("obj", id(item))


def _items(structured: dict[str, Any], types: set[str], suffix: Optional[str] = None) -> list[dict[str, Any]]:
    """Structured items whose type is in ``types`` (or ends with ``suffix``), de-duplicated, in page order."""
    out: list[dict[str, Any]] = []
    seen: set[Any] = set()
    for source in ("json-ld", "microdata", "rdfa"):
        for item in _walk(structured.get(source, [])):
            names = type_names(item)
            if not (names & types or (suffix and any(n.endswith(suffix) for n in names))):
                continue
            key = _identity(item)
            if key not in seen:
                seen.add(key)
                out.append(item)
    return out


def _unique(models: list[Any], *fields: str) -> list[Any]:
    """Drop entities that repeat the same ``fields`` (e.g. the same job published as JSON-LD *and* microdata)."""
    out, seen = [], set()
    for m in models:
        key = tuple((getattr(m, f) or "") for f in fields)
        if key not in seen:
            seen.add(key)
            out.append(m)
    return out


def _text(value: Any) -> Optional[str]:
    """Plain text from a structured value that may contain HTML."""
    text = first_text(value)
    if text and "<" in text and ">" in text:
        try:
            text = " ".join(lxml.html.fromstring(text).text_content().split())
        except (lxml.etree.ParserError, ValueError):
            pass
    return text or None


def _number(value: Any) -> Optional[float]:
    if isinstance(value, dict):
        value = value.get("@value", value.get("value"))
    if isinstance(value, list):
        value = value[0] if value else None
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        match = re.search(r"\d+(?:\.\d+)?", str(value))
        return float(match.group()) if match else None


def _int(value: Any) -> Optional[int]:
    num = _number(value)
    return int(num) if num is not None else None


def _images(value: Any, base: str) -> list[str]:
    out: list[str] = []
    for v in value if isinstance(value, list) else [value]:
        if isinstance(v, dict):
            v = v.get("url") or v.get("contentUrl") or v.get("@id")
        if isinstance(v, list):
            out.extend(_images(v, base))
        elif isinstance(v, str) and v.strip():
            out.append(urljoin(base, v.strip()))
    return list(dict.fromkeys(out))


def _strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [s.strip() for s in value.split(",") if s.strip()]
    if isinstance(value, list):
        return [t for v in value if (t := _text(v))]
    t = _text(value)
    return [t] if t else []


def _duration_minutes(value: Any) -> Optional[int]:
    """ISO 8601 duration (``PT1H30M``) or plain minutes -> whole minutes."""
    text = first_text(value)
    if not text:
        return None
    match = _DURATION_RE.match(text.strip())
    if match and any(match.groups()):
        days, hours, minutes, seconds = (float(g) if g else 0.0 for g in match.groups())
        return round(days * 1440 + hours * 60 + minutes + seconds / 60)
    num = _number(text)
    return int(num) if num is not None else None


def _address(value: Any) -> Optional[str]:
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, str):
        return " ".join(value.split()) or None
    if not isinstance(value, dict):
        return None
    if value.get("address") is not None and "streetAddress" not in value:
        return _address(value["address"])
    parts = []
    for key in ("streetAddress", "addressLocality", "addressRegion", "postalCode", "addressCountry"):
        part = first_text(value.get(key))
        if part and part not in parts:
            parts.append(part)
    return ", ".join(parts) or None


def _rating(item: dict[str, Any]) -> tuple[Optional[float], Optional[int]]:
    agg = item.get("aggregateRating")
    if isinstance(agg, list):
        agg = agg[0] if agg else None
    if not isinstance(agg, dict):
        return None, None
    return _number(agg.get("ratingValue")), _int(agg.get("ratingCount") or agg.get("reviewCount"))


def _offer(item: dict[str, Any]) -> tuple[Optional[float], Optional[str], Optional[str]]:
    offers = item.get("offers")
    if isinstance(offers, list):
        offers = offers[0] if offers else None
    if not isinstance(offers, dict):
        return None, None, None
    price = _number(offers.get("price") or offers.get("lowPrice"))
    return price, first_text(offers.get("priceCurrency")), first_text(offers.get("url"))


def _enum(value: Any) -> Optional[str]:
    """``https://schema.org/EventScheduled`` -> ``EventScheduled``."""
    text = first_text(value)
    return text.rstrip("/").rsplit("/", 1)[-1] if text else None


# ----------------------------------------------------------------------------- recipe
def _instructions(value: Any) -> list[str]:
    steps: list[str] = []
    for v in value if isinstance(value, list) else [value]:
        if isinstance(v, dict):
            if v.get("itemListElement"):  # HowToSection
                steps.extend(_instructions(v["itemListElement"]))
                continue
            text = _text(v.get("text") or v.get("name"))
            if text:
                steps.append(text)
        elif isinstance(v, str):
            steps.extend(_split_steps(v))
    return steps


_NUMBERED_STEP = re.compile(r"(?:^|(?<=[.!?])\s+)(?:step\s*)?\d{1,2}[.):]\s+", re.I)


def _split_steps(raw: str) -> list[str]:
    """Split one block of recipe instructions into steps: list items / paragraphs / lines first, then
    "1. ... 2. ..." numbering that starts a sentence. Plain sentences are not split."""
    chunks: list[str]
    if "<" in raw and ">" in raw:
        try:
            frag = lxml.html.fromstring(f"<div>{raw}</div>")
            blocks = [" ".join(el.text_content().split()) for el in frag.iter("li", "p")]
            chunks = [b for b in blocks if b] or [frag.text_content()]
        except (lxml.etree.ParserError, ValueError):
            chunks = [raw]
    else:
        chunks = [c for c in re.split(r"\r?\n+", raw) if c.strip()]
    steps: list[str] = []
    for chunk in chunks:
        chunk = " ".join(chunk.split())
        parts = [p.strip() for p in _NUMBERED_STEP.split(chunk) if p.strip()]
        steps.extend(parts)
    return steps


def extract_recipe(html_or_root: Union[str, bytes, Any], url: str = "",
                   structured: Optional[dict[str, Any]] = None) -> Optional[Recipe]:
    """The page's recipe (schema.org Recipe), or ``None``."""
    _, structured = _prepare(html_or_root, url, structured)
    for item in _items(structured, {"Recipe"}):
        title = _text(item.get("name"))
        if not title:
            continue
        rating, count = _rating(item)
        nutrition: dict[str, Any] = item["nutrition"] if isinstance(item.get("nutrition"), dict) else {}
        yields = item.get("recipeYield")
        if isinstance(yields, list):
            yields = next((y for y in yields if isinstance(y, str) and not y.isdigit()), yields[0] if yields else None)
        raw_ingredients = item.get("recipeIngredient") or item.get("ingredients") or []
        if not isinstance(raw_ingredients, list):
            raw_ingredients = [raw_ingredients]  # one string: do not split on commas ("1 cup flour, sifted")
        return Recipe(
            url=url, title=title, description=_text(item.get("description")), author=_text(item.get("author")),
            images=_images(item.get("image"), url),
            ingredients=[t for i in raw_ingredients if (t := _text(i))],
            instructions=_instructions(item.get("recipeInstructions")),
            prep_time_minutes=_duration_minutes(item.get("prepTime")),
            cook_time_minutes=_duration_minutes(item.get("cookTime")),
            total_time_minutes=_duration_minutes(item.get("totalTime")),
            servings=first_text(yields), calories=first_text(nutrition.get("calories")),
            cuisine=", ".join(_strings(item.get("recipeCuisine"))) or None,
            category=", ".join(_strings(item.get("recipeCategory"))) or None,
            keywords=_strings(item.get("keywords")), rating=rating, review_count=count,
        )
    return None


# ----------------------------------------------------------------------------- events
def extract_events(html_or_root: Union[str, bytes, Any], url: str = "",
                   structured: Optional[dict[str, Any]] = None) -> list[Event]:
    """Every schema.org Event on the page (concerts, conferences, webinars, ...)."""
    _, structured = _prepare(html_or_root, url, structured)
    events: list[Event] = []
    for item in _items(structured, {"Event", "Festival", "CourseInstance"}, suffix="Event"):
        title = _text(item.get("name"))
        if not title:
            continue
        location = item.get("location")
        if isinstance(location, list):
            location = location[0] if location else None
        loc_name = _text(location.get("name")) if isinstance(location, dict) else _text(location)
        address = _address(location) if isinstance(location, dict) else None
        if isinstance(location, dict) and "VirtualLocation" in type_names(location):
            address = address or first_text(location.get("url"))
        price, currency, ticket = _offer(item)
        events.append(Event(
            url=url, title=title, description=_text(item.get("description")),
            start_date=first_text(item.get("startDate")), end_date=first_text(item.get("endDate")),
            status=_enum(item.get("eventStatus")), attendance_mode=_enum(item.get("eventAttendanceMode")),
            location_name=loc_name, address=address, organizer=_text(item.get("organizer")),
            price=price, currency=currency, ticket_url=urljoin(url, ticket) if ticket else None,
            images=_images(item.get("image"), url),
        ))
    return _unique(events, "title", "start_date", "location_name")


# ----------------------------------------------------------------------------- jobs
def _salary(value: Any) -> tuple[Optional[float], Optional[float], Optional[str], Optional[str]]:
    if isinstance(value, list):
        value = value[0] if value else None
    if not isinstance(value, dict):
        num = _number(value)
        return num, num, None, None
    currency = first_text(value.get("currency"))
    inner = value.get("value", value)
    if not isinstance(inner, dict):
        num = _number(inner)
        return num, num, currency, first_text(value.get("unitText"))
    low = _number(inner.get("minValue"))
    high = _number(inner.get("maxValue"))
    exact = _number(inner.get("value"))
    if low is None and high is None:
        low = high = exact
    return low, high, currency, first_text(inner.get("unitText") or value.get("unitText"))


def extract_jobs(html_or_root: Union[str, bytes, Any], url: str = "",
                 structured: Optional[dict[str, Any]] = None) -> list[JobPosting]:
    """Every schema.org JobPosting on the page."""
    _, structured = _prepare(html_or_root, url, structured)
    jobs: list[JobPosting] = []
    for item in _items(structured, {"JobPosting"}):
        title = _text(item.get("title") or item.get("name"))
        if not title:
            continue
        locations = item.get("jobLocation")
        locations = locations if isinstance(locations, list) else [locations]
        location = "; ".join(a for loc in locations if (a := _address(loc))) or None
        remote = "TELECOMMUTE" in (first_text(item.get("jobLocationType")) or "").upper()
        low, high, currency, period = _salary(item.get("baseSalary") or item.get("estimatedSalary"))
        employment = _strings(item.get("employmentType"))
        jobs.append(JobPosting(
            url=url, title=title, company=_text(item.get("hiringOrganization")), location=location,
            remote=remote, employment_type=", ".join(employment) or None,
            date_posted=first_text(item.get("datePosted")), valid_through=first_text(item.get("validThrough")),
            salary_min=low, salary_max=high, salary_currency=currency, salary_period=period,
            description=_text(item.get("description")),
        ))
    return _unique(jobs, "title", "company", "location")


# ----------------------------------------------------------------------------- reviews
def extract_reviews(html_or_root: Union[str, bytes, Any], url: str = "",
                    structured: Optional[dict[str, Any]] = None) -> tuple[list[Review], Optional[float], Optional[int]]:
    """``(reviews, aggregate_rating, rating_count)`` for the page's main reviewed item."""
    _, structured = _prepare(html_or_root, url, structured)
    reviews: list[Review] = []
    for item in _items(structured, {"Review"}):
        rating: dict[str, Any] = item["reviewRating"] if isinstance(item.get("reviewRating"), dict) else {}
        body = _text(item.get("reviewBody") or item.get("description") or item.get("text"))
        author = _text(item.get("author"))
        if not (body or rating):
            continue
        reviews.append(Review(
            author=author, rating=_number(rating.get("ratingValue")), best_rating=_number(rating.get("bestRating")),
            title=_text(item.get("name")) if item.get("name") != body else None, body=body,
            date=first_text(item.get("datePublished") or item.get("dateCreated")),
        ))
    agg_value: Optional[float] = None
    agg_count: Optional[int] = None
    for item in _walk([structured.get(s, []) for s in ("json-ld", "microdata", "rdfa")]):
        value, count = _rating(item)
        if value is not None:
            agg_value, agg_count = value, count
            break
    if agg_value is None:
        for item in _items(structured, {"AggregateRating"}):
            agg_value = _number(item.get("ratingValue"))
            agg_count = _int(item.get("ratingCount") or item.get("reviewCount"))
            if agg_value is not None:
                break
    return reviews, agg_value, agg_count


# ----------------------------------------------------------------------------- FAQ
def extract_faq(html_or_root: Union[str, bytes, Any], url: str = "",
                structured: Optional[dict[str, Any]] = None) -> list[FAQItem]:
    """Question / answer pairs from FAQPage markup, or from ``<details><summary>`` accordions."""
    root, structured = _prepare(html_or_root, url, structured)
    faq: list[FAQItem] = []
    seen: set[str] = set()
    for item in _items(structured, {"Question"}):
        question = _text(item.get("name") or item.get("text"))
        answer = item.get("acceptedAnswer") or item.get("suggestedAnswer")
        if isinstance(answer, list):
            answer = answer[0] if answer else None
        answer_text = _text(answer.get("text")) if isinstance(answer, dict) else _text(answer)
        if question and answer_text and question not in seen:
            seen.add(question)
            faq.append(FAQItem(question=question, answer=answer_text))
    if faq:
        return faq
    # DOM fallback: accordion widgets built from <details><summary>.
    pairs = []
    for details in root.iter("details"):
        summary = details.find(".//summary")
        if summary is None:
            continue
        question = " ".join(summary.text_content().split())
        answer = " ".join(details.text_content().split())
        answer = answer[len(question):].strip() if answer.startswith(question) else answer
        if question and answer:
            pairs.append(FAQItem(question=question, answer=answer))
    return pairs if len(pairs) >= 2 else []


# ----------------------------------------------------------------------------- breadcrumbs
def extract_breadcrumbs(html_or_root: Union[str, bytes, Any], url: str = "",
                        structured: Optional[dict[str, Any]] = None) -> list[Breadcrumb]:
    """The page's breadcrumb trail, from BreadcrumbList markup or a breadcrumb ``<nav>``."""
    root, structured = _prepare(html_or_root, url, structured)
    for item in _items(structured, {"BreadcrumbList"}):
        elements = item.get("itemListElement") or []
        elements = elements if isinstance(elements, list) else [elements]
        crumbs = []
        for pos, el in sorted(enumerate(e for e in elements if isinstance(e, dict)),
                              key=lambda p: (_number(p[1].get("position")) or p[0])):
            target = el.get("item")
            name = _text(el.get("name")) or (_text(target.get("name")) if isinstance(target, dict) else None)
            link = first_text(target.get("@id") or target.get("url")) if isinstance(target, dict) else first_text(target)
            if name:
                crumbs.append(Breadcrumb(name=name, url=urljoin(url, link) if link else None))
        if crumbs:
            return crumbs
    # DOM fallback
    for container in root.xpath(
        "//nav[contains(translate(@aria-label,'BREADCRUMB','breadcrumb'),'breadcrumb')]"
        " | //*[contains(concat(' ',normalize-space(translate(@class,'BREADCRUMB','breadcrumb')),' '),'breadcrumb')]"
    ):
        crumbs = []
        for node in container.xpath(".//li | .//a[not(ancestor::li)]"):
            link_el = node if node.tag == "a" else node.find(".//a")
            name = " ".join(node.text_content().split()).strip(" >/›»|")
            if not name or len(name) > 80:
                continue
            href = link_el.get("href") if link_el is not None else None
            crumbs.append(Breadcrumb(name=name, url=urljoin(url, href) if href else None))
        if len(crumbs) >= 2:
            return crumbs
    return []


# ----------------------------------------------------------------------------- organisation / contacts
def extract_organization(html_or_root: Union[str, bytes, Any], url: str = "",
                         structured: Optional[dict[str, Any]] = None) -> Optional[Organization]:
    """The organisation behind the page with emails, phones, address and social profiles.

    Returns ``None`` when the page has neither organisation markup nor any contact details.
    """
    root, structured = _prepare(html_or_root, url, structured)
    org_items = _items(structured, _ORG_TYPES)
    org = org_items[0] if org_items else {}
    emails: list[str] = []
    phones: list[str] = []
    socials: list[str] = []

    for item in org_items[:3]:
        if (email := first_text(item.get("email"))):
            emails.append(email.removeprefix("mailto:").strip())
        if (phone := first_text(item.get("telephone"))):
            phones.append(phone)
        points = item.get("contactPoint")
        points = points if isinstance(points, list) else [points]
        for point in (p for p in points if isinstance(p, dict)):
            if (email := first_text(point.get("email"))):
                emails.append(email.removeprefix("mailto:").strip())
            if (phone := first_text(point.get("telephone"))):
                phones.append(phone)
        same_as = item.get("sameAs")
        socials.extend(s for s in (same_as if isinstance(same_as, list) else [same_as]) if isinstance(s, str))

    for a in root.iter("a"):
        href = (a.get("href") or "").strip()
        low = href.lower()
        if low.startswith("mailto:"):
            emails.append(href[7:].split("?", 1)[0].strip())
        elif low.startswith("tel:"):
            phones.append(href[4:].strip())
        elif low.startswith(("http://", "https://")):
            host = (urlsplit(href).hostname or "").lower().removeprefix("www.")
            if any(host == s or host.endswith("." + s) for s in _SOCIAL_HOSTS):
                path = urlsplit(href).path.strip("/")
                if path and not path.startswith(("share", "intent", "sharer", "dialog")):
                    socials.append(href)

    body = root.find(".//body")
    if body is not None:
        visible = " ".join(body.xpath(".//text()[not(ancestor::script or ancestor::style or ancestor::noscript"
                                      " or ancestor::template)]"))
        for match in _EMAIL_RE.findall(visible):
            if not match.lower().endswith(_NOT_EMAIL_SUFFIX):
                emails.append(match)

    emails = list(dict.fromkeys(e.lower() for e in emails if "@" in e))[:20]
    phones = list(dict.fromkeys(" ".join(p.split()) for p in phones if sum(ch.isdigit() for ch in p) >= 6))[:20]
    socials = list(dict.fromkeys(socials))[:20]
    if not org and not emails and not phones:
        return None

    meta = structured.get("opengraph", {})
    logo = org.get("logo")
    return Organization(
        name=_text(org.get("name")) or first_text(meta.get("og:site_name")),
        url=first_text(org.get("url")) or None,
        logo=next(iter(_images(logo, url)), None),
        description=_text(org.get("description")),
        emails=emails, phones=phones, address=_address(org.get("address")), social_profiles=socials,
    )


# ----------------------------------------------------------------------------- pagination
_NOT_PAGINATION = ("next post", "next article", "next story", "next video", "next episode")


def _tokens(value: str) -> set[str]:
    return {t for t in re.split(r"[\s_\-]+", value.lower()) if t}


def _hint(el: Any) -> str:
    return f"{el.get('class') or ''} {el.get('id') or ''} {el.get('aria-label') or ''}"


_PAGER_TOKENS = {"pagination", "pager", "paging", "paginate", "paginator", "pagenav", "pagenavi", "pagelinks",
                 "pages", "wp-pagenavi"}


def _is_pager(el: Any) -> bool:
    """True for pagination containers (``.pagination``, ``.pager``, ``.page-numbers``, ``nav[aria-label=Pages]``),
    not for generic wrappers such as ``id="page"`` or ``.page-content``."""
    tokens = _tokens(_hint(el))
    if tokens & _PAGER_TOKENS:
        return True
    return "page" in tokens and bool(tokens & {"numbers", "nav", "navigation", "links", "list"})


def find_next_page(html_or_root: Union[str, bytes, Any], url: str = "") -> Optional[str]:
    """Absolute URL of the next page of results (``rel=next``, "Next" buttons, numbered pagers), or ``None``.

    Links to the next *article* ("Next post", "Next article") are not pagination and are ignored.
    """
    root = as_root(html_or_root)
    here = url.split("#")[0]

    def ok(href: Optional[str]) -> Optional[str]:
        href = (href or "").strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            return None
        absolute = urljoin(url, href)
        return absolute if absolute.split("#")[0] != here else None

    # 1. Explicit rel="next" (<link> in <head> or <a>): the most reliable signal.
    for el in root.xpath("//link[@href] | //a[@href]"):
        if "next" in (el.get("rel") or "").lower().split() and (found := ok(el.get("href"))):
            return found

    # 2. A link labelled or classed "next", or an arrow inside a pager.
    for a in root.xpath("//a[@href]"):
        text = " ".join(a.text_content().split()).lower()
        if text.startswith(_NOT_PAGINATION):
            continue
        label = (a.get("aria-label") or a.get("title") or "").strip().lower()
        own = _tokens(f"{a.get('class') or ''} {a.get('id') or ''}")
        in_pager = _is_pager(a) or any(_is_pager(p) for p in itertools.islice(a.iterancestors(), 4))
        if (label.startswith("next") or "next" in own or text in ("next", "next page", "older posts",
                                                                  "older entries", "more results")
                or (text.startswith("next ") and in_pager) or (in_pager and text in _NEXT_TEXT)):
            if (found := ok(a.get("href"))):
                return found

    # 3. Numbered pager: the first numeric link after the current-page marker, in document order.
    markers = root.xpath("//*[@aria-current='page'] | //*[contains(concat(' ',normalize-space(@class),' '),' current ')]"
                         " | //*[contains(concat(' ',normalize-space(@class),' '),' active ')]")
    for current in markers:
        pager = next((p for p in itertools.islice(current.iterancestors(), 6) if _is_pager(p)), None)
        if pager is None:
            continue
        inside_current = set(map(id, current.iter()))
        passed = False
        for el in pager.iter():
            if id(el) in inside_current:
                passed = True
                continue
            if passed and el.tag == "a" and el.get("href"):
                if re.fullmatch(r"\d+", " ".join(el.text_content().split())) and (found := ok(el.get("href"))):
                    return found
    return None


# ----------------------------------------------------------------------------- tables
def extract_tables(html_or_root: Union[str, bytes, Any], max_tables: int = 10,
                   max_rows: int = 200) -> list[list[dict[str, str]]]:
    """Data tables as lists of row dicts (layout tables and one-row tables are skipped)."""
    from omniscrape.parsers.selector import Element
    from omniscrape.parsers.tables import TableParser

    root = as_root(html_or_root)
    tables: list[list[dict[str, str]]] = []
    for table in root.iter("table"):
        if table.find(".//table") is not None:  # layout table wrapping other tables
            continue
        rows = table.xpath(".//tr")
        if len(rows) < 2 or max((len(r.xpath("./td|./th")) for r in rows), default=0) < 2:
            continue
        parsed = TableParser.parse_table(Element(table, ""))[:max_rows]
        if parsed:
            tables.append(parsed)
        if len(tables) >= max_tables:
            break
    return tables


# ----------------------------------------------------------------------------- page type + everything
def extract_entities(html_or_root: Union[str, bytes, Any], url: str = "",
                     structured: Optional[dict[str, Any]] = None) -> PageEntities:
    """Run every zero-config extractor in this module over one parsed page."""
    root, structured = _prepare(html_or_root, url, structured)
    reviews, rating, rating_count = extract_reviews(root, url, structured)
    return PageEntities(
        recipe=extract_recipe(root, url, structured),
        events=extract_events(root, url, structured),
        jobs=extract_jobs(root, url, structured),
        reviews=reviews, rating=rating, rating_count=rating_count,
        faq=extract_faq(root, url, structured),
        organization=extract_organization(root, url, structured),
        breadcrumbs=extract_breadcrumbs(root, url, structured),
        next_page=find_next_page(root, url),
        tables=extract_tables(root),
    )


CONTENT_TYPES = ("product", "article", "recipe", "event", "job", "listing", "faq", "organization", "other")

_LISTING_TYPES = {"ItemList", "CollectionPage", "SearchResultsPage", "OfferCatalog"}
_ARTICLE_TYPES = {"Article", "NewsArticle", "BlogPosting", "Report", "ScholarlyArticle", "TechArticle",
                  "LiveBlogPosting", "OpinionNewsArticle", "AnalysisNewsArticle", "ReviewNewsArticle"}
ARTICLE_MARKUP_TYPES = frozenset(_ARTICLE_TYPES)
_UNSET: Any = object()


def product_markup_count(structured: dict[str, Any]) -> int:
    """Number of distinct top-level Product items (variants nested in a ProductGroup are not counted)."""
    seen: set[Any] = set()
    for source in ("json-ld", "microdata", "rdfa"):
        for item in structured.get(source, []):
            if isinstance(item, dict) and "Product" in type_names(item):
                seen.add(_identity(item))
            for key in ("mainEntity", "about"):
                nested = item.get(key) if isinstance(item, dict) else None
                if isinstance(nested, dict) and "Product" in type_names(nested):
                    seen.add(_identity(nested))
    return len(seen)


def page_signals(html_or_root: Union[str, bytes, Any], url: str = "") -> tuple[int, int]:
    """``(repeated_item_links, prices)`` in the page body, outside ``nav``/``header``/``footer``.

    *repeated_item_links* is the size of the largest group of same-site links sharing a URL shape (first path
    segment and depth), e.g. 24 links like ``/catalogue/<book>/index.html``; listing pages have many, product
    pages few. *prices* counts price-like strings in the visible text.
    """
    from collections import Counter

    from omniscrape.extract.listings import _PRICE_RE

    root = as_root(html_or_root)
    body = root.find(".//body")
    if body is None:
        return 0, 0
    host = urlsplit(url).netloc
    shapes: Counter = Counter()
    for a in body.xpath(".//a[@href][not(ancestor::nav or ancestor::header or ancestor::footer)]"):
        target = urlsplit(urljoin(url, a.get("href")))
        segments = [seg for seg in target.path.split("/") if seg]
        if len(segments) >= 2 and target.netloc == host:
            shapes[(segments[0], len(segments))] += 1
    text = " ".join(body.xpath(".//text()[not(ancestor::script or ancestor::style or ancestor::noscript"
                               " or ancestor::nav or ancestor::header or ancestor::footer)]"))
    return (max(shapes.values()) if shapes else 0), len(_PRICE_RE.findall(text))


def detect_content_type(html_or_root: Union[str, bytes, Any], url: str = "",
                        structured: Optional[dict[str, Any]] = None, *,
                        entities: Optional[PageEntities] = None, product: Any = _UNSET, article: Any = _UNSET) -> str:
    """Classify a page as one of :data:`CONTENT_TYPES`.

    Structured data decides when it is present (Recipe, JobPosting, Event, Product, FAQPage, Article, ItemList,
    ContactPage). Otherwise page signals decide: many same-shaped item links with matching prices or a grid of
    cards means a listing; a priced product with few item links means a product page; then article. On the
    benchmark corpus (143 labelled pages) this matches the labels on 141.
    """
    root, structured = _prepare(html_or_root, url, structured)
    tops: set[str] = set()
    for source in ("json-ld", "microdata", "rdfa"):
        for item in structured.get(source, []):
            tops |= type_names(item)
            for key in ("mainEntity", "mainEntityOfPage"):
                if isinstance(item.get(key), dict):
                    tops |= type_names(item[key])
    ents = entities

    # 1. Decisive structured data.
    if "Recipe" in tops or (ents and ents.recipe):
        return "recipe"
    jobs = ents.jobs if ents else _items(structured, {"JobPosting"})
    if jobs:
        return "job" if len(jobs) == 1 else "listing"
    products = product_markup_count(structured)
    if products >= 3:  # one Product per card: a category / search page
        return "listing"
    if ({"Product", "ProductGroup"} & tops) and not (_LISTING_TYPES & tops):
        return "product"
    meta = {k.lower(): v for k, v in (structured.get("opengraph") or {}).items()}
    if str(meta.get("og:type", "")).lower() == "product" or "product:price:amount" in meta:
        return "product"
    events = ents.events if ents else _items(structured, {"Event"}, suffix="Event")
    if events:
        return "event" if len(events) == 1 else "listing"
    if "FAQPage" in tops:
        return "faq"
    if _ARTICLE_TYPES & tops:
        return "article"
    if _LISTING_TYPES & tops:
        return "listing"
    if {"ContactPage", "AboutPage"} & tops:
        return "organization"

    # 2. Page signals.
    if product is _UNSET or article is _UNSET:
        from omniscrape.parsers.semantic import SemanticExtractor

        semantic = SemanticExtractor(url=url, root=root)
        semantic._structured = structured
        product = semantic.extract_product() if product is _UNSET else product
        article = semantic.extract_article() if article is _UNSET else article
    from omniscrape.extract.listings import extract_listings

    links, prices = page_signals(root, url)
    cards = sum(1 for c in extract_listings(root, url) if c.get("url") and (c.get("price") or c.get("image")))
    if (links >= 20 and prices >= max(12, links // 2)) or cards >= 8:
        return "listing"
    words = len(article.body_text.split()) if article is not None else 0
    priced_product = product is not None and getattr(product, "price", None) is not None
    if priced_product and links <= 12 and prices <= 15 and not (article is not None and words >= 400 and prices <= 2):
        return "product"
    if article is not None:
        return "article"
    if links >= 20:
        return "listing"
    if priced_product:
        return "product"
    path = urlsplit(url).path.lower()
    if any(seg in path for seg in ("/search", "/category", "/categories", "/collections/", "/tag/", "/catalog")):
        return "listing"
    if ents and len(ents.faq) >= 3:
        return "faq"
    if (_ORG_TYPES & tops) or (any(seg in path for seg in ("/contact", "/about")) and ents and ents.organization):
        return "organization"
    return "other"
