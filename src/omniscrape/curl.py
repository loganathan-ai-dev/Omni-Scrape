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
    "--oauth2-bearer": "bearer",
    "-F": "form", "--form": "form",
    "-T": "unsupported", "--upload-file": "unsupported", "-K": "unsupported", "--config": "unsupported",
}
# Options that take a value but do not change the request we replay; their value must not be read as the URL.
for _opt in ("--retry-delay", "--retry-max-time", "-r", "--range", "--max-filesize", "--connect-to", "--dns-servers",
             "--local-port", "--proto", "--proto-redir", "--tls-max", "--ciphers", "--expect100-timeout",
             "--keepalive-time", "-z", "--time-cond", "-Y", "--speed-limit", "-y", "--speed-time", "-C",
             "--continue-at", "-D", "--dump-header", "--trace", "--trace-ascii", "--stderr", "--unix-socket",
             "--abstract-unix-socket", "--happy-eyeballs-timeout-ms", "--request-target", "--variable",
             "--proxy-user", "-U", "--noproxy", "--capath", "--crlfile", "--pinnedpubkey", "--cert-type",
             "--key-type", "--pass", "--socks5", "--socks4", "--socks4a", "--socks5-hostname", "--preproxy",
             "--doh-url", "--alt-svc", "--hsts", "--etag-save", "--etag-compare", "--output-dir", "-E"):
    _WITH_VALUE.setdefault(_opt, "ignore_value")
_FLAGS = {
    "-G": "get", "--get": "get", "-I": "head", "--head": "head", "-k": "insecure", "--insecure": "insecure",
    "--http1.1": "http1", "--http1.0": "http1", "--http2": "http2", "--http2-prior-knowledge": "http2",
    "--http3": "http3", "--http3-only": "http3",
}
_IGNORED_FLAGS = {"-s", "--silent", "-S", "--show-error", "-v", "--verbose", "-L", "--location", "-i", "--include",
                  "--compressed", "-f", "--fail", "-N", "--no-buffer", "-g", "--globoff", "-#", "--progress-bar"}
_SHORT_WITH_VALUE = {"-X", "-H", "-b", "-d", "-A", "-e", "-u", "-x", "-m", "-o", "-w", "-c", "-F", "-r", "-D",
                     "-E", "-T", "-K", "-C", "-z", "-y", "-Y", "-U"}
_SHORT_FLAG_CHARS = set("sSLkIvGifNg#")
_ANSI_C = re.compile(r"\$'((?:[^'\\]|\\.)*)'", re.S)
_SIMPLE_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", "'": "'", '"': '"', "a": "\a", "b": "\b",
                   "e": "\x1b", "E": "\x1b", "f": "\f", "v": "\v", "?": "?"}


def _decode_ansi_c(body: str) -> str:
    """Decode the inside of a bash ``$'...'`` string (browsers emit these for values with ``'``, ``!`` or
    control characters). ``\\xHH`` runs are UTF-8 bytes."""
    out: list[str] = []
    pending = bytearray()

    def flush() -> None:
        if pending:
            out.append(pending.decode("utf-8", errors="replace"))
            pending.clear()

    i = 0
    while i < len(body):
        ch = body[i]
        if ch != "\\" or i + 1 >= len(body):
            flush()
            out.append(ch)
            i += 1
            continue
        nxt = body[i + 1]
        if nxt == "x" and (m := re.match(r"[0-9a-fA-F]{1,2}", body[i + 2:])):
            pending.append(int(m.group(), 16))
            i += 2 + len(m.group())
            continue
        flush()
        width = 4 if nxt == "u" else 8
        if nxt in ("u", "U") and (m := re.match(rf"[0-9a-fA-F]{{1,{width}}}", body[i + 2:])):
            out.append(chr(int(m.group(), 16)))
            i += 2 + len(m.group())
        elif nxt in "01234567" and (m := re.match(r"[0-7]{1,3}", body[i + 1:])):
            out.append(chr(int(m.group(), 8)))
            i += 1 + len(m.group())
        elif nxt in _SIMPLE_ESCAPES:
            out.append(_SIMPLE_ESCAPES[nxt])
            i += 2
        else:
            out.append("\\" + nxt)
            i += 2
    flush()
    return "".join(out)


def _unwrap_ansi_c(command: str) -> str:
    """Replace every ``$'...'`` segment with an equivalent single-quoted string ``shlex`` understands."""
    return _ANSI_C.sub(lambda m: shlex.quote(_decode_ansi_c(m.group(1))), command)


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
    command = _unwrap_ansi_c(command)
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
        elif (re.fullmatch(r"-[A-Za-z#]{2,}", tok) and set(tok[1:-1]) <= _SHORT_FLAG_CHARS
              and f"-{tok[-1]}" in _SHORT_WITH_VALUE):
            # -sX POST, -sSLo out.html: flags followed by one option that takes the next token as its value
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
    positionals: list[str] = []

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
            elif kind == "bearer":
                headers["Authorization"] = f"Bearer {value}"
            elif kind == "unsupported":
                raise ConfigError(f"curl option {tok} (uploads / config files) is not supported")
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
        else:
            positionals.append(tok)
        i += 1

    if url is None and positionals:
        # The value of an option we do not know may land here too; prefer what looks like a URL.
        url = (next((t for t in positionals if "://" in t), None)
               or next((t for t in positionals if "." in t or t.startswith("localhost") or ":" in t), None)
               or positionals[0])
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


_SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


async def fetch_curl(command: str, **overrides: Any) -> Any:
    """Replay a curl command with OmniScrape's HTTP tier (browser TLS fingerprint, proxies).

    ``overrides`` replace parsed values or add ``OmniClient.fetch`` options, e.g. ``impersonate="safari"`` or
    ``tier=2`` (browser tiers can only replay GET requests without a body). GET/HEAD/OPTIONS are retried on
    transient errors; other methods are sent exactly once unless you pass ``retries=``, because replaying a
    form submission or API write twice can repeat its side effects. Returns a
    :class:`~omniscrape.models.FetchResult`.
    """
    from omniscrape.client import OmniClient
    from omniscrape.fetchers.registry import get_spec

    req = parse_curl(command)
    insecure = req.pop("insecure")
    url = req.pop("url")
    timeout = req.pop("timeout") or 30.0
    proxy = req.pop("proxy")
    options = {k: v for k, v in req.items() if v not in (None, {}, "")}
    retries = overrides.pop("retries", None)
    options.update(overrides)
    options.setdefault("tier", 1)
    method = str(options.get("method", "GET")).upper()
    if get_spec(options["tier"]).name not in ("http", "httpx") and (method not in ("GET", "HEAD")
                                                                    or options.get("data") is not None):
        raise ConfigError(f"Browser tiers only load pages with GET; replay this {method} request with tier=1")
    if retries is None:
        retries = 2 if method in _SAFE_METHODS else 0
    fetcher_options: Optional[dict[Any, dict[str, Any]]] = {1: {"verify": False}} if insecure else None
    async with OmniClient(timeout=timeout, proxy=proxy, retries=retries, fetcher_options=fetcher_options) as client:
        return await client.fetch(url, **options)
