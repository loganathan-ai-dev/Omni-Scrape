"""Repository-consistency checks: skills in sync, manifests valid, README numbers match published data.

These read files outside ``src/``, so they only run from a git checkout (the sdist ships no tests).
"""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PUBLISHED = ROOT / "benchmarks" / "published" / "2026-11-27"
README = ROOT / "README.md"

pytestmark = pytest.mark.skipif(not (ROOT / "pyproject.toml").exists(), reason="needs a git checkout")


def _load(name: str) -> dict:
    return json.loads((PUBLISHED / f"{name}.json").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ skills
def test_claude_skill_is_an_exact_copy_of_the_agents_skill():
    spec = importlib.util.spec_from_file_location("sync_skills", ROOT / "scripts" / "sync_skills.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for target in module.TARGETS:
        assert module.differences(module.SOURCE, target) == [], "run: python scripts/sync_skills.py"


def test_skill_frontmatter_is_valid():
    text = (ROOT / ".agents/skills/omniscrape/SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\nname: omniscrape\ndescription: ")


def test_skill_uses_current_action_keys_and_pypi_name():
    cheat = (ROOT / ".agents/skills/omniscrape/references/api_cheatsheet.md").read_text(encoding="utf-8")
    assert '"milliseconds"' in cheat and '"ms"' not in cheat
    for md in ROOT.glob(".agents/**/*.md"):
        assert "omniscrape[" not in md.read_text(encoding="utf-8"), f"{md}: use omni-scraper[extra]"


# ------------------------------------------------------------------ manifests
@pytest.mark.parametrize("path", [".claude-plugin/plugin.json", ".claude-plugin/marketplace.json", ".mcp.json"])
def test_json_manifests_parse(path):
    file = ROOT / path
    if not file.exists():
        pytest.skip(f"{path} not present")
    assert isinstance(json.loads(file.read_text(encoding="utf-8")), dict)


def test_plugin_manifest_matches_package_version():
    manifest = ROOT / ".claude-plugin" / "plugin.json"
    if not manifest.exists():
        pytest.skip("no plugin manifest")
    from omniscrape import __version__

    assert json.loads(manifest.read_text(encoding="utf-8"))["version"] == __version__


# ------------------------------------------------------------------ packaging metadata
def test_distribution_name_and_single_version_source():
    import tomllib

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["name"] == "omni-scraper"
    assert "version" in project["dynamic"] and "version" not in project
    assert project["license"] == "MIT"
    assert not {"orjson", "beautifulsoup4"} & {d.split(">")[0] for d in project["dependencies"]}
    assert (ROOT / "src/omniscrape/py.typed").exists()


# ------------------------------------------------------------------ README <-> published benchmark data
def test_readme_benchmark_numbers_match_published_json():
    readme = README.read_text(encoding="utf-8")
    adaptive, parse, crawl = _load("adaptive"), _load("parse"), _load("crawl")
    render, markdown, extract = _load("render"), _load("markdown"), _load("extract")
    live = _load("live")

    omni, scrapling = adaptive["tools"]["omniscrape"], adaptive["tools"]["scrapling"]
    assert omni["groups"]["all"]["recovered"] == omni["groups"]["all"]["n"] == 1377
    assert f"{scrapling['groups']['all']['recovery_rate'] * 100:.1f}%" in readme  # 85.3%
    assert str(scrapling["groups"]["all"]["wrong"]) in readme  # 202
    assert f"{omni['ms_per_page_variant']:.1f}" in readme and f"{scrapling['ms_per_page_variant']:.1f}" in readme

    for tool in ("omniscrape", "scrapling"):
        assert f"{parse['tools'][tool]['docs_per_sec']:.1f}" in readme
        assert f"{crawl['tools'][tool]['pages_per_sec']:.1f}" in readme
        assert f"{adaptive['tools'][tool]['rss_after_import_mb']:.1f}" in readme
    assert f"{render['tools']['omniscrape-isolated']['pages_per_sec']:.2f}" in readme
    assert f"{render['tools']['omniscrape']['pages_per_sec']:.2f}" in readme
    assert f"{render['tools']['scrapling']['pages_per_sec']:.2f}" in readme

    for target in ("books", "quotes"):
        for tool in ("omniscrape", "scrapling"):
            assert f"{live['tools'][tool]['targets'][target]['pages_per_sec']:.2f}" in readme

    for tool in ("omniscrape", "trafilatura"):
        assert f"{markdown['tools'][tool]['groups']['all']['f1']:.4f}" in readme
        assert f"{markdown['tools'][tool]['groups']['holdout']['f1']:.4f}" in readme
        assert f"{extract['tools'][tool]['groups']['all:article']['f1']:.4f}" in readme
    assert f"{extract['tools']['omniscrape']['groups']['all:product']['f1']:.3f}" in readme
    assert f"{markdown['tools']['omniscrape']['groups']['all']['leakage'] * 100:.2f}%" in readme
    assert f"{markdown['tools']['trafilatura']['groups']['all']['leakage'] * 100:.2f}%" in readme


def test_readme_has_no_stale_install_instructions():
    readme = README.read_text(encoding="utf-8")
    assert "git+https" not in readme
    assert "pip install omniscrape" not in readme
    assert 'omniscrape[' not in readme
    # PyPI rejected "omni-scrape" as too similar to the existing "omniscrape"; the name is "omni-scraper".
    import re

    assert re.search(r"omni-scrape(?!r)", readme) is None
