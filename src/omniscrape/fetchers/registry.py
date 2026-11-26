"""Fetcher registry: maps names, aliases and tier numbers to fetcher classes.

Built-in engines are registered lazily, so importing the registry never imports Playwright or
Camoufox. Third-party engines plug in with ``register_fetcher``::

    from omniscrape.fetchers.registry import register_fetcher
    register_fetcher("my-api", MyApiFetcher, aliases=["myapi"])
"""

from dataclasses import dataclass, field
from importlib import import_module
from threading import Lock
from typing import Any, Callable, Optional, Union

from omniscrape.exceptions import ConfigError
from omniscrape.fetchers.base import BaseFetcher

FetcherFactory = Callable[..., BaseFetcher]


@dataclass
class FetcherSpec:
    name: str
    factory: Union[FetcherFactory, str]  # a class/callable or a lazy "module:attr" path
    tier: Optional[int] = None
    aliases: list[str] = field(default_factory=list)
    description: str = ""

    def resolve(self) -> FetcherFactory:
        if isinstance(self.factory, str):
            module_name, attr = self.factory.split(":")
            self.factory = getattr(import_module(module_name), attr)
        return self.factory


_lock = Lock()
_specs: dict[str, FetcherSpec] = {}
_aliases: dict[str, str] = {}
_tiers: dict[int, str] = {}


def register_fetcher(
    name: str,
    factory: Union[FetcherFactory, str],
    *,
    tier: Optional[int] = None,
    aliases: Optional[list[str]] = None,
    description: str = "",
    override: bool = False,
) -> FetcherSpec:
    """Register a fetcher under ``name`` (plus optional aliases and escalation tier)."""
    key = name.lower()
    spec = FetcherSpec(name=key, factory=factory, tier=tier, aliases=list(aliases or []), description=description)
    with _lock:
        if key in _specs and not override:
            raise ConfigError(f"Fetcher '{name}' is already registered (pass override=True to replace it)")
        _specs[key] = spec
        for alias in spec.aliases:
            _aliases[alias.lower()] = key
        if tier is not None:
            _tiers[tier] = key
    return spec


def get_spec(name_or_tier: Union[str, int]) -> FetcherSpec:
    with _lock:
        if isinstance(name_or_tier, int) or (isinstance(name_or_tier, str) and name_or_tier.isdigit()):
            tier = int(name_or_tier)
            if tier not in _tiers:
                raise ConfigError(f"No fetcher registered for tier {tier}. Known tiers: {sorted(_tiers)}")
            return _specs[_tiers[tier]]
        key = name_or_tier.lower()
        key = _aliases.get(key, key)
        if key not in _specs:
            raise ConfigError(f"Unknown fetcher '{name_or_tier}'. Available: {sorted(_specs)}")
        return _specs[key]


def create_fetcher(name_or_tier: Union[str, int], **options: Any) -> BaseFetcher:
    """Instantiate a registered fetcher with the given constructor options."""
    return get_spec(name_or_tier).resolve()(**options)


def tier_of(name_or_tier: Union[str, int]) -> Optional[int]:
    return get_spec(name_or_tier).tier


def available_fetchers() -> list[FetcherSpec]:
    with _lock:
        return list(_specs.values())


def _register_builtins() -> None:
    register_fetcher(
        "http", "omniscrape.fetchers.http:FastFetcher", tier=1,
        aliases=["fast", "fastfetcher", "curl"],
        description="curl_cffi HTTP/2 client with browser TLS impersonation",
    )
    register_fetcher(
        "browser", "omniscrape.fetchers.browser:DynamicFetcher", tier=2,
        aliases=["dynamic", "dynamicfetcher", "playwright"],
        description="Playwright Chromium for JavaScript-rendered pages",
    )
    register_fetcher(
        "stealth", "omniscrape.fetchers.stealth:StealthFetcher", tier=3,
        aliases=["stealthfetcher", "camoufox"],
        description="Camoufox / hardened Playwright (opt-in escalation only)",
    )
    register_fetcher(
        "httpx", "omniscrape.fetchers.httpx_fetcher:HttpxFetcher",
        aliases=["h2"],
        description="httpx client with HTTP/2 (optional 'httpx' dependency)",
    )


_register_builtins()
