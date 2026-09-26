#!/usr/bin/env python3
"""
Step 3 of the pipeline: render a two-panel line chart from analyzed dataset JSON:
  - Top panel: Share of Voice (Views per 1M Total)
  - Bottom panel: Absolute Monthly Views

Usage:
    python scripts/generate_chart.py \
        --input output/lion__cs-de-uk/analyzed_views.json \
        --out output/lion__cs-de-uk/chart.png
"""
import argparse
import json
import sys
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime


def load_data(input_path: str) -> dict:
    with open(input_path, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_chart(data: dict, output_path: str) -> None:
    topic = data.get("topic", "Topic")
    languages_data = data.get("languages", {})

    # Set aesthetic style
    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    
    # Configure font fallback for Cyrillic / international support
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial", "Liberation Sans", "sans-serif"]

    # 2-Panel Figure Setup with dedicated vertical spacing to avoid header/legend collisions
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6.8), sharex=True, dpi=300)
    fig.subplots_adjust(top=0.88, hspace=0.35, bottom=0.12, left=0.10, right=0.95)

    color_palette = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2"]
    
    # Track overall date bounds for formatting
    all_dates = []

    for idx, (lang, lang_info) in enumerate(languages_data.items()):
        if not lang_info.get("resolved") or not lang_info.get("series"):
            continue

        resolved_title = lang_info.get("resolved_title", topic)
        label_text = f"{lang.upper()} ({resolved_title})"
        color = color_palette[idx % len(color_palette)]

        series = lang_info["series"]
        dates = [datetime.strptime(item["date"], "%Y-%m-%d") for item in series]
        all_dates.extend(dates)

        # Metrics
        views_per_m = [item.get("views_per_million", 0.0) for item in series]
        abs_views = [item.get("views", 0) for item in series]

        # Top Panel: Share of Voice
        ax1.plot(
            dates,
            views_per_m,
            marker="o",
            markersize=3,
            linewidth=1.8,
            color=color,
            label=label_text,
        )

        # Bottom Panel: Absolute Monthly Views
        ax2.plot(
            dates,
            abs_views,
            marker="s",
            markersize=3,
            linewidth=1.5,
            linestyle="--",
            color=color,
            label=label_text,
        )

    # --- Top Panel Formatting ---
    ax1.set_title(f"Market Interest Analysis: '{topic}'", fontsize=12, fontweight="bold", pad=12)
    ax1.set_ylabel("Share of Voice\n(Views per 1M Total)", fontsize=9, fontweight="bold")
    ax1.legend(
        loc="upper right",
        frameon=True,
        facecolor="white",
        edgecolor="#CBD5E0",
        fontsize=8,
        ncol=min(len(languages_data), 4),
    )
    ax1.grid(True, linestyle=":", alpha=0.6)

    # --- Bottom Panel Formatting ---
    ax2.set_ylabel("Absolute Monthly Views", fontsize=9, fontweight="bold")
    ax2.set_xlabel("Month", fontsize=9, fontweight="bold")
    ax2.grid(True, linestyle=":", alpha=0.6)

    # Format X-axis dates cleanly
    if all_dates:
        ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
        ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        fig.autofmt_xdate(rotation=0, ha="center")

    # Output generation
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_file, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Chart saved to {out_file}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate dual-panel visualization chart for topic interest.")
    parser.add_argument("--input", "-i", required=True, help="Path to analyzed_views.json input file")
    parser.add_argument("--out", "-o", required=True, help="Path to save output chart PNG")
    args = parser.parse_args()

    data = load_data(args.input)
    generate_chart(data, args.out)


if __name__ == "__main__":
    main()