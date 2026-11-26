"""Deterministic local test site for crawl benchmarks (aiohttp).

    python -m benchmarks.site.server --port 8765 --pages 300

Features: link graph of N pages + categories, robots.txt disallowing /private/, sitemap.xml,
flaky pages (HTTP 500 on the first request, 200 afterwards), JS-rendered pages (/js/{i}),
configurable per-request latency, and server-side ground truth via /__stats and /__meta.
"""

import argparse
import asyncio
import random
from collections import Counter, deque
from typing import Optional

from aiohttp import web

PRIVATE_COUNT = 20
FLAKY_COUNT = 10
CATEGORY_COUNT = 10
WORDS = ("orbit lantern meadow copper harbor signal ember quartz willow summit cedar falcon river "
         "garden velvet prism canyon violet nectar thistle beacon").split()


class Site:
    def __init__(self, n_pages: int = 300, seed: int = 7, latency_ms: tuple[float, float] = (5.0, 25.0)):
        self.n = n_pages
        self.latency_ms = latency_ms
        rng = random.Random(seed)
        self.rng = random.Random(seed + 1)
        self.links: dict[str, list[str]] = {}
        self.text: dict[str, str] = {}
        for i in range(n_pages):
            targets = {(i + 1) % n_pages, (i * 2) % n_pages, (i * 7 + 3) % n_pages}
            targets |= {rng.randrange(n_pages) for _ in range(4)}
            links = [f"/page/{t}" for t in sorted(targets) if t != i]
            links.append(f"/c/{i % CATEGORY_COUNT}")
            if i % 15 == 0:
                links.append(f"/private/{(i // 15) % PRIVATE_COUNT}")
            if i % 30 == 5:
                links.append(f"/flaky/{(i // 30) % FLAKY_COUNT}")
            links.append(f"/page/{i}#section")  # fragment duplicate of self
            self.links[f"/page/{i}"] = links
            self.text[f"/page/{i}"] = " ".join(rng.choice(WORDS) for _ in range(rng.randint(150, 600)))
        for k in range(CATEGORY_COUNT):
            self.links[f"/c/{k}"] = [f"/page/{j}" for j in range(k, n_pages, CATEGORY_COUNT)][:40]
        for k in range(FLAKY_COUNT):
            self.links[f"/flaky/{k}"] = [f"/page/{(k * 37) % n_pages}"]
        for k in range(PRIVATE_COUNT):
            self.links[f"/private/{k}"] = [f"/page/{(k * 11) % n_pages}"]
        self.links["/"] = [f"/c/{k}" for k in range(CATEGORY_COUNT)] + ["/page/0"]
        self.expected = self._reachable_allowed()
        self.reset()

    def _reachable_allowed(self) -> list[str]:
        seen, queue = {"/"}, deque(["/"])
        while queue:
            path = queue.popleft()
            for link in self.links.get(path, []):
                link = link.split("#")[0]
                if link.startswith("/private/") or link in seen:
                    continue
                seen.add(link)
                queue.append(link)
        return sorted(seen)

    def reset(self) -> None:
        self.hits: Counter[str] = Counter()
        self.flaky_served: set[str] = set()

    def page_html(self, path: str, title: str) -> str:
        links = "".join(f'<li><a href="{href}">{href}</a></li>' for href in self.links.get(path, []))
        body = self.text.get(path, "")
        paras = "".join(f"<p>{body[i:i + 400]}</p>" for i in range(0, len(body), 400))
        return (f"<!DOCTYPE html><html><head><title>{title}</title></head><body>"
                f'<nav><a href="/">Home</a> <a href="/sitemap.xml">Sitemap</a></nav>'
                f"<h1>{title}</h1>{paras}<ul>{links}</ul></body></html>")

    def stats(self) -> dict:
        content = {p: c for p, c in self.hits.items() if p not in ("/robots.txt", "/sitemap.xml", "/favicon.ico")}
        allowed = {p for p in content if not p.startswith("/private/")}
        expected = set(self.expected)
        flaky_seen = {p for p in content if p.startswith("/flaky/")}
        flaky_recovered = {p for p in flaky_seen if content[p] >= 2}
        extra_flaky_requests = sum(1 for p in flaky_recovered)
        duplicates = sum(c - 1 for p, c in content.items() if c > 1) - extra_flaky_requests
        return {
            "total_requests": sum(self.hits.values()),
            "unique_allowed_fetched": len(allowed & expected),
            "expected_allowed": len(expected),
            "coverage": round(len(allowed & expected) / len(expected), 4),
            "robots_violations": len([p for p in content if p.startswith("/private/")]),
            "duplicate_requests": max(0, duplicates),
            "robots_txt_requested": self.hits.get("/robots.txt", 0) > 0,
            "flaky_seen": len(flaky_seen),
            "flaky_recovered": len(flaky_recovered),
        }


def build_app(site: Site) -> web.Application:
    async def delay() -> None:
        lo, hi = site.latency_ms
        if hi > 0:
            await asyncio.sleep(site.rng.uniform(lo, hi) / 1000)

    @web.middleware
    async def track(request: web.Request, handler):
        if not request.path.startswith("/__"):
            site.hits[request.path] += 1
            await delay()
        return await handler(request)

    async def home(_: web.Request) -> web.Response:
        return web.Response(text=site.page_html("/", "Home"), content_type="text/html")

    async def page(request: web.Request) -> web.Response:
        path = request.path
        if path not in site.links:
            raise web.HTTPNotFound()
        return web.Response(text=site.page_html(path, path.strip("/").replace("/", " ").title()), content_type="text/html")

    async def flaky(request: web.Request) -> web.Response:
        path = request.path
        if path not in site.flaky_served:
            site.flaky_served.add(path)
            return web.Response(status=500, text="temporary failure")
        return await page(request)

    async def js_page(request: web.Request) -> web.Response:
        i = request.match_info["i"]
        html = (f"<!DOCTYPE html><html><head><title>JS {i}</title></head><body><div id=\"root\"></div>"
                f"<script>document.getElementById('root').innerHTML='<h1>Rendered {i}</h1><p class=\"msg\">"
                f"Hydrated content for page {i}</p><ul>' + [1,2,3].map(n => '<li class=\"item\">Item '+n+'</li>').join('') + '</ul>';"
                f"</script></body></html>")
        return web.Response(text=html, content_type="text/html")

    async def interactive(_: web.Request) -> web.Response:
        html = ("<!DOCTYPE html><html><head><title>Interactive</title></head><body><h1>Offers</h1>"
                "<button id='more' onclick=\"document.getElementById('hidden').innerHTML="
                "'<p class=\\'deal\\'>Secret deal unlocked</p>'\">Show deals</button><div id='hidden'></div>"
                "<input id='q' name='q'><button id='go' onclick=\"document.getElementById('out').textContent="
                "'You searched: ' + document.getElementById('q').value\">Go</button><p id='out'></p></body></html>")
        return web.Response(text=html, content_type="text/html")

    async def infinite(_: web.Request) -> web.Response:
        html = ("<!DOCTYPE html><html><head><title>Feed</title><style>.item{height:400px}</style></head><body>"
                "<div id='feed'></div><script>let n=0;function more(){if(n>=50)return;for(let i=0;i<10;i++){"
                "const d=document.createElement('div');d.className='item';d.textContent='Item '+(++n);"
                "document.getElementById('feed').appendChild(d);}}more();"
                "window.addEventListener('scroll',()=>{if(window.innerHeight+window.scrollY>=document.body.offsetHeight-50)"
                "setTimeout(more,100);});</script></body></html>")
        return web.Response(text=html, content_type="text/html")

    async def spa(_: web.Request) -> web.Response:
        html = ("<!DOCTYPE html><html><head><title>Catalog</title></head><body><div id='app'>Loading</div><script>"
                "fetch('/api/items').then(r=>r.json()).then(d=>{document.getElementById('app').innerHTML="
                "d.items.map(i=>'<div class=\"product\"><h2>'+i.name+'</h2><span class=\"price\">$'+i.price+'</span></div>').join('');});"
                "</script></body></html>")
        return web.Response(text=html, content_type="text/html")

    async def api_items(_: web.Request) -> web.Response:
        await asyncio.sleep(0.05)
        return web.json_response({"items": [{"name": f"Lamp {i}", "price": 10 + i} for i in range(5)]})

    async def robots(_: web.Request) -> web.Response:
        return web.Response(text="User-agent: *\nDisallow: /private/\n\nSitemap: /sitemap.xml\n")

    async def sitemap(request: web.Request) -> web.Response:
        base = f"{request.scheme}://{request.host}"
        urls = "".join(f"<url><loc>{base}{p}</loc></url>" for p in site.expected)
        return web.Response(text=f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>',
                            content_type="application/xml")

    async def stats(_: web.Request) -> web.Response:
        return web.json_response(site.stats())

    async def reset(_: web.Request) -> web.Response:
        site.reset()
        return web.json_response({"ok": True})

    async def meta(_: web.Request) -> web.Response:
        return web.json_response({"expected_allowed": len(site.expected), "pages": site.n})

    app = web.Application(middlewares=[track])
    app.router.add_get("/", home)
    app.router.add_get("/page/{i}", page)
    app.router.add_get("/c/{k}", page)
    app.router.add_get("/private/{k}", page)
    app.router.add_get("/flaky/{k}", flaky)
    app.router.add_get("/js/{i}", js_page)
    app.router.add_get("/interactive", interactive)
    app.router.add_get("/infinite", infinite)
    app.router.add_get("/spa", spa)
    app.router.add_get("/api/items", api_items)
    app.router.add_get("/robots.txt", robots)
    app.router.add_get("/sitemap.xml", sitemap)
    app.router.add_get("/__stats", stats)
    app.router.add_post("/__reset", reset)
    app.router.add_get("/__reset", reset)
    app.router.add_get("/__meta", meta)
    return app


def main(argv: Optional[list[str]] = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--pages", type=int, default=300)
    ap.add_argument("--latency-min", type=float, default=5.0)
    ap.add_argument("--latency-max", type=float, default=25.0)
    args = ap.parse_args(argv)
    site = Site(args.pages, latency_ms=(args.latency_min, args.latency_max))
    web.run_app(build_app(site), host="127.0.0.1", port=args.port, print=None, access_log=None)


if __name__ == "__main__":
    main()
