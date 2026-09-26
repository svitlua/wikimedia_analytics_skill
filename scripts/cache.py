"""
Flat-JSON cache so repeat/related queries (a wider date range, one more
language) don't re-fetch data we already have.

Each entry is keyed by the exact API call it represents (language, title,
granularity, date range), so a follow-up question that only adds a new
language, or extends the date range, only triggers new API calls for the
pieces that are actually missing -- everything else is read from disk.
"""
from __future__ import annotations

import calendar
import hashlib
import json
import re
from pathlib import Path
from typing import Iterator, Optional, Tuple

CACHE_DIR = Path(".cache/pageviews")


def month_chunks(start: str, end: str) -> Iterator[Tuple[str, str]]:
    """
    Yield (chunk_start, chunk_end) YYYYMMDD pairs, one per whole calendar
    month, covering every month that overlaps [start, end].

    Chunks are always whole months -- even if the caller's start/end cuts
    into the middle of a month -- so that a cached chunk is fully reusable
    by ANY future query that touches that month, regardless of the exact
    day boundaries that query happens to ask for. Without this, asking
    "last 24 months" twice on two different days would produce two
    different [start, end] strings and miss the cache entirely, even
    though 23 of those 24 months hadn't changed.
    """
    y, m = int(start[:4]), int(start[4:6])
    end_y, end_m = int(end[:4]), int(end[4:6])
    while (y, m) <= (end_y, end_m):
        last_day = calendar.monthrange(y, m)[1]
        yield f"{y:04d}{m:02d}01", f"{y:04d}{m:02d}{last_day:02d}"
        m += 1
        if m > 12:
            m = 1
            y += 1


def slug(text: str) -> str:
    """
    ASCII-safe, collision-resistant identifier for use in filenames.

    Article titles are frequently non-Latin (e.g. Ukrainian "Астрономія"),
    so a naive "strip anything non-ASCII" approach collapses every such
    title down to the same empty string -- which silently merges unrelated
    cache entries. We keep a readable ASCII prefix when there is one, but
    always append a short hash of the *original* text so distinct titles
    in any script never collide.
    """
    text = text.strip()
    ascii_part = re.sub(r"[^a-z0-9_.-]", "", text.lower().replace(" ", "_"))
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    return f"{ascii_part}-{digest}" if ascii_part else digest


def cache_path(lang: str, title: str, granularity: str, start: str, end: str) -> Path:
    key = f"{lang}__{slug(title)}__{granularity}__{start}-{end}.json"
    return CACHE_DIR / key


def load(path: Path) -> Optional[list]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def save(path: Path, series: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(series, ensure_ascii=False, indent=2), encoding="utf-8")