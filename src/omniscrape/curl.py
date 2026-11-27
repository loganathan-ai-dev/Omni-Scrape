"""Import ``curl`` commands (e.g. a browser's *Copy as cURL*) and replay them through OmniScrape.

    >>> from omniscrape import parse_curl, fetch_curl
    >>> parse_curl("curl 'https://api.example.com/items?page=2' -H 'Accept: application/json'")
    {'url': 'https://api.example.com/items?page=2', 'method': 'GET', 'headers': {'Accept': 'application/json'}, ...}
    >>> res = await fetch_curl(command)        # FetchResult, sent with the HTTP tier's browser TLS fingerprint

Supported: ``-X``, ``-H``, ``-b`` (cookie string), ``-d``/``--data*``, ``--data-urlencode``, ``--json``, ``-A``,
``-e``, ``-u``, ``-x``, ``-G``, ``-I``, ``-m``, ``-k``, ``--http1.1``/``--http2``/``--http3``, ``--url``, and the
bash and Windows ``cmd`` quoting styles that browsers produce. Flags that only affect curl's own output
(``-s``, ``-v``, ``-o``, ``--compressed``, ...) are accepted and ignored.
"""

import base64
import re
import shlex
from typing import Any, Optional
from urllib.parse import quote

from omniscrape.exceptions import ConfigError

_WITH_VALUE = {
    "-X": "method", "--request": "method",
    "-H": "header", "--header": "header",
    "-b": "cookie", "--cookie": "cookie",
    "-d": "data", "--data": "data", "--data-raw": "data", "--data-binary": "data", "--data-ascii": "data",
    "--data-urlencode": "data_urlencode",
    "--json": "json",
    "-A": "user_agent", "--user-agent": "user_agent",
    "-e": "referer", "--referer": "referer",
    "-u": "user", "--user": "user",
    "-x": "proxy", "--proxy": "proxy",
    "-m": "timeout", "--max-time": "timeout", "--connect-timeout": "ignore_value",
    "--url": "url",
    "-o": "ignore_value", "--output": "ignore_value", "-w": "ignore_value", "--write-out": "ignore_value",
    "-c": "ignore_value", "--cookie-jar": "ignore_value", "--retry": "ignore_value",
    "--resolve": "ignore_value", "--cacert": "ignore_value", "--cert": "ignore_value", "--key": "ignore_value",
    "--max-redirs": "ignore_value", "--limit-rate": "ignore_value", "--interface": "ignore_value",
    "-F": "form", "--form": "form",
}
_FLAGS = {
    "-G": "get", "--get": "get", "-I": "head", "--head": "head", "-k": "insecure", "--insecure": "insecure",
    "--http1.1": "http1", "--http1.0": "http1", "--http2": "http2", "--http2-prior-knowledge": "http2",
    "--http3": "http3", "--http3-only": "http3",
}
_IGNORED_FLAGS = {"-s", "--silent", "-S", "--show-error", "-v", "--verbose", "-L", "--location", "-i", "--include",
                  "--compressed", "-f", "--fail", "-N", "--no-buffer", "-g", "--globoff", "-#", "--progress-bar"}
_SHORT_WITH_VALUE = {"-X", "-H", "-b", "-d", "-A", "-e", "-u", "-x", "-m", "-o", "-w", "-c", "-F"}
_SHORT_FLAG_CHARS = set("sSLkIvGifNg#")


def _unwrap_cmd_style(command: str) -> str:
    """Convert Windows ``cmd`` quoting (``^"...^"``, ``^`` line continuations) to bash style."""
    if '^"' not in command:
        return command
    command = re.sub(r"\^\s*\r?\n", " ", command)
    command = command.replace('^\\^"', '\\"').replace('^"', '"')
    return re.sub(r"\^(.)", r"\1", command)


def _tokens(command: str) -> list[str]:
    command = _unwrap_cmd_style(command.strip())
    command = re.sub(r"\\\r?\n", " ", command)  # bash line continuations
    try:
        parts = shlex.split(command)
    except ValueError as exc:
        raise ConfigError(f"Could not parse curl command: {exc}") from exc
    if not parts or parts[0].lower() not in ("curl", "curl.exe"):
        raise ConfigError("Expected a command starting with 'curl'")
    out: list[str] = []
    for tok in parts[1:]:
        # Expand combined short flags (-sSL) and attached short values (-XPOST, -H'Accept: x').
        if re.fullmatch(r"-[A-Za-z#]{2,}", tok) and set(tok[1:]) <= _SHORT_FLAG_CHARS:
            out.extend(f"-{ch}" for ch in tok[1:])
        elif len(tok) > 2 and tok[:2] in _SHORT_WITH_VALUE and not tok.startswith("--"):
            out.extend([tok[:2], tok[2:]])
        else:
            out.append(tok)
    return out


def parse_curl(command: str) -> dict[str, Any]:
    """Parse a curl command into ``OmniClient.fetch`` keyword arguments plus ``url`` and ``insecure``.

    Returns ``{"url", "method", "headers", "cookies", "data", "proxy", "timeout", "http_version",
    "insecure"}`` (absent options are ``None`` / empty).
    """
    tokens = _tokens(command)
    url: Optional[str] = None
    method: Optional[str] = None
    headers: dict[str, str] = {}
    cookies: dict[str, str] = {}
    data_parts: list[str] = []
    json_body: Optional[str] = None
    proxy: Optional[str] = None
    timeout: Optional[float] = None
    http_version: Optional[str] = None
    flags: set[str] = set()

    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in _WITH_VALUE:
            if i + 1 >= len(tokens):
                raise ConfigError(f"curl option {tok} needs a value")
            kind, value = _WITH_VALUE[tok], tokens[i + 1]
            i += 2
            if kind == "method":
                method = value.upper()
            elif kind == "header":
                name, sep, val = value.partition(":")
                if sep and name.strip():
                    headers[name.strip()] = val.strip()
            elif kind == "cookie":
                if "=" in value:  # a cookie string; a bare value is a cookie *file*, which we skip
                    for pair in value.split(";"):
                        k, _, v = pair.strip().partition("=")
                        if k:
                            cookies[k] = v
            elif kind == "data":
                if value.startswith("@"):
                    raise ConfigError("curl -d @file is not supported; paste the body inline")
                data_parts.append(value)
            elif kind == "data_urlencode":
                name, sep, val = value.partition("=")
                data_parts.append(f"{name}={quote(val, safe='')}" if sep else quote(value, safe=""))
            elif kind == "json":
                json_body = value
            elif kind == "user_agent":
                headers["User-Agent"] = value
            elif kind == "referer":
                headers["Referer"] = value
            elif kind == "user":
                headers["Authorization"] = "Basic " + base64.b64encode(value.encode()).decode()
            elif kind == "proxy":
                proxy = value
            elif kind == "timeout":
                timeout = float(value)
            elif kind == "url":
                url = value
            elif kind == "form":
                raise ConfigError("curl -F (multipart upload) is not supported")
            continue
        if tok in _FLAGS:
            flags.add(_FLAGS[tok])
        elif tok in _IGNORED_FLAGS or (tok.startswith("-") and tok not in ("-",)):
            pass  # output/verbosity flags and unknown switches do not change the request
        elif url is None:
            url = tok
        i += 1

    if not url:
        raise ConfigError("No URL found in the curl command")
    if not url.startswith(("http://", "https://")):
        url = "http://" + url

    data: Optional[str] = "&".join(data_parts) if data_parts else None
    if "get" in flags and data:  # -G: send the -d values as the query string
        url = url + ("&" if "?" in url else "?") + data
        data = None
    if json_body is not None:
        headers.setdefault("Content-Type", "application/json")
        headers.setdefault("Accept", "application/json")
    elif data is not None and not any(h.lower() == "content-type" for h in headers):
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if method is None:
        method = "HEAD" if "head" in flags else ("POST" if (data is not None or json_body is not None) else "GET")
    if "http3" in flags:
        http_version = "3"
    elif "http2" in flags:
        http_version = "2"
    elif "http1" in flags:
        http_version = "1.1"

    return {
        "url": url, "method": method, "headers": headers, "cookies": cookies,
        "data": json_body if json_body is not None else data, "proxy": proxy, "timeout": timeout,
        "http_version": http_version, "insecure": "insecure" in flags,
    }


async def fetch_curl(command: str, **overrides: Any) -> Any:
    """Replay a curl command with OmniScrape's HTTP tier (browser TLS fingerprint, retries, proxies).

    ``overrides`` replace parsed values or add ``OmniClient.fetch`` options, e.g. ``tier=2`` or
    ``impersonate="safari"``. Returns a :class:`~omniscrape.models.FetchResult`.
    """
    from omniscrape.client import OmniClient

    req = parse_curl(command)
    insecure = req.pop("insecure")
    url = req.pop("url")
    timeout = req.pop("timeout") or 30.0
    proxy = req.pop("proxy")
    options = {k: v for k, v in req.items() if v not in (None, {}, "")}
    options.update(overrides)
    options.setdefault("tier", 1)
    fetcher_options: Optional[dict[Any, dict[str, Any]]] = {1: {"verify": False}} if insecure else None
    async with OmniClient(timeout=timeout, proxy=proxy, fetcher_options=fetcher_options) as client:
        return await client.fetch(url, **options)
