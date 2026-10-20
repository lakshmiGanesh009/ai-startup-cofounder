#!/usr/bin/env bash
# Starts the AI Startup Co-Founder on this machine: locally, the default, or in
# Docker. With no command it asks which, and on which ports; ./start.sh --help
# lists the rest. Written for the bash 3.2 that macOS ships.

set -euo pipefail

# The start of a line in .env that sets a setting, perhaps after "export".
SETS='^[[:space:]]*(export[[:space:]]+)?'

usage() {
  cat <<'EOF'
Usage: ./start.sh [local | docker | stop] [--web-port N] [--api-port N]

Starts the AI Startup Co-Founder on this machine.

  local    the API (uv) and the web app (next dev) here; Ctrl+C stops both
  docker   PostgreSQL, the API and the web app in containers built from this
           checkout, running in the background
  stop     stops the containers; the database's data stays in its volume

With no command it asks which, and on which ports. --web-port and --api-port,
or WEB_PORT and API_PORT, choose the ports (3000 and 8000 by default); a port
in use is asked about again. Both answer on this machine only: WEB_HOST=0.0.0.0
opens the web app to the network.
EOF
}

say() { printf '%s\n' "$*"; }
fail() {
  printf '%s\n' "$*" >&2
  exit 1
}

# The answer to a question, or its default on Enter or when no one answers.
ask() {
  local answer=""
  printf '%s [%s]: ' "$1" "$2" >&2
  read -r answer || true
  answer=$(printf '%s' "$answer" | tr -d '[:space:]')
  [ -t 0 ] || printf '%s\n' "${answer:-$2}" >&2
  printf '%s' "${answer:-$2}"
}

# Whether the answer to a yes-or-no question is yes, the default.
agrees() {
  local answer=""
  printf '%s [Y/n]: ' "$1" >&2
  read -r answer || true
  [ -t 0 ] || printf '%s\n' "${answer:-y}" >&2
  case $answer in [Nn]*) return 1 ;; esac
}

choose_mode() {
  local answer
  say "How should the AI Startup Co-Founder run?" >&2
  say "  1  Locally: the API with uv and the web app with npm, on this machine" >&2
  say "  2  In Docker: PostgreSQL, the API and the web app in containers" >&2
  while :; do
    answer=$(ask "Run it" 1)
    case $answer in
      1 | local) printf local && return ;;
      2 | docker) printf docker && return ;;
    esac
    say "Answer 1 or 2." >&2
  done
}

is_port() {
  case $1 in '' | *[!0-9]*) return 1 ;; esac
  [ "$1" -ge 1 ] && [ "$1" -le 65535 ]
}

# Whether something on this machine already answers on the port.
in_use() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }

# Whether one of the two servers can have the port: free, and not the other's ($2).
usable() { is_port "$1" && [ "$1" != "${2:-}" ] && ! in_use "$1"; }

# The first port from $1 on that usable allows.
free_from() {
  local port=$1
  until usable "$port" "${2:-}"; do
    port=$((port + 1))
    [ "$port" -le 65535 ] || fail "No port from $1 on is free."
  done
  printf '%s' "$port"
}

# The port for $2 ("the web app"), from $1: asked for when $3 is "ask", and
# whenever the one chosen cannot be had, offering the next free one. $4 is the
# other server's port.
choose_port() {
  local port=$1 what=$2 other=${4:-}
  is_port "$1" || fail "\"$1\" is not a port number, for $what."
  if [ "$3" = ask ] && usable "$port" "$other"; then
    port=$(ask "Port for $what" "$port")
  fi
  until usable "$port" "$other"; do
    if ! is_port "$port"; then
      say "\"$port\" is not a port number." >&2
      port=$1
    elif [ "$port" = "$other" ]; then
      say "Port $port is the web app's." >&2
    else
      say "Port $port is in use." >&2
    fi
    port=$(ask "Port for $what" "$(free_from "$port" "$other")")
  done
  printf '%s' "$port"
}

# .env holds the model's keys and the settings; it starts as .env.example.
need_env() {
  [ -f .env ] && return 0
  say "There is no .env yet: it holds the model's keys and the settings."
  agrees "Make it from .env.example?" || fail "Copy .env.example to .env and fill it in, then run ./start.sh again."
  cp .env.example .env
  fail "Made .env: fill in your Azure OpenAI (or OpenAI) key there, then run ./start.sh again."
}

# Whether .env gives the setting a value, read as Compose reads it: the last
# line for it wins, and " #" starts a comment.
has_setting() {
  grep -E "$SETS$1[[:space:]]*=" .env | tail -n 1 |
    sed -E 's/^[^=]*=//; s/[[:space:]]+#.*$//; s/^[[:space:]]+//; s/[[:space:]]+$//; s/^"(.*)"$/\1/'"; s/^'(.*)'\$/\1/" |
    grep -q .
}

# Sets the setting $1 to $2 in .env: on its line if it has one, else at the end.
put_setting() {
  local copy
  if grep -Eq "$SETS$1[[:space:]]*=" .env; then
    copy=$(mktemp)
    awk -v name="$1" -v value="$2" '
      $0 ~ ("^[ \t]*(export[ \t]+)?" name "[ \t]*=") { print name "=" value; next }
      { print }' .env >"$copy"
    cat "$copy" >.env
    rm -f "$copy"
  else
    [ -z "$(tail -c 1 .env)" ] || printf '\n' >>.env
    printf '%s=%s\n' "$1" "$2" >>.env
  fi
}

# --- Locally ---------------------------------------------------------------

SERVERS=""

# Each line a server writes, under its name, without the terminal codes some
# still send down a pipe (a line of nothing else is left out).
label() {
  awk -v name="$1" '{
    line = $0
    gsub(/\033\[[0-9;?]*[A-Za-z]/, "", line)
    if (line != "" || $0 == "") { print name " | " line; fflush() }
  }'
}

# Whether every process named is still running.
running() {
  local pid
  for pid in "$@"; do kill -0 "$pid" 2>/dev/null || return 1; done
}

# Whether $1 answers within $2 s, while the process $3 runs.
answers() {
  local deadline=$((SECONDS + $2))
  until curl -fs -o /dev/null --max-time 30 "$1"; do
    running "$3" && [ "$SECONDS" -lt "$deadline" ] || return 1
    sleep 1
  done
}

# Every process started from $1, children first.
descendants() {
  local child
  for child in $(pgrep -P "$1" 2>/dev/null || true); do
    descendants "$child"
    printf '%s ' "$child"
  done
}

# Stops the servers, gives them 10 s, stops anything they left, and exits with $1.
stop_local() {
  trap - INT TERM HUP EXIT
  local all="" alive="" pid tries=0
  if [ -n "$SERVERS" ]; then
    for pid in $SERVERS; do all="$all $(descendants "$pid") $pid"; done
    say "" >&2
    say "Stopping the API and the web app..." >&2
    # shellcheck disable=SC2086 # one word per process
    kill -TERM $SERVERS 2>/dev/null || true
    while :; do
      alive=""
      for pid in $all; do
        if kill -0 "$pid" 2>/dev/null; then alive="$alive $pid"; fi
      done
      [ -n "$alive" ] && [ "$tries" -lt 20 ] || break
      sleep 0.5
      tries=$((tries + 1))
    done
    # shellcheck disable=SC2086
    [ -z "$alive" ] || kill -KILL $alive 2>/dev/null || true
  fi
  exit "$1"
}

run_local() {
  local key web
  command -v uv >/dev/null 2>&1 || fail "uv is not installed (https://docs.astral.sh/uv/); or run ./start.sh docker."
  command -v npm >/dev/null 2>&1 || fail "Node.js 20.9 or newer is not installed (https://nodejs.org/); or run ./start.sh docker."
  need_env
  if [ ! -x frontend/node_modules/.bin/next ]; then
    say "Installing the web app's packages..."
    (cd frontend && npm ci)
  fi
  WEB_PORT=$(choose_port "$WEB_PORT" "the web app" "$ASK_PORTS")
  API_PORT=$(choose_port "$API_PORT" "the API" "$ASK_PORTS" "$WEB_PORT")

  say "Starting the API on port $API_PORT..."
  # The key the API reads, for the web app's server to send with each call, so
  # the two match whatever frontend/.env.local says.
  key=$(uv run --quiet python -c 'import sys, config; sys.stdout.write(config.API_KEY)')
  trap 'stop_local 130' INT
  trap 'stop_local 143' TERM
  trap 'stop_local 129' HUP
  trap 'stop_local 1' EXIT
  # No reloader, which would outlive an API that fails to start (uv run python
  # main.py reloads on edits).
  uv run uvicorn main:app --host 127.0.0.1 --port "$API_PORT" > >(label api) 2>&1 &
  SERVERS=$!
  answers "http://127.0.0.1:$API_PORT/health" 180 "$SERVERS" || {
    say "The API did not start: its lines above say why." >&2
    stop_local 1
  }

  say "Starting the web app on port $WEB_PORT..."
  (cd frontend && BACKEND_URL="http://127.0.0.1:$API_PORT" API_KEY="$key" \
    exec ./node_modules/.bin/next dev --hostname "${WEB_HOST:-127.0.0.1}" --port "$WEB_PORT") > >(label web) 2>&1 &
  web=$!
  SERVERS="$SERVERS $web"
  answers "http://127.0.0.1:$WEB_PORT/" 180 "$web" || {
    say "The web app did not start: its lines above say why." >&2
    stop_local 1
  }

  say ""
  say "Running here: open http://localhost:$WEB_PORT (the API's docs are at http://127.0.0.1:$API_PORT/docs)."
  say "Ctrl+C stops both."
  # shellcheck disable=SC2086
  while running $SERVERS; do sleep 1; done
  say "A server stopped: its lines above say why." >&2
  stop_local 1
}

# --- In Docker -------------------------------------------------------------

docker_ready() {
  command -v docker >/dev/null 2>&1 ||
    fail "Docker is not installed (https://www.docker.com/products/docker-desktop/); or run ./start.sh local."
  docker compose version >/dev/null 2>&1 || fail "This needs Docker Compose v2, the docker compose command."
  docker info >/dev/null 2>&1 || fail "Docker is not running: start Docker Desktop, then try again."
}

# The port on this machine that the running service $1 publishes its port $2
# on, else $3.
published() {
  local address
  address=$(docker compose port "$1" "$2" 2>/dev/null || true)
  case $address in
    *:[0-9]*) printf '%s' "${address##*:}" ;;
    *) printf '%s' "$3" ;;
  esac
}

# The database in Docker needs a password: set here or in .env, else made now
# and kept in .env, never shown.
need_password() {
  [ -z "${POSTGRES_PASSWORD:-}" ] || return 0
  has_setting POSTGRES_PASSWORD && return 0
  say "The database in Docker needs a password, kept in .env."
  agrees "Make one and save it there?" || fail "Set POSTGRES_PASSWORD in .env, then run ./start.sh docker again."
  put_setting POSTGRES_PASSWORD "$(od -An -N24 -tx1 /dev/urandom | tr -d ' \n')"
  say "Saved a new POSTGRES_PASSWORD in .env."
}

run_docker() {
  docker_ready
  need_env
  need_password
  if [ -n "$(docker compose ps --quiet --status running 2>/dev/null || true)" ]; then
    WEB_PORT=$(published web 3000 "$WEB_PORT")
    API_PORT=$(published api 8000 "$API_PORT")
    say "It is already running in Docker, on port $WEB_PORT."
    agrees "Build it again from this checkout, and restart it?" || {
      say "Open http://localhost:$WEB_PORT"
      return 0
    }
  else
    WEB_PORT=$(choose_port "$WEB_PORT" "the web app" "$ASK_PORTS")
    API_PORT=$(choose_port "$API_PORT" "the API" "$ASK_PORTS" "$WEB_PORT")
  fi
  export WEB_PORT API_PORT
  say "Building the images and starting the containers; the first build takes a few minutes."
  docker compose up --build --detach --wait || fail "It did not start: docker compose ps and docker compose logs say why."
  say ""
  say "Running in Docker: open http://localhost:$WEB_PORT (the API answers on http://127.0.0.1:$API_PORT)."
  say "Its logs: docker compose logs -f. To stop it: ./start.sh stop."
}

stop_docker() {
  docker_ready
  [ -f .env ] || fail "There is no .env, so nothing was started from here."
  # Compose reads the password even to stop; it is not needed for that.
  if [ -z "${POSTGRES_PASSWORD:-}" ] && ! has_setting POSTGRES_PASSWORD; then
    export POSTGRES_PASSWORD=unused
  fi
  docker compose down
  say "Stopped. The database's data stays in its volume; docker compose down --volumes deletes it."
}

main() {
  local mode=""
  cd "$(dirname "$0")"
  WEB_PORT=${WEB_PORT:-3000}
  API_PORT=${API_PORT:-8000}
  ASK_PORTS=keep
  while [ $# -gt 0 ]; do
    case $1 in
      local | docker | stop)
        [ -z "$mode" ] || {
          usage >&2
          exit 2
        }
        mode=$1
        ;;
      --web-port | --api-port)
        [ $# -ge 2 ] || fail "$1 needs a port number."
        if [ "$1" = --web-port ]; then WEB_PORT=$2; else API_PORT=$2; fi
        shift
        ;;
      --web-port=*) WEB_PORT=${1#*=} ;;
      --api-port=*) API_PORT=${1#*=} ;;
      -h | --help | help)
        usage
        exit 0
        ;;
      *)
        usage >&2
        exit 2
        ;;
    esac
    shift
  done
  if [ -z "$mode" ]; then
    mode=$(choose_mode)
    ASK_PORTS=ask
  fi
  case $mode in
    local) run_local ;;
    docker) run_docker ;;
    stop) stop_docker ;;
  esac
}

# Run, unless sourced: the tests call the functions.
if [ "${BASH_SOURCE[0]}" = "$0" ]; then main "$@"; fi
