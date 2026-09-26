"""
Single source of truth for how this skill identifies itself to Wikimedia's
APIs. Both wikidata.py and wikimedia_api.py import CONTACT/USER_AGENT from
here so there is exactly one place to configure -- previously each module
defined its own copy, which meant updating one and forgetting the other
was an easy mistake.

Wikimedia's API usage policy expects a genuine, identifying User-Agent
(ideally an email or a URL to a project page) -- generic or placeholder
values are exactly what their infrastructure is tuned to throttle or
block. Set WIKI_ANALYTICS_CONTACT in the environment before real use:

    export WIKI_ANALYTICS_CONTACT="your-real-email@example.com"

Falling back to a placeholder is fine for local testing against mocks,
but should not be relied on for real traffic against wikimedia.org.
"""
import os

CONTACT = os.environ.get("WIKI_ANALYTICS_CONTACT", "svitlana.shymko123@gmail.com")
USER_AGENT = f"wikimedia-analytics-skill/0.1 (contact: {CONTACT}) requests"