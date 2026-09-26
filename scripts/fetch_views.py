#!/usr/bin/env python3
"""
Step 1 of the pipeline: resolve the correct article title per language,
then fetch pageviews for a topic across one or more language editions,
including project-wide baseline traffic for normalization (views per million),
using a local cache so repeat/related queries are cheap.

Usage:
    python scripts/fetch_views.py \
        --topic-title "Astronomy" --source-lang en \
        --langs uk,pl,cs --months 24
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import cache, wikidata, wikimedia_api  # noqa: E402


def _months_ago(months: int) -> str:
    today = datetime.now(timezone.utc)
    year, month = today.year, today.month - months
    while month <= 0:
        month += 12
        year -= 1
    return f"{year:04d}{month:02d}01"


def _default_end() -> str:
    """
    Returns the YYYYMMDD string for the last day of the previous calendar month.
    This prevents fetching incomplete data for the current month, which would create
    an artificial drop to zero at the end of trend line charts.
    """
    today = datetime.now(timezone.utc)
    first_of_this_month = today.replace(day=1)
    last_day_prev_month = first_of_this_month - timedelta(days=1)
    return last_day_prev_month.strftime("%Y%m%d")


def fetch_series_with_cache(
    lang: str, title: str, start: str, end: str,
    granularity: str, access: str, agent: str,
) -> list:
    """
    Fetches [start, end] for one (language, title) pair, one calendar
    month at a time, reusing whatever months are already cached.
    """
    combined: list = []
    for chunk_start, chunk_end in cache.month_chunks(start, end):
        c_path = cache.cache_path(lang, title, granularity, chunk_start, chunk_end)
        month_series = cache.load(c_path)
        if month_series is None:
            # Fallback for API method name compatibility
            fetch_fn = getattr(wikimedia_api, "fetch_pageviews", None) or getattr(wikimedia_api, "fetch_monthly_pageviews", None)
            if fetch_fn is None:
                raise AttributeError("wikimedia_api module has no fetch_pageviews or fetch_monthly_pageviews function")

            # Check if function supports granular flags or simple range
            try:
                month_series = fetch_fn(
                    lang, title, chunk_start, chunk_end,
                    granularity=granularity, access=access, agent=agent,
                )
            except TypeError:
                month_series = fetch_fn(title, lang, chunk_start, chunk_end)

            cache.save(c_path, month_series)
        combined.extend(month_series)

    combined.sort(key=lambda row: row["date"])
    if granularity == "daily":
        combined = [row for row in combined if start <= row["date"].replace("-", "") <= end]
    return combined


def fetch_project_totals_map(lang: str, start: str, end: str) -> dict[str, int]:
    """
    Fetches project-wide total monthly pageviews for normalizing traffic.
    Returns a dict of 'YYYY-MM-01' -> total_views.
    """
    fetch_proj_fn = getattr(wikimedia_api, "fetch_project_aggregate_views", None)
    if not fetch_proj_fn:
        return {}
    return fetch_proj_fn(lang, start, end)


def _default_out_path(topic: str, langs: list) -> Path:
    lang_part = "-".join(sorted(langs))
    return Path("output") / f"{cache.slug(topic)}__{lang_part}" / "raw_views.json"


def build_dataset(
    topic_title: str,
    source_lang: str,
    langs: list,
    start: str,
    end: str,
    granularity: str,
    access: str,
    agent: str,
) -> dict:
    """Pure function: resolves titles, fetches & normalizes pageview series."""
    resolved = wikidata.resolve_titles(source_lang, topic_title, langs)

    languages_out = {}
    for lang in sorted(set(langs) | {source_lang}):
        title = resolved.get(lang)
        if not title:
            languages_out[lang] = {
                "project": f"{lang}.wikipedia.org",
                "resolved_title": None,
                "resolved": False,
                "series": [],
            }
            continue

        raw_series = fetch_series_with_cache(lang, title, start, end, granularity, access, agent)
        project_totals = fetch_project_totals_map(lang, start, end)

        # Filter out trailing partial/incomplete months where pageview metrics return 0
        raw_series = [row for row in raw_series if row.get("views", 0) > 0]

        # Enrich series with normalized metrics (views_per_million)
        normalized_series = []
        for row in raw_series:
            d = row["date"]
            v = row.get("views", 0)
            proj_total = project_totals.get(d, 0)

            vpm = round((v / proj_total * 1_000_000), 2) if proj_total > 0 else 0.0

            normalized_series.append({
                "date": d,
                "views": v,
                "project_total_views": proj_total,
                "views_per_million": vpm,
            })

        languages_out[lang] = {
            "project": f"{lang}.wikipedia.org",
            "resolved_title": title,
            "resolved": True,
            "series": normalized_series,
        }

    return {
        "topic": topic_title,
        "source_lang": source_lang,
        "granularity": granularity,
        "start": start,
        "end": end,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "languages": languages_out,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Wikipedia pageviews for a topic across languages.")
    parser.add_argument("--topic-title", required=True, help="Article title in the source language.")
    parser.add_argument("--source-lang", default="en")
    parser.add_argument("--langs", required=True, help="Comma-separated language codes, e.g. uk,pl,cs")
    parser.add_argument("--months", type=int, default=12)
    parser.add_argument("--start", help="Override start date, YYYYMMDD")
    parser.add_argument("--end", help="Override end date, YYYYMMDD")
    parser.add_argument("--granularity", default="monthly", choices=["monthly", "daily"])
    parser.add_argument("--access", default="all-access")
    parser.add_argument("--agent", default="user")
    parser.add_argument("--out", help="Output path for the merged JSON.")
    args = parser.parse_args()

    langs = [l.strip() for l in args.langs.split(",") if l.strip()]
    start = args.start or _months_ago(args.months)
    end = args.end or _default_end()

    result = build_dataset(
        args.topic_title, args.source_lang, langs, start, end,
        args.granularity, args.access, args.agent,
    )

    out_path = Path(args.out) if args.out else _default_out_path(args.topic_title, langs)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()