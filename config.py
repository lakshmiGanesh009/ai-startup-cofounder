import os

from dotenv import load_dotenv

load_dotenv()

# Workflow debugging flag: DEBUG logging plus LangGraph step-by-step traces.
DEBUG_MODE = os.getenv("DEBUG_MODE", "false").strip().lower() in {"1", "true", "yes", "on"}

# How log lines are written: "text" for reading in a terminal, or "json", one
# object a line, for a log collector. Either way each line names its request.
LOG_FORMAT = "json" if os.getenv("LOG_FORMAT", "text").strip().lower() == "json" else "text"

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

# Where sessions, reports and the Monitor's history are kept: a PostgreSQL URL,
# such as postgresql://user:password@localhost:5432/cofounder, so they survive a
# restart; unset, they are kept in memory and lost when the API stops.
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

# The key a caller must send (Authorization: Bearer <key>) for anything but
# /health. The Next.js app's server adds it to the calls it forwards, so it
# never reaches a browser. Unset, anyone who can reach the API can use it:
# fine on your own machine, not on a network.
API_KEY = os.getenv("API_KEY", "").strip()

# Limits, so one caller cannot exhaust the API or the model deployment. The
# largest request body accepted, in bytes; evaluations, briefs and proposals
# running at once (more are refused until one ends); and, per caller, those
# runs an hour and requests a minute.
MAX_REQUEST_BYTES = int(os.getenv("MAX_REQUEST_BYTES", "1000000"))
MAX_CONCURRENT_RUNS = int(os.getenv("MAX_CONCURRENT_RUNS", "4"))
RUNS_PER_HOUR = int(os.getenv("RUNS_PER_HOUR", "30"))
REQUESTS_PER_MINUTE = int(os.getenv("REQUESTS_PER_MINUTE", "300"))
