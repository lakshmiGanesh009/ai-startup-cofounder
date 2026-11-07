"""Tests for the launcher (start.sh): the question of how to run the app, the
ports it offers, what it says when a tool is missing, and how it edits .env.
Its functions run on their own, from the script sourced into bash; starting
the servers and the containers is checked live."""

import os
import re
import shutil
import socket
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "start.sh"
BASH = shutil.which("bash") or ""  # "" when there is none: the tests below are then skipped
# Settings the launcher takes from the environment; CI sets POSTGRES_PASSWORD.
OWN = ("POSTGRES_PASSWORD", "WEB_PORT", "API_PORT", "WEB_HOST")

pytestmark = pytest.mark.skipif(not BASH, reason="the launcher needs bash")


def run(code, cwd, answers="", **env):
    """Runs `code` in bash with the launcher's functions loaded, in `cwd`, with
    `answers` typed in (none: every question takes its default)."""
    environment = {name: value for name, value in os.environ.items() if name not in OWN} | env
    return subprocess.run(
        [BASH, "-c", f'source "$1"; {code}', "bash", str(SCRIPT)],
        cwd=cwd, input=answers, capture_output=True, text=True, timeout=30, env=environment,
    )


def free_port(but=None):
    while True:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        if port != but:
            return port


@pytest.fixture
def taken():
    """A port something listens on."""
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        yield server.getsockname()[1]


def test_help_and_a_wrong_command():
    shown = subprocess.run([BASH, str(SCRIPT), "--help"], capture_output=True, text=True, timeout=30)
    wrong = subprocess.run([BASH, str(SCRIPT), "deploy"], capture_output=True, text=True, timeout=30)
    assert shown.returncode == 0 and shown.stdout.startswith("Usage: ./start.sh [local | docker | stop]")
    assert wrong.returncode == 2 and wrong.stderr.startswith("Usage:") and not wrong.stdout


@pytest.mark.parametrize(
    ("answers", "mode"),
    [("", "local"), ("\n", "local"), ("2\n", "docker"), ("docker\n", "docker"), ("x\n1\n", "local")],
)
def test_the_question_of_how_to_run_it(tmp_path, answers, mode):
    done = run("choose_mode", tmp_path, answers)
    assert done.stdout == mode
    assert "1  Locally" in done.stderr and "2  In Docker" in done.stderr
    assert ("Answer 1 or 2." in done.stderr) == answers.startswith("x")


def test_a_free_port_is_kept_without_asking(tmp_path):
    port = free_port()
    done = run(f"choose_port {port} 'the web app' keep", tmp_path)
    assert done.stdout == str(port) and not done.stderr


def test_a_port_in_use_is_asked_about_offering_the_next_free_one(tmp_path, taken):
    done = run(f"choose_port {taken} 'the web app' keep", tmp_path)
    offered = re.search(r"Port for the web app \[(\d+)\]", done.stderr)
    assert f"Port {taken} is in use." in done.stderr
    assert offered and int(offered[1]) > taken and done.stdout == offered[1]


def test_a_port_can_be_chosen_when_asked(tmp_path):
    first = free_port()
    second = free_port(but=first)
    done = run(f"choose_port {first} 'the web app' ask", tmp_path, f"{second}\n")
    assert done.stdout == str(second) and f"Port for the web app [{first}]: {second}" in done.stderr


def test_a_wrong_answer_is_asked_again(tmp_path):
    port = free_port()
    done = run(f"choose_port {port} 'the API' ask", tmp_path, "eighty\n\n")
    assert '"eighty" is not a port number.' in done.stderr and done.stdout == str(port)


def test_the_api_cannot_have_the_web_apps_port(tmp_path):
    port = free_port()
    done = run(f"choose_port {port} 'the API' keep {port}", tmp_path)
    assert f"Port {port} is the web app's." in done.stderr and int(done.stdout) > port


def test_a_port_that_is_no_number_stops_it(tmp_path):
    done = run("choose_port 80a 'the web app' keep", tmp_path)
    assert done.returncode == 1 and '"80a" is not a port number, for the web app.' in done.stderr


@pytest.mark.parametrize(
    ("command", "says"),
    [("local", "uv is not installed"), ("docker", "Docker is not installed")],
)
def test_a_missing_tool_is_named_with_the_other_way_to_run_it(tmp_path, command, says):
    tools = tmp_path / "bin"
    tools.mkdir()
    (tools / "dirname").symlink_to(shutil.which("dirname"))
    done = subprocess.run([BASH, str(SCRIPT), command], env={"PATH": str(tools)},
                          capture_output=True, text=True, timeout=30)
    other = "docker" if command == "local" else "local"
    assert done.returncode == 1 and says in done.stderr and f"./start.sh {other}" in done.stderr


def test_docker_not_running_is_named(tmp_path):
    tools = tmp_path / "bin"
    tools.mkdir()
    (tools / "dirname").symlink_to(shutil.which("dirname"))
    docker = tools / "docker"
    docker.write_text('#!/bin/sh\n[ "$1" = compose ] && exit 0\nexit 1\n')  # compose there, the daemon not
    docker.chmod(0o755)
    done = subprocess.run([BASH, str(SCRIPT), "docker"], env={"PATH": str(tools)},
                          capture_output=True, text=True, timeout=30)
    assert done.returncode == 1 and "Docker is not running: start Docker Desktop" in done.stderr


def test_without_env_it_offers_to_make_one_from_the_example(tmp_path):
    (tmp_path / ".env.example").write_text("AZURE_OPENAI_API_KEY=your-key\n")
    refused = run("need_env", tmp_path, "n\n")
    assert refused.returncode == 1 and "Copy .env.example to .env" in refused.stderr
    assert not (tmp_path / ".env").exists()
    made = run("need_env", tmp_path)
    assert made.returncode == 1 and "fill in your Azure OpenAI (or OpenAI) key there" in made.stderr
    assert (tmp_path / ".env").read_text() == "AZURE_OPENAI_API_KEY=your-key\n"
    assert run("need_env", tmp_path).returncode == 0


@pytest.mark.parametrize(
    ("lines", "has_it"),
    [
        ("", False),
        ("POSTGRES_PASSWORD=\n", False),
        ('POSTGRES_PASSWORD=""\n', False),
        ("POSTGRES_PASSWORD=   # a comment\n", False),
        ("POSTGRES_PASSWORD_FILE=/run/secret\n", False),
        ("POSTGRES_PASSWORD=abc\nPOSTGRES_PASSWORD=\n", False),
        ("POSTGRES_PASSWORD=abc\n", True),
        ("export POSTGRES_PASSWORD=abc\n", True),
        ("POSTGRES_PASSWORD = 'abc'  # quoted\n", True),
    ],
)
def test_whether_env_gives_a_setting_a_value(tmp_path, lines, has_it):
    (tmp_path / ".env").write_text("A=1\n" + lines)
    assert (run("has_setting POSTGRES_PASSWORD", tmp_path).returncode == 0) is has_it


def test_a_setting_goes_on_its_line_and_nothing_else_changes(tmp_path):
    env = tmp_path / ".env"
    before = "# The database\nPOSTGRES_PASSWORD=\nPOSTGRES_PASSWORD_FILE=keep\nAZURE_OPENAI_API_KEY=k  # mine\n"
    env.write_text(before)
    env.chmod(0o600)
    run("put_setting POSTGRES_PASSWORD abc123", tmp_path)
    assert env.read_text() == before.replace("POSTGRES_PASSWORD=\n", "POSTGRES_PASSWORD=abc123\n")
    assert env.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("ending", ["\n", ""])
def test_a_missing_setting_goes_at_the_end(tmp_path, ending):
    (tmp_path / ".env").write_text("A=1" + ending)
    run("put_setting POSTGRES_PASSWORD abc123", tmp_path)
    assert (tmp_path / ".env").read_text() == "A=1\nPOSTGRES_PASSWORD=abc123\n"


def test_the_database_password_is_made_kept_in_env_and_never_shown(tmp_path):
    env = tmp_path / ".env"
    env.write_text("A=1\nPOSTGRES_PASSWORD=\nB=2\n")
    env.chmod(0o600)
    done = run("need_password", tmp_path)
    first, line, last = env.read_text().splitlines()
    password = line.removeprefix("POSTGRES_PASSWORD=")
    assert done.returncode == 0 and (first, last) == ("A=1", "B=2")
    assert re.fullmatch(r"[0-9a-f]{48}", password)
    assert password not in done.stdout + done.stderr and "Saved a new POSTGRES_PASSWORD" in done.stdout
    assert env.stat().st_mode & 0o777 == 0o600
    again = run("need_password", tmp_path)
    assert again.returncode == 0 and not again.stdout and env.read_text().splitlines()[1] == line


def test_no_password_is_made_when_one_is_given_or_it_is_refused(tmp_path):
    env = tmp_path / ".env"
    env.write_text("A=1\n")
    given = run("need_password", tmp_path, POSTGRES_PASSWORD="from-the-shell")
    refused = run("need_password", tmp_path, "n\n")
    assert given.returncode == 0 and not given.stdout
    assert refused.returncode == 1 and "Set POSTGRES_PASSWORD in .env" in refused.stderr
    assert env.read_text() == "A=1\n"
