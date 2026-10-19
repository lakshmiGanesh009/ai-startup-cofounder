import os

from dotenv import load_dotenv

load_dotenv()

# Workflow debugging flag: DEBUG logging plus LangGraph step-by-step traces.
DEBUG_MODE = os.getenv("DEBUG_MODE", "false").strip().lower() in {"1", "true", "yes", "on"}

# How many times a rejected report may be revised. 1 in the initial version.
MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "1"))

# How many cross-critique rounds are allowed. 1 in the initial version.
MAX_CRITIQUE_ROUNDS = int(os.getenv("MAX_CRITIQUE_ROUNDS", "1"))

# Per-call LLM timeout in seconds, and how many times to retry a failed call.
# Azure occasionally stalls a request that an identical retry answers in seconds,
# so the timeout should be a few times the slowest normal call (under 60 s up to
# medium reasoning) rather than generous. Calls at high reasoning can take a
# minute or two, so they get LLM_TIMEOUT_HIGH instead.
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "120"))
LLM_TIMEOUT_HIGH = float(os.getenv("LLM_TIMEOUT_HIGH", "300"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))

# Seconds to wait for one web search (Tavily) while a brief is prepared, and
# for one deep research task, which takes 20-90 s (measured with "mini").
SEARCH_TIMEOUT = float(os.getenv("SEARCH_TIMEOUT", "20"))
RESEARCH_TIMEOUT = float(os.getenv("RESEARCH_TIMEOUT", "300"))

# Browser origins allowed to call the API, comma-separated. The default is the
# Next.js dev server.
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]
