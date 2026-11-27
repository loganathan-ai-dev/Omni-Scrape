"""URL canonicalization and request fingerprints for deduplication."""

import hashlib
import re
from functools import lru_cache
from typing import Optional
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

TRACKING_PARAMS = re.compile(
    r"^(utm_[a-z]+|gclid|dclid|fbclid|msclkid|mc_cid|mc_eid|_ga|_gl|yclid|igshid|ref_src|spm|"
    r"__hstc|__hssc|__hsfp|hsCtaTracking|oly_enc_id|oly_anon_id|vero_id|wickedid|s_kwcid)$",
    re.IGNORECASE,
)
DEFAULT_PORTS = {"http": 80, "https": 443}
NON_HTML_EXT = re.compile(
    r"\.(jpe?g|png|gif|webp|avif|svg|ico|bmp|tiff?|mp[34]|m4[av]|webm|mov|avi|mkv|wav|ogg|flac|zip|rar|7z|"
    r"gz|tgz|bz2|xz|tar|exe|msi|dmg|apk|iso|bin|woff2?|ttf|otf|eot|css|js|map)$",
    re.IGNORECASE,
)


@lru_cache(maxsize=65536)  # the same links repeat on every page of a site
def canonicalize(url: str, keep_fragment: bool = False, strip_trailing_slash: bool = True) -> str:
    """Normalize a URL so equivalent addresses compare equal.

    Lower-cases scheme/host, drops default ports, fragments and tracking parameters, sorts the
    query, normalizes percent-encoding and (by default) removes a trailing slash from paths.
    """
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower().rstrip(".")
    port = parts.port
    netloc = host if port is None or DEFAULT_PORTS.get(scheme) == port else f"{host}:{port}"
    if parts.username:
        netloc = f"{parts.username}{':' + parts.password if parts.password else ''}@{netloc}"
    raw_path = parts.path or "/"
    path = quote(unquote(raw_path), safe="/:@!$&'()*+,;=-._~%") if ("%" in raw_path or not raw_path.isascii()) else raw_path
    if "//" in path:
        path = re.sub(r"/{2,}", "/", path)
    if strip_trailing_slash and len(path) > 1:
        path = path.rstrip("/")
    if parts.query:
        query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not TRACKING_PARAMS.match(k)]
        query.sort()
        qs = urlencode(query, doseq=True)
    else:
        qs = ""
    return urlunsplit((scheme, netloc, path, qs, parts.fragment if keep_fragment else ""))


def fingerprint(url: str, method: str = "GET", body: Optional[bytes] = None) -> str:
    h = hashlib.sha1()
    h.update(method.upper().encode())
    h.update(canonicalize(url).encode())
    if body:
        h.update(body if isinstance(body, bytes) else str(body).encode())
    return h.hexdigest()


def registered_host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def origin(url: str) -> str:
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}"


def looks_like_page(url: str) -> bool:
    """False for obvious binary/static assets (images, archives, media, fonts, scripts)."""
    return not NON_HTML_EXT.search(urlsplit(url).path)
