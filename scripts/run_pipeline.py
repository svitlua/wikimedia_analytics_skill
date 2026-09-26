#!/usr/bin/env python3
"""
Master Pipeline Orchestrator: Runs Steps 1 through 4 sequentially for a given topic
and outputs the final metrics summary to stdout for LLM agents.

Usage:
    python scripts/run_pipeline.py \
        --topic-title "Artificial intelligence" \
        --source-lang en \
        --langs uk,cs,de \
        --months 12
"""
from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


def run_step_1(cmd: list[str]) -> Path:
    print(f"\n[EXEC] {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    
    print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="")

    if result.returncode != 0:
        print(f"Error: Step 1 failed with return code {result.returncode}", file=sys.stderr)
        sys.exit(result.returncode)

    # Extract output path printed by fetch_views.py ("Wrote output/...")
    for line in result.stdout.splitlines():
        if line.startswith("Wrote "):
            return Path(line.replace("Wrote ", "").strip())

    raise FileNotFoundError("Could not determine output path from Step 1 output.")


def run_command(cmd: list[str]) -> None:
    print(f"\n[EXEC] {' '.join(cmd)}")
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        print(f"Error: Step failed with return code {result.returncode}", file=sys.stderr)
        sys.exit(result.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run complete 4-step Wikipedia pageview research pipeline.")
    parser.add_argument("--topic-title", required=True, help="Article title in the source language.")
    parser.add_argument("--source-lang", default="en", help="Source Wikipedia language code (default: en).")
    parser.add_argument("--langs", required=True, help="Target language codes (comma-separated, e.g., 'uk,cs,de').")
    parser.add_argument("--months", type=int, default=12, help="Number of months of historical data (default: 12).")
    args = parser.parse_args()

    python_exe = sys.executable
    script_dir = Path(__file__).parent

    # Step 1: Fetch Raw Data
    print("=== STEP 1: Fetching Raw Pageview Data ===")
    raw_views_path = run_step_1([
        python_exe,
        str(script_dir / "fetch_views.py"),
        "--topic-title", args.topic_title,
        "--source-lang", args.source_lang,
        "--langs", args.langs,
        "--months", str(args.months),
    ])

    output_dir = raw_views_path.parent
    metrics_path = output_dir / "metrics.json"
    chart_path = output_dir / "chart.png"
    report_path = output_dir / "report.pdf"

    # Step 2: Analyze Data
    print("\n=== STEP 2: Analyzing Growth & Trends ===")
    run_command([
        python_exe,
        str(script_dir / "analyze_data.py"),
        "--input", str(raw_views_path),
        "--output", str(metrics_path),
    ])

    # Step 3: Generate Visual Chart
    print("\n=== STEP 3: Rendering Trend Chart ===")
    run_command([
        python_exe,
        str(script_dir / "generate_chart.py"),
        "--input", str(raw_views_path),
        "--out", str(chart_path),
    ])

    # Step 4: Export PDF Brief
    print("\n=== STEP 4: Exporting Executive PDF Brief ===")
    run_command([
        python_exe,
        str(script_dir / "export_pdf.py"),
        "--summary", str(metrics_path),
        "--chart", str(chart_path),
        "--output", str(report_path),
    ])

    print(f"\n✅ Pipeline complete! Final PDF generated at: {report_path}")

    # Step 5: Output JSON metrics summary for agent context
    if metrics_path.exists():
        print("\n=== SUMMARY METRICS (FOR AGENT) ===")
        metrics_data = json.loads(metrics_path.read_text(encoding="utf-8"))
        print(json.dumps(metrics_data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()