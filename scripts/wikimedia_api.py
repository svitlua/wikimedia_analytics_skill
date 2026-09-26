"""
Client for Wikimedia REST APIs (Pageview API & Wikidata API).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import USER_AGENT

TIMEOUT = 15
BASE_PAGEVIEWS_URL = "https://wikimedia.org/api/rest_v1/metrics/pageviews"


def _get(url: str, params: Optional[dict] = None) -> dict:
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def fetch_monthly_pageviews(article_title: str, lang: str, start: str, end: str) -> List[dict]:
    """
    Fetches monthly article pageviews from Wikimedia API.
    Dates in YYYYMMDD format.
    """
    slug = article_title.replace(" ", "_")
    url = (
        f"{BASE_PAGEVIEWS_URL}/per-article/"
        f"{lang}.wikipedia.org/all-access/user/{slug}/monthly/{start}/{end}"
    )
    try:
        data = _get(url)
        items = data.get("items", [])
        return [
            {
                "date": f"{item['timestamp'][:4]}-{item['timestamp'][4:6]}-01",
                "views": item.get("views", 0),
            }
            for item in items
        ]
    except Exception:
        return []


def fetch_project_aggregate_views(lang: str, start: str, end: str) -> Dict[str, int]:
    """
    Fetches aggregate monthly pageviews for the ENTIRE language Wikipedia project.
    Returns a dict mapping 'YYYY-MM-01' -> total_project_views.
    """
    project = f"{lang}.wikipedia.org"
    # ✅ ВИПРАВЛЕНО: використовуємо /aggregate/ замість /aggregate-all-projects/
    url = (
        f"{BASE_PAGEVIEWS_URL}/aggregate/"
        f"{project}/all-access/user/monthly/{start}/{end}"
    )
    try:
        data = _get(url)
        items = data.get("items", [])
        result = {}
        for item in items:
            date_key = f"{item['timestamp'][:4]}-{item['timestamp'][4:6]}-01"
            result[date_key] = item.get("views", 0)
        return result
    except Exception:
        return {}