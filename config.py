import os

from dotenv import load_dotenv

load_dotenv()

# Workflow debugging flag: DEBUG logging plus LangGraph step-by-step traces.
DEBUG_MODE = os.getenv("DEBUG_MODE", "false").strip().lower() in {"1", "true", "yes", "on"}

# How many times a rejected report may be revised. 1 in the initial version.
MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "1"))
