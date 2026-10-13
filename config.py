import os

from dotenv import load_dotenv

load_dotenv()

# Workflow debugging flag: DEBUG logging plus LangGraph step-by-step traces.
DEBUG_MODE = os.getenv("DEBUG_MODE", "false").strip().lower() in {"1", "true", "yes", "on"}
