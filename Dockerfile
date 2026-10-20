# The API: FastAPI on uvicorn, with the founding team's agents.
#
# Two stages: uv installs the locked dependencies into a virtual environment,
# and only that environment and the app's code go into the slim image that
# runs, as a user without privileges. Keys and passwords come from the
# environment when the container starts (.env through docker compose), never
# from the image: .dockerignore keeps .env out of the build.

FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.12-slim
RUN useradd --create-home --uid 10001 cofounder
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY *.py ./
COPY agents ./agents
COPY assets ./assets
COPY scenarios ./scenarios
COPY templates ./templates
# JSON log lines for a collector; one worker, since the Monitor's statistics
# and the rate limits live in the process (sessions and reports are shared in
# PostgreSQL).
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 LOG_FORMAT=json
USER cofounder
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import sys, urllib.request; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status != 200)"]
# The API's own access log replaces uvicorn's; on a stop, requests still
# running get 30 s to finish.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--timeout-graceful-shutdown", "30"]
