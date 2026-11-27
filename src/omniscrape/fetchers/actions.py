"""Browser page actions (Firecrawl-style action lists) and page-readiness helpers.

Actions are dicts::

    {"type": "click", "selector": "button.more"}
    {"type": "type", "selector": "input[name=q]", "text": "lamps"}      # alias: "write"
    {"type": "press", "key": "Enter"}
    {"type": "scroll", "direction": "down", "amount": 800}               # or {"type": "scroll", "to": "bottom"}
    {"type": "infinite_scroll", "max_scrolls": 10}
    {"type": "wait", "milliseconds": 500}                                # or {"type": "wait", "selector": ".x"}
    {"type": "evaluate", "script": "() => document.title"}               # alias: "execute_javascript"
    {"type": "screenshot", "full_page": true}
    {"type": "scrape"}                                                   # snapshot the HTML at this point
"""

from typing import Any, Optional
import asyncio
import json

SETTLE_JS = """
(args) => new Promise((resolve) => {
  let timer = null;
  const done = () => { obs.disconnect(); resolve(true); };
  const obs = new MutationObserver(() => { clearTimeout(timer); timer = setTimeout(done, args.quiet); });
  obs.observe(document, {subtree: true, childList: true, attributes: true, characterData: true});
  timer = setTimeout(done, args.quiet);
  setTimeout(done, args.max);
})
"""


async def settle(page: Any, quiet_ms: int = 150, max_ms: int = 3000) -> None:
    """Wait until the DOM has been quiet for ``quiet_ms`` (at most ``max_ms``)."""
    if quiet_ms <= 0:
        return
    try:
        await page.evaluate(SETTLE_JS, {"quiet": quiet_ms, "max": max_ms})
    except Exception:
        pass  # navigation during settle, closed page, CSP: readiness is best-effort


async def infinite_scroll(page: Any, max_scrolls: int = 10, pause_ms: int = 400) -> int:
    """Scroll to the bottom repeatedly until the page height stops growing. Returns scrolls done."""
    last = await page.evaluate("() => document.body ? document.body.scrollHeight : 0")
    for i in range(max_scrolls):
        await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(pause_ms)
        await settle(page, quiet_ms=150, max_ms=2000)
        height = await page.evaluate("() => document.body ? document.body.scrollHeight : 0")
        if height <= last:
            return i + 1
        last = height
    return max_scrolls


async def run_actions(page: Any, actions: list[dict[str, Any]], timeout_ms: int = 15000) -> dict[str, Any]:
    """Run actions in order. Returns {"log": [...], "screenshots": [bytes], "snapshots": [html], "results": [...]}."""
    out: dict[str, Any] = {"log": [], "screenshots": [], "snapshots": [], "results": []}
    for i, action in enumerate(actions):
        kind = (action.get("type") or "").lower()
        entry = {"index": i, "type": kind, "ok": True}
        try:
            if kind == "click":
                await page.click(action["selector"], timeout=timeout_ms)
                await settle(page)
            elif kind in ("type", "write", "fill"):
                if action.get("selector"):
                    await page.fill(action["selector"], action.get("text", ""), timeout=timeout_ms)
                else:
                    await page.keyboard.type(action.get("text", ""))
            elif kind == "press":
                await page.keyboard.press(action["key"])
                await settle(page)
            elif kind == "scroll":
                if action.get("to") == "bottom":
                    await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
                elif action.get("to") == "top":
                    await page.evaluate("() => window.scrollTo(0, 0)")
                else:
                    dy = int(action.get("amount", 800)) * (-1 if action.get("direction") == "up" else 1)
                    await page.mouse.wheel(0, dy)
                await settle(page)
            elif kind == "infinite_scroll":
                entry["scrolls"] = await infinite_scroll(page, int(action.get("max_scrolls", 10)),
                                                         int(action.get("pause_ms", 400)))
            elif kind == "wait":
                if action.get("selector"):
                    await page.wait_for_selector(action["selector"], timeout=int(action.get("timeout", timeout_ms)))
                else:
                    await page.wait_for_timeout(int(action.get("milliseconds", 500)))
            elif kind in ("evaluate", "execute_javascript", "js"):
                out["results"].append(await page.evaluate(action["script"]))
            elif kind == "screenshot":
                out["screenshots"].append(await page.screenshot(full_page=bool(action.get("full_page", True))))
            elif kind == "scrape":
                out["snapshots"].append(await page.content())
            else:
                raise ValueError(f"unknown action type '{kind}'")
        except Exception as exc:
            entry.update(ok=False, error=f"{type(exc).__name__}: {exc}"[:300])
            out["log"].append(entry)
            if not action.get("optional", False):
                break
            continue
        out["log"].append(entry)
    return out


async def _capture_json_response(response: Any, sink: list[dict[str, Any]]) -> None:
    """Keep JSON responses from XHR/fetch calls (API data behind SPAs)."""
    try:
        if response.request.resource_type not in ("xhr", "fetch"):
            return
        ctype = (await response.all_headers()).get("content-type", "")
        if "json" not in ctype:
            return
        body = await response.text()
        try:
            data: Any = json.loads(body)
        except ValueError:
            data = body[:20000]
        sink.append({"url": response.url, "status": response.status, "method": response.request.method, "json": data})
    except Exception:
        pass


async def run_playwright_fetch(
    context: Any,
    page: Any,
    url: str,
    *,
    timeout: float = 30.0,
    wait_until: str = "load",
    wait_for: Optional[str] = None,
    settle_ms: int = 40,
    max_settle_ms: int = 3000,
    actions: Optional[list[dict[str, Any]]] = None,
    screenshot: bool = False,
    full_page: bool = True,
    pdf: bool = False,
    headless: bool = True,
    capture_network: bool = False,
) -> dict[str, Any]:
    """Shared page navigation, readiness settle, action execution and artifact capture."""
    on_response = None
    captured: list[dict[str, Any]] = []
    if capture_network:
        def on_response(resp: Any) -> None:
            asyncio.ensure_future(_capture_json_response(resp, captured))

        page.on("response", on_response)

    ms = int(timeout * 1000)
    try:
        resp = await page.goto(url, timeout=ms, wait_until=wait_until)
        if wait_for:
            await page.wait_for_selector(wait_for, timeout=ms)
        await settle(page, settle_ms, max_settle_ms)
        action_out = await run_actions(page, actions, ms) if actions else {"log": [], "screenshots": [], "results": []}
        if screenshot or (pdf and headless):
            content = await page.content()
            shot = await page.screenshot(full_page=full_page) if screenshot else None
            if shot is None and action_out["screenshots"]:
                shot = action_out["screenshots"][-1]
            pdf_bytes = await page.pdf() if pdf and headless else None
            resp_headers = await resp.all_headers() if resp else {}
            raw_cookies = await context.cookies(page.url)
        else:
            if resp is not None:
                content, resp_headers, raw_cookies = await asyncio.gather(
                    page.content(), resp.all_headers(), context.cookies(page.url)
                )
            else:
                content, raw_cookies = await asyncio.gather(page.content(), context.cookies(page.url))
                resp_headers = {}
            shot = action_out["screenshots"][-1] if action_out["screenshots"] else None
            pdf_bytes = None
        return {
            "url": page.url,
            "status_code": resp.status if resp else 200,
            "headers": resp_headers,
            "html": content,
            "cookies": {c["name"]: c["value"] for c in raw_cookies},
            "screenshot": shot,
            "pdf": pdf_bytes,
            "network": captured,
            "actions_log": action_out["log"],
            "action_results": action_out["results"],
        }
    finally:
        if on_response is not None:
            try:
                page.remove_listener("response", on_response)
            except Exception:
                pass
