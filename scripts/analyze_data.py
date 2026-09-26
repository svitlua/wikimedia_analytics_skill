#!/usr/bin/env python3
"""
Step 2 of the pipeline: Consumes raw_views.json produced by Step 1 (fetch_views.py)
and computes key metrics (total volume, monthly average, growth rate, spike/volatility
ratio, and trend reliability confidence) per language edition.

Usage:
    python scripts/analyze_data.py --input output/<topic-slug>__<langs>/raw_views.json
    
If --output is omitted, it defaults to metrics.json alongside the input file:
    output/<topic-slug>__<langs>/metrics.json

Output JSON Schema:
{
  "topic": "Astronomy",
  "source_lang": "en",
  "start": "20240101",
  "end": "20260101",
  "languages": {
    "uk": {
      "resolved": true,
      "resolved_title": "Астрономія",
      "total_views": 120000,
      "monthly_avg": 5000.0,
      "growth_rate_pct": 25.4,
      "spike_ratio": 1.65,
      "confidence": "HIGH_GROWTH",
      "notes": "Sustained upward trend with low volatility."
    },
    "cs": {
      "resolved": false,
      "resolved_title": null,
      "total_views": 0,
      "monthly_avg": 0.0,
      "growth_rate_pct": None,
      "spike_ratio": 0.0,
      "confidence": "UNRESOLVED",
      "notes": "No article exists on cs.wikipedia.org for this topic."
    }
  }
}
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path


def calculate_metrics(series: list[dict]) -> dict:
    """
    Computes summary metrics and trend reliability for a single time series.
    """
    if not series:
        return {
            "total_views": 0,
            "monthly_avg": 0.0,
            "growth_rate_pct": None,
            "spike_ratio": 0.0,
            "confidence": "NO_DATA",
            "notes": "Series exists but contains zero data points.",
        }

    views = [item["views"] for item in series]
    total_views = sum(views)
    monthly_avg = round(total_views / len(views), 1)

    # 1. Volatility / Spike Ratio (Max view / Median view)
    sorted_views = sorted(views)
    n = len(sorted_views)
    if n % 2 == 1:
        median_views = sorted_views[n // 2]
    else:
        median_views = (sorted_views[(n // 2) - 1] + sorted_views[n // 2]) / 2.0

    max_views = max(views)
    # Prevent division by zero if median is 0
    safe_median = max(median_views, 1.0)
    spike_ratio = round(max_views / safe_median, 2)

    # 2. Growth Rate (Percentage change between first half and second half)
    half_point = len(views) // 2
    if half_point >= 1:
        first_half_avg = sum(views[:half_point]) / half_point
        second_half_avg = sum(views[half_point:]) / (len(views) - half_point)
        
        safe_first_half = max(first_half_avg, 1.0)
        growth_rate_pct = round(((second_half_avg - first_half_avg) / safe_first_half) * 100, 1)
    else:
        growth_rate_pct = None

    # 3. Confidence & Reliability Classification
    if total_views < 500:
        confidence = "LOW_VOLUME"
        notes = "Traffic volume is too low (<500 total) to establish a reliable baseline."
    elif spike_ratio >= 3.5:
        confidence = "LOW_SPIKY"
        notes = f"High volatility detected (peak is {spike_ratio}x median). Growth may be driven by a short-lived news spike."
    elif growth_rate_pct is not None and growth_rate_pct >= 15.0:
        confidence = "HIGH_GROWTH"
        notes = f"Sustained upward momentum (+{growth_rate_pct}% half-over-half) with controlled volatility."
    elif growth_rate_pct is not None and growth_rate_pct <= -15.0:
        confidence = "DECLINING"
        notes = f"Consistent decline in pageviews ({growth_rate_pct}% half-over-half)."
    else:
        confidence = "STABLE"
        notes = "Consistent baseline traffic with no significant growth or decline."

    return {
        "total_views": total_views,
        "monthly_avg": monthly_avg,
        "growth_rate_pct": growth_rate_pct,
        "spike_ratio": spike_ratio,
        "confidence": confidence,
        "notes": notes,
    }


def analyze_dataset(raw_data: dict) -> dict:
    """
    Processes all languages in a raw_views dataset and formats output dict.
    """
    output_languages = {}

    for lang, lang_info in raw_data.get("languages", {}).items():
        if not lang_info.get("resolved", False):
            output_languages[lang] = {
                "resolved": False,
                "resolved_title": None,
                "total_views": 0,
                "monthly_avg": 0.0,
                "growth_rate_pct": None,
                "spike_ratio": 0.0,
                "confidence": "UNRESOLVED",
                "notes": f"No Wikipedia article exists for this topic on {lang}.wikipedia.org.",
            }
            continue

        series = lang_info.get("series", [])
        metrics = calculate_metrics(series)

        output_languages[lang] = {
            "resolved": True,
            "resolved_title": lang_info.get("resolved_title"),
            **metrics,
        }

    return {
        "topic": raw_data.get("topic"),
        "source_lang": raw_data.get("source_lang"),
        "granularity": raw_data.get("granularity", "monthly"),
        "start": raw_data.get("start"),
        "end": raw_data.get("end"),
        "languages": output_languages,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze pageview time series for growth and reliability.")
    parser.add_argument("--input", required=True, help="Path to raw_views.json from Step 1.")
    parser.add_argument("--output", help="Optional path for output metrics.json.")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file '{input_path}' does not exist.", file=sys.stderr)
        sys.exit(1)

    raw_data = json.loads(input_path.read_text(encoding="utf-8"))
    metrics_result = analyze_dataset(raw_data)

    out_path = Path(args.output) if args.output else input_path.parent / "metrics.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(metrics_result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
