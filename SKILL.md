---
name: wikimedia-analytics-skill
description: Analyses Wikimedia pageview data to evaluate audience interest, language usage, and market potential for a topic across Wikipedia language editions. Compares languages, checks trend reliability, and generates charts and a 1-page PDF report.
---

# Wikimedia Analytics Skill

## Purpose
This skill enables the agent to act as a Product Strategy Assistant. It analyzes
Wikipedia pageviews across different language editions to evaluate topic
popularity, compare interest across languages, and assess growth trends before
a team invests in a new feature, course, or localization.

## Key Capabilities
1. **Multi-Language Interest Comparison**: Compare interest across language
   editions (e.g. `uk`, `pl`, `cs`) for the *same* underlying topic, automatically
   resolving the correct per-language article titles via Wikidata.
2. **Topic Growth Analysis**: Calculate growth over time, monthly averages,
   and volatility/spike ratios. Also computes each language's traffic as a
   share of that Wikipedia edition's total readership ("views per million"),
   so a small-readership edition isn't unfairly judged against a huge one on
   raw view counts alone.
3. **Trend Reliability Check**: Flag whether a trend is backed by stable data
   or driven by temporary spikes/low volume.
4. **Automated Visual & PDF Briefing**: Produce a two-panel trend chart
   (`chart.png`) and an executive 1-page PDF summary (`report.pdf`).

---
## One-time setup

Before the first run in a session, install dependencies into a virtual
environment (do this once; skip if `.venv` already exists and is populated):

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

All commands below assume `.venv/bin/python` (or an activated venv) is on
the path. Do not `pip install` packages ad hoc — if something is missing,
it should be added to `requirements.txt`, not installed one-off.

Wikimedia's API usage policy expects a genuine, identifying User-Agent. A
contact address is baked into `config.py` as a fallback, but you can
override it per environment:
```bash
export WIKI_ANALYTICS_CONTACT="your-real-contact@example.com"
```

---

## Execution Protocol

Run these four steps in sequence for every query.

### Step 1 — Resolve titles & fetch pageviews
```bash
python scripts/fetch_views.py \
    --topic-title "<Article_Title_in_source_language>" \
    --source-lang <source_lang_code> \
    --langs <comma_separated_lang_codes> \
    --months <N>
```
- `--topic-title`: the article title in whatever language you know it in.
- `--source-lang`: default `en`.
- `--langs`: the language editions to compare, e.g. `uk,pl,cs`. The source
  language is included automatically even if not repeated here.
- `--months`: how far back to look (default 12). Use `--start`/`--end`
  (`YYYYMMDD`) instead for an exact range. The end of the range defaults to
  the end of the last fully-completed calendar month, so it never reports
  an artificial drop from a not-yet-published partial month.
- `--granularity`, `--access`, `--agent` exist as flags but **currently have
  no effect** — every request is fetched as monthly/all-access/user
  regardless of what you pass. Don't rely on these until fixed.
- Omit `--out`: the script derives a collision-free path automatically —
  `output/<topic-slug>__<sorted-langs>/raw_views.json`. Read the printed
  `Wrote <path>` line to know where the result landed; don't guess the path
  (the slug includes a hash suffix and won't match a naive
  lowercase-and-underscore guess).

**Output schema** (`raw_views.json`):
```json
{
  "topic": "Astronomy",
  "source_lang": "en",
  "granularity": "monthly",
  "start": "20240101",
  "end": "20241231",
  "generated_at": "2026-09-24T12:00:00Z",
  "languages": {
    "uk": {
      "project": "uk.wikipedia.org",
      "resolved_title": "Астрономія",
      "resolved": true,
      "series": [
        {
          "date": "2024-01-01",
          "views": 12345,
          "project_total_views": 48000000,
          "views_per_million": 257.19
        }
      ]
    },
    "cs": {
      "project": "cs.wikipedia.org",
      "resolved_title": null,
      "resolved": false,
      "series": []
    }
  }
}
```
`views_per_million` is this article's views per million total views on that
language edition that period — use it, not raw `views`, when comparing
interest fairly across languages with very different overall readership.

**How to read `"resolved": false`:** no Wikipedia article about this topic
exists in that language edition. This is a real, reportable finding ("no
local content exists yet for this topic"), not a fetch failure. Never
silently drop an unresolved language from your final answer.

### Step 2 — Analyze growth & trend reliability
```bash
python scripts/analyze_data.py --input <path_from_step_1>
```
Writes `metrics.json` next to the input file by default.

**Output schema** (`metrics.json`):
```json
{
  "topic": "Astronomy",
  "source_lang": "en",
  "granularity": "monthly",
  "start": "20240101",
  "end": "20241231",
  "languages": {
    "uk": {
      "resolved": true,
      "resolved_title": "Астрономія",
      "total_views": 120000,
      "monthly_avg": 5000.0,
      "growth_rate_pct": 25.4,
      "spike_ratio": 1.65,
      "confidence": "HIGH_GROWTH",
      "notes": "Sustained upward momentum (+25.4% half-over-half) with controlled volatility."
    },
    "cs": {
      "resolved": false,
      "resolved_title": null,
      "total_views": 0,
      "monthly_avg": 0.0,
      "growth_rate_pct": null,
      "spike_ratio": 0.0,
      "confidence": "UNRESOLVED",
      "notes": "No article exists on cs.wikipedia.org for this topic."
    }
  }
}
```
`confidence` is one of: `UNRESOLVED` | `NO_DATA` | `LOW_VOLUME` | `LOW_SPIKY`
| `HIGH_GROWTH` | `DECLINING` | `STABLE`. Always relay the `notes` text
alongside any number you quote — see the growth_rate_pct caveat above
before repeating that field verbatim.

### Step 3 — Generate chart
```bash
python scripts/generate_chart.py --input <raw_views.json_path> --out chart.png
```
Reads `raw_views.json` (not `metrics.json`) directly, since it already
contains the `views_per_million` field. Produces a two-panel PNG: share of
voice (views per million) on top, absolute monthly views below.

### Step 4 — Create PDF summary
```bash
python scripts/export_pdf.py --summary metrics.json --chart chart.png --output report.pdf
```

---

## Handling follow-up and refined queries

Users commonly narrow, widen, or extend a query after seeing the first
answer ("also check Slovak," "widen this to 3 years"). Re-run Step 1 with
the updated `--langs` / `--months` / `--start`/`--end` values — previously
fetched (language, title, month) combinations are served from a local
cache automatically, so only genuinely new months are fetched from the
network. Note: the `views_per_million` project-total lookup is **not**
currently cached and re-fetches from the network on every run, even for
previously-seen months — this doesn't affect correctness, only speed.

## Reporting results to the user

Every claim about a trend in your final response must be accompanied by:
- the date range and language(s) it covers,
- an explicit note of low reliability if `confidence` is `LOW_VOLUME` or
  `LOW_SPIKY`, or if `growth_rate_pct` looks implausibly large (see Known
  issues above — describe the change qualitatively instead in that case),
- an explicit mention of any requested language where no article exists at
  all (`"resolved": false`), rather than omitting it.

Never state that interest "is growing" or "is declining" without this
context attached — an unqualified trend claim is not an acceptable output
of this skill.
