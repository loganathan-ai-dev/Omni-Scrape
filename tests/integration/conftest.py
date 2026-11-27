"""Integration fixtures: the local benchmark test site, served in a subprocess."""

import pytest

from benchmarks.suites.crawl import SiteServer


@pytest.fixture
def site():
    server = SiteServer(pages=60, latency=(1.0, 3.0))
    server.get("/__reset")
    yield server
    server.stop()
