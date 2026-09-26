# Wikimedia Analytics Agent Skill for B2C Market Validation

An agentic analytics skill designed to assess organic search demand and topic interest using Wikipedia pageview metrics. Built for B2C product managers, founders, and growth strategists deciding where to invest next (e.g., introducing a new course, expanding content topics, or expanding into new language markets).

---

## 🎯 Product Value

Adding new features, courses, or language localizations to a B2C application requires significant time and financial investment. Wikipedia pageview data serves as a free, unbiased proxy for top-of-funnel demand (**Problem Awareness & Organic Search Interest**).

**Key Capabilities:**
* **Comparative Market Analysis:** Benchmark user interest across multiple topics or language editions over custom timeframes (e.g., 12 to 24 months).
* **Growth Trend Metrics:** Automatically calculate Year-over-Year (YoY) growth rates (`growth_rate_pct`).
* **Data Confidence Scoring:** Automatically evaluate traffic variance to filter out anomalous news spikes or bot-driven traffic.
* **Executive Deliverables:** Auto-generate normalized time-series charts and 1-page PDF executive summaries ready for team sharing.

---

## 🏗️ Architecture & Pipeline Overview

The skill operates on a 2-tier architecture:
1. **Agentic Layer (`SKILL.md` / `test_openrouter_agent.py`):** Handles natural language understanding, extracts parameters from query prompts, and synthesizes structured business memos.
2. **Deterministic Data Layer (`scripts/`):** A robust Python pipeline that fetches, cleans, and processes data to prevent LLM hallucinations.

```text
[User Query] 
     │
     ▼
[AI Agent (OpenRouter LLM)] ────(JSON Parameters)──┐
                                                   ▼
┌──────────────────────────────────────────────────┴──────────────────────────────────┐
│ Python Orchestrator (`scripts/run_pipeline.py`)                                     │
│                                                                                     │
│  1. Fetch (`fetch_views.py`)     → Wikimedia REST API (12-24m history)             │
│  2. Analyze (`analyze_views.py`) → Total Views, YoY Growth, Confidence Score        │
│  3. Visualizer (`generate_chart.py`) → Y-axis normalized Matplotlib charts          │
│  4. Exporter (`export_pdf.py`)   → 1-page PDF Executive Summary (ReportLab)        │
└──────────────────────────────────────────────────┬──────────────────────────────────┘
                                                   ▼
[User Output] ◄───(Strategic Decision Memo)
