import os
import json
import subprocess
import sys

from openai import OpenAI

if __name__ == "__main__":
    # Force UTF-8 output (needed on Windows consoles for Cyrillic text).
    # reconfigure() is idempotent and doesn't replace the stream object,
    # unlike wrapping it in a fresh io.TextIOWrapper -- doing the latter
    # unconditionally at import time broke pytest's own stdout capture
    # when this module was imported to test extract_summary_json below,
    # and would equally break any other caller that imports this file
    # rather than running it directly.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

_client = None


def get_client() -> OpenAI:
    """
    Lazily constructs the OpenAI client on first real use.

    Building this at module import time (as an earlier version did) meant
    simply IMPORTING this file -- e.g. to reuse extract_summary_json in a
    test, or from any other script -- required a real OPENROUTER_API_KEY
    to be set, and crashed immediately otherwise. Deferring construction
    until a request is actually made keeps the module importable without
    credentials, while still failing clearly (see the check below) if you
    try to actually call the API without a key configured.
    """
    global _client
    if _client is None:
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set. Export it before running "
                "this script against the real OpenRouter API."
            )
        _client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
    return _client

def sanitize_langs(langs_raw) -> str:
    """Cleans array or messy string inputs into standard comma-separated format."""
    if isinstance(langs_raw, list):
        return ",".join(str(item).strip() for item in langs_raw)
    elif isinstance(langs_raw, str):
        cleaned = langs_raw.replace("[", "").replace("]", "").replace('"', "").replace("'", "").strip()
        return cleaned
    return str(langs_raw)

SUMMARY_MARKER = "=== SUMMARY METRICS (FOR AGENT) ==="


def extract_summary_json(stdout: str) -> str:
    """
    Pulls the metrics JSON run_pipeline.py prints after SUMMARY_MARKER out
    of its captured stdout.

    This deliberately does NOT reconstruct the output file path itself.
    An earlier version guessed the path with its own ad hoc slugging logic
    (topic_title.lower().replace(" ", "_")) -- but fetch_views.py's real
    slug (lib/cache.py's slug()) always appends a content hash, so the two
    could never match, and the file it guessed ("analyzed_views.json")
    isn't a name any script actually writes (the real file is
    "metrics.json"). Reading the JSON straight from run_pipeline.py's own
    stdout removes that whole class of path-guessing bug -- there's only
    one place that knows the real path (run_pipeline.py itself), and this
    reads its answer instead of re-deriving it independently.

    Raises ValueError with the full stdout included if the marker isn't
    found, so a caller sees exactly what the pipeline actually printed
    instead of a generic "file not found" message that hides the cause.
    """
    if SUMMARY_MARKER not in stdout:
        raise ValueError(
            "Expected marker not found in run_pipeline.py output -- "
            f"full stdout was:\n{stdout}"
        )
    return stdout.split(SUMMARY_MARKER, 1)[1].strip()


def execute_pipeline_tool(topic_title: str, langs_raw, months: int = 12) -> str:
    """Executes the CLI script run_pipeline.py and returns the JSON result content."""
    langs = sanitize_langs(langs_raw)
    print(f"\n[TOOL EXECUTED] Topic: '{topic_title}', Languages: '{langs}', Months: {months}")

    script_dir = os.path.dirname(os.path.abspath(__file__))
    cmd = [
        sys.executable, os.path.join(script_dir, "run_pipeline.py"),
        "--topic-title", topic_title,
        "--source-lang", "en",
        "--langs", langs,
        "--months", str(months)
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return f"Pipeline execution error: {result.stderr}"

    try:
        return extract_summary_json(result.stdout)
    except ValueError as e:
        return f"Pipeline executed, but its summary output could not be parsed: {e}"

SYSTEM_PROMPT = """
You are an expert market analyst. You must extract parameters to run a Wikipedia analytics query.

Your ONLY job in this first step is to output valid JSON matching this schema:
{
  "topic_title": "Main topic/product name in English (e.g. 'Astronomy')",
  "langs": "Comma-separated language code string (e.g. 'uk')",
  "months": 12
}

Do NOT include any conversational text or markdown codeblocks outside the JSON.
"""

FINAL_SUMMARY_PROMPT = """
You are a lead product analyst and business strategist.
Based on the provided Wikipedia Analytics JSON data, answer the user's question in Ukrainian.

Prepare a concise strategic decision memo including:
1. Total pageviews
2. Growth rate (growth_rate_pct)
3. Data confidence rating
4. Concrete business recommendation on whether to launch the course/product.
"""

def test_prompt(user_query: str, model_id: str = "openrouter/auto"):
    print("\n==================================================")
    print(f"MODEL: {model_id}")
    print(f"PROMPT: {user_query}")
    print("==================================================")

    # Step 1: Prompt the model to produce tool arguments as JSON
    step1_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_query}
    ]

    response = get_client().chat.completions.create(
        model=model_id,
        messages=step1_messages,
    )

    raw_content = response.choices[0].message.content.strip()
    
    # Clean potential markdown fences (e.g. ```json ... ```)
    if raw_content.startswith("```"):
        raw_content = raw_content.split("```")[1]
        if raw_content.startswith("json"):
            raw_content = raw_content[4:]
    raw_content = raw_content.strip()

    try:
        args = json.loads(raw_content)
    except Exception as e:
        print(f"Failed to parse JSON parameters from model response: {raw_content}")
        return

    # Step 2: Execute local script
    tool_data = execute_pipeline_tool(
        topic_title=args.get("topic_title", "Astronomy"),
        langs_raw=args.get("langs", "uk"),
        months=int(args.get("months", 12))
    )

    # Step 3: Pass tool data back to model for final text analysis
    step2_messages = [
        {"role": "system", "content": FINAL_SUMMARY_PROMPT},
        {"role": "user", "content": f"User question: {user_query}\n\nAnalytics Data:\n{tool_data}"}
    ]

    final_response = get_client().chat.completions.create(
        model=model_id,
        messages=step2_messages,
    )

    print("\n=== AGENT FINAL RESPONSE ===")
    print(final_response.choices[0].message.content)

if __name__ == "__main__":
    test_query = "Ми думаємо додати курс з астрономії до освітнього застосунку. Чи зростає інтерес до цієї теми в україномовній Wikipedia, і наскільки цьому зростанню можна довіряти?"
    
    # Works reliably across ALL OpenRouter models, including openrouter/auto
    test_prompt(test_query, model_id="openrouter/auto")