"""
Unit tests for title resolution, the pageviews client, and caching.

These mock the HTTP layer entirely, so they run offline -- no dependency
on live Wikimedia/Wikidata access. That matters here specifically because
the sandbox this was built in has no network route to those domains; this
is how the logic was verified before you run it for real. Once you have
normal internet access, do one live smoke test too (see SKILL.md).

Run:
    python -m pytest tests/ -v
"""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import requests

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from lib import wikidata, wikimedia_api, cache  # noqa: E402


def _mock_response(json_data, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(f"{status_code}")
    else:
        resp.raise_for_status = MagicMock()
    return resp


def test_resolve_titles_uses_sitelinks_and_flags_missing_language():
    pageprops_response = {
        "query": {"pages": {"123": {"pageprops": {"wikibase_item": "Q333"}}}}
    }
    sitelinks_response = {
        "entities": {
            "Q333": {
                "sitelinks": {
                    "enwiki": {"title": "Astronomy"},
                    "ukwiki": {"title": "Астрономія"},
                    # deliberately no "cswiki" entry: simulates "no article yet"
                }
            }
        }
    }
    with patch("lib.wikidata.requests.get") as mock_get:
        mock_get.side_effect = [
            _mock_response(pageprops_response),
            _mock_response(sitelinks_response),
        ]
        result = wikidata.resolve_titles("en", "Astronomy", ["uk", "cs"])

    assert result["en"] == "Astronomy"
    assert result["uk"] == "Астрономія"
    assert result["cs"] is None  # correctly surfaces "no article found"


def test_resolve_titles_falls_back_when_no_wikidata_item():
    pageprops_response = {"query": {"pages": {"1": {"missing": ""}}}}
    with patch("lib.wikidata.requests.get") as mock_get:
        mock_get.return_value = _mock_response(pageprops_response)
        result = wikidata.resolve_titles("en", "SomeMadeUpTitle", ["uk"])

    assert result["en"] == "SomeMadeUpTitle"
    assert result["uk"] is None


def test_fetch_pageviews_parses_items_into_date_view_pairs():
    api_response = {
        "items": [
            {"project": "en.wikipedia.org", "article": "Astronomy", "granularity": "monthly",
             "timestamp": "2025010100", "access": "all-access", "agent": "user", "views": 50000},
            {"project": "en.wikipedia.org", "article": "Astronomy", "granularity": "monthly",
             "timestamp": "2025020100", "access": "all-access", "agent": "user", "views": 52000},
        ]
    }
    with patch("lib.wikimedia_api.requests.get") as mock_get:
        mock_get.return_value = _mock_response(api_response)
        series = wikimedia_api.fetch_pageviews("en", "Astronomy", "20250101", "20250301")

    assert series == [
        {"date": "2025-01-01", "views": 50000},
        {"date": "2025-02-01", "views": 52000},
    ]


def test_fetch_pageviews_404_returns_empty_series_not_an_error():
    with patch("lib.wikimedia_api.requests.get") as mock_get:
        mock_get.return_value = _mock_response({}, status_code=404)
        series = wikimedia_api.fetch_pageviews("cs", "Nonexistent_Article", "20250101", "20250301")

    assert series == []


def test_slug_does_not_collapse_non_latin_titles():
    """Regression test: an earlier version stripped all non-ASCII characters,
    so any two Cyrillic titles (e.g. two different Ukrainian articles) both
    slugged to the same empty string and silently shared one cache file."""
    a = cache.slug("Астрономія")
    b = cache.slug("Фізика")
    assert a != b
    assert a != ""
    assert b != ""


def test_cache_roundtrip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = cache.cache_path("en", "Astronomy", "monthly", "20250101", "20250301")
    assert cache.load(path) is None
    cache.save(path, [{"date": "2025-01-01", "views": 1}])
    assert cache.load(path) == [{"date": "2025-01-01", "views": 1}]


def _month_aware_pageviews_router(pageprops_response, sitelinks_response):
    """
    A `requests.get` stand-in that returns distinct, realistic pageview
    data per month based on the requested chunk's start date -- unlike a
    single fixed response, this lets tests actually check that per-month
    chunking and merging works, instead of silently passing on duplicated
    data every mocked call happens to return.
    """
    def router(url, **kwargs):
        if "wikidata.org" in url:
            return _mock_response(sitelinks_response)
        if "wikipedia.org/w/api.php" in url:
            return _mock_response(pageprops_response)
        # Pageviews URL: .../{title}/{granularity}/{start}/{end}
        chunk_start = url.rstrip("/").split("/")[-2]  # "YYYYMMDD"
        views = 100 + int(chunk_start[4:6]) * 10  # varies deterministically by month
        return _mock_response({"items": [{"timestamp": chunk_start + "00", "views": views}]})
    return router


def test_build_dataset_end_to_end_with_mocks(tmp_path, monkeypatch):
    """Exercises fetch_views.build_dataset the way the CLI actually calls it,
    with both a resolvable and an unresolvable language.

    Note: wikidata.py and wikimedia_api.py both `import requests`, so they
    share the exact same `requests.get` attribute -- patching it in two
    separate `with patch(...)` blocks would make the second silently
    replace the first for the whole block (this bit us during development:
    the first version of this test used two separate patches and every
    title resolution came back None, because the pageviews mock had quietly
    taken over requests.get entirely). Routing one shared mock by URL avoids
    that trap.
    """
    monkeypatch.chdir(tmp_path)
    import fetch_views  # noqa: E402  (imported here so cwd patch applies to cache dir)

    pageprops_response = {"query": {"pages": {"1": {"pageprops": {"wikibase_item": "Q333"}}}}}
    sitelinks_response = {
        "entities": {"Q333": {"sitelinks": {
            "enwiki": {"title": "Astronomy"},
            "ukwiki": {"title": "Астрономія"},
        }}}
    }
    router = _month_aware_pageviews_router(pageprops_response, sitelinks_response)

    with patch("requests.get", side_effect=router):
        dataset = fetch_views.build_dataset(
            topic_title="Astronomy", source_lang="en", langs=["uk", "cs"],
            start="20250101", end="20250301", granularity="monthly",
            access="all-access", agent="user",
        )

    assert dataset["languages"]["en"]["resolved"] is True
    assert dataset["languages"]["uk"]["resolved"] is True
    # Jan/Feb/Mar 2025 -> three distinct monthly data points, in order.
    assert [row["views"] for row in dataset["languages"]["uk"]["series"]] == [110, 120, 130]
    assert dataset["languages"]["cs"]["resolved"] is False
    assert dataset["languages"]["cs"]["series"] == []


def test_fetch_series_with_cache_only_fetches_new_months(tmp_path, monkeypatch):
    """The actual point of the month-chunked cache: widening a date range
    should only trigger API calls for the newly-added month(s), not
    re-fetch months that were already cached -- which is what made the
    previous whole-range cache key ineffective for the common "ask again
    tomorrow" / "widen the range" cases."""
    monkeypatch.chdir(tmp_path)
    import fetch_views  # noqa: E402

    call_count = {"n": 0}

    def counting_router(url, **kwargs):
        call_count["n"] += 1
        chunk_start = url.rstrip("/").split("/")[-2]
        return _mock_response({"items": [{"timestamp": chunk_start + "00", "views": 42}]})

    with patch("lib.wikimedia_api.requests.get", side_effect=counting_router):
        fetch_views.fetch_series_with_cache(
            "en", "Astronomy", "20250101", "20250228", "monthly", "all-access", "user"
        )
        assert call_count["n"] == 2  # Jan, Feb

        # Widen by one month -- only March should trigger a new call.
        fetch_views.fetch_series_with_cache(
            "en", "Astronomy", "20250101", "20250331", "monthly", "all-access", "user"
        )
        assert call_count["n"] == 3  # +1 for March; Jan/Feb served from cache