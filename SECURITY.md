# Security policy

## Supported versions

Only the latest released minor version receives security fixes.

| Version | Supported |
|---|---|
| 0.1.x | yes |

## Reporting a vulnerability

Please **do not** open a public issue for security problems.

Use GitHub's private reporting: **Security → Report a vulnerability** on
<https://github.com/loganathan-ai-dev/Omni-Scrape/security/advisories/new>.
Include the version, a minimal reproduction and the impact you see. You can expect an acknowledgement within
a few days and a fix or mitigation plan after triage.

## Scope

In scope: the `omni-scraper` package and its CLI and MCP server, for example SSRF through the MCP tools,
unsafe deserialisation, path handling in storage backends, or credential leakage in logs.

Out of scope: behaviour of sites you scrape, and misuse of the library against sites that forbid it.

## Using OmniScrape responsibly

The library detects anti-bot systems but does not solve CAPTCHAs or interactive challenges. The stealth tier
is opt-in. The `omniscrape mcp` server fetches whatever URL an agent asks for: run it only where that is
acceptable, and do not expose `--transport http` to untrusted networks without authentication in front of it.
