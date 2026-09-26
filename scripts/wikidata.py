"""
Resolves a single-language article title to the equivalent article title
in each requested Wikipedia language edition, using Wikidata as the anchor.

Flow:
    1. Look up the Wikidata item (QID) attached to the source-language
       article via pageprops.wikibase_item.
    2. Fallback: If not found, search Wikipedia (list=search) to find the
       closest matching article, then look up its QID.
    3. Ask Wikidata for that item's sitelinks filtered to target wikis.
    4. Return {lang_code: title_or_None}.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import USER_AGENT

TIMEOUT = 15


def _get(url: str, params: dict) -> dict:
    resp = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def search_wikipedia_title(source_lang: str, title: str) -> Optional[str]:
    """Fallback search when exact title match yields no Wikidata item."""
    url = f"https://{source_lang}.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "list": "search",
        "srsearch": title,
        "srlimit": 1,
        "format": "json",
    }
    data = _get(url, params)
    search_results = data.get("query", {}).get("search", [])
    if search_results:
        return search_results[0]["title"]
    return None


def get_wikidata_qid(source_lang: str, title: str) -> tuple[Optional[str], str]:
    """
    Find the Wikidata item id (e.g. 'Q333') and resolved source title.
    Uses direct lookup first, and falls back to full-text search.
    """
    url = f"https://{source_lang}.wikipedia.org/w/api.php"
    
    # 1. Direct PageProps Lookup
    params = {
        "action": "query",
        "titles": title,
        "prop": "pageprops",
        "ppprop": "wikibase_item",
        "format": "json",
        "redirects": 1,
    }
    data = _get(url, params)
    pages = data.get("query", {}).get("pages", {})
    
    for page in pages.values():
        if "missing" not in page:
            qid = page.get("pageprops", {}).get("wikibase_item")
            resolved_source_title = page.get("title", title)
            if qid:
                return qid, resolved_source_title

    # 2. Search Fallback (if exact title match failed)
    fallback_title = search_wikipedia_title(source_lang, title)
    if fallback_title and fallback_title.lower() != title.lower():
        params["titles"] = fallback_title
        data = _get(url, params)
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            if "missing" not in page:
                qid = page.get("pageprops", {}).get("wikibase_item")
                if qid:
                    return qid, fallback_title

    return None, title


def resolve_titles(source_lang: str, title: str, target_langs: list) -> dict:
    """
    Returns, for each requested language code (plus the source language),
    either the matching article title on that language's Wikipedia, or
    None if no such article exists.
    """
    all_langs = sorted(set(target_langs) | {source_lang})
    result = {lang: None for lang in all_langs}

    qid, resolved_source_title = get_wikidata_qid(source_lang, title)
    if qid is None:
        result[source_lang] = resolved_source_title
        return result

    site_filter = "|".join(f"{lang}wiki" for lang in all_langs)
    data = _get(
        "https://www.wikidata.org/w/api.php",
        {
            "action": "wbgetentities",
            "ids": qid,
            "props": "sitelinks",
            "sitefilter": site_filter,
            "format": "json",
        },
    )
    entity = data.get("entities", {}).get(qid, {})
    sitelinks = entity.get("sitelinks", {})
    for lang in all_langs:
        site_key = f"{lang}wiki"
        if site_key in sitelinks:
            result[lang] = sitelinks[site_key]["title"]

    if not result.get(source_lang):
        result[source_lang] = resolved_source_title

    return result