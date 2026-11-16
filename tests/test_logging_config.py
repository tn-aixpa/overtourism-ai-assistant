"""LOG_LEVEL applied at startup by app.main, and the DEBUG-level payload logs.

app.main configures logging as an import side effect (basicConfig(force=True)
replaces the root handlers), so the startup checks run in a fresh interpreter
instead of reloading the module inside the pytest process.
"""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

PROBE = """
import json, logging, sys
sys.path.insert(0, {root!r})
import app.main
lv = lambda n: logging.getLevelName(logging.getLogger(n).level)
print(json.dumps({{
    "root": lv(""),
    "uvicorn": lv("uvicorn"),
    "uvicorn.error": lv("uvicorn.error"),
    "uvicorn.access": lv("uvicorn.access"),
    "httpcore": lv("httpcore"),
    "anthropic": lv("anthropic"),
    "openai": lv("openai"),
}}))
"""


def start_app(tmp_path, **env):
    """Import app.main in a clean interpreter; returns (levels, stderr)."""
    child_env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in (
            "LOG_LEVEL",
            "SAVE_CONVERSATION_LOGS",
            "LOG_CONFIG_FILE",
            "ANTHROPIC_API_KEY",
            "AZURE_API_KEY",
        )
    }
    child_env.update(BACKEND_URL="http://backend.test/")
    child_env.update(env)
    done = subprocess.run(
        [sys.executable, "-I", "-c", PROBE.format(root=str(ROOT))],
        cwd=tmp_path,  # no .env next to the cwd, no logs/ in the repo
        env=child_env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1]), done.stderr


def make_minimal_project(tmp_path, dotenv):
    """A copy of app/main.py + settings.py with a stub router and a .env next to
    it (app.main looks for the .env one directory above app/)."""
    project = tmp_path / "project"
    (project / "app" / "utils").mkdir(parents=True)
    (project / "app" / "api").mkdir()
    (project / "app" / "__init__.py").write_text("")
    (project / "app" / "api" / "__init__.py").write_text("")
    (project / "app" / "api" / "routes.py").write_text(
        "from fastapi import APIRouter\nrouter = APIRouter()\n"
    )
    (project / "app" / "main.py").write_text((ROOT / "app" / "main.py").read_text())
    (project / "app" / "utils" / "settings.py").write_text(
        (ROOT / "app" / "utils" / "settings.py").read_text()
    )
    (project / ".env").write_text(dotenv)
    return project


def root_level_of(project, cwd, **env):
    probe = (
        "import logging, sys\n"
        f"sys.path.insert(0, {str(project)!r})\n"
        "import app.main\n"
        "print(logging.getLevelName(logging.getLogger().level))\n"
    )
    child_env = {k: v for k, v in os.environ.items() if k != "LOG_LEVEL"}
    child_env.update(BACKEND_URL="http://backend.test/", **env)
    done = subprocess.run(
        [sys.executable, "-I", "-c", probe],
        cwd=cwd, env=child_env, capture_output=True, text=True, timeout=120,
    )
    assert done.returncode == 0, done.stderr
    return done.stdout.strip().splitlines()[-1]


class TestLogLevelAtStartup:
    def test_default_is_info(self, tmp_path):
        levels, _ = start_app(tmp_path)

        assert levels["root"] == "INFO"
        assert levels["uvicorn"] == levels["uvicorn.access"] == "INFO"

    @pytest.mark.parametrize("value", ["DEBUG", "debug", "WARNING", "ERROR", "CRITICAL"])
    def test_level_applies_to_app_and_uvicorn_loggers(self, tmp_path, value):
        levels, _ = start_app(tmp_path, LOG_LEVEL=value)

        expected = value.upper()
        assert levels["root"] == expected
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
            assert levels[name] == expected

    def test_chatty_client_libraries_stay_at_info_in_debug(self, tmp_path):
        levels, _ = start_app(tmp_path, LOG_LEVEL="DEBUG")

        assert levels["root"] == "DEBUG"
        for name in ("httpcore", "anthropic", "openai"):
            assert levels[name] == "INFO"

    def test_quiet_levels_apply_to_client_libraries_too(self, tmp_path):
        levels, _ = start_app(tmp_path, LOG_LEVEL="ERROR")

        for name in ("httpcore", "anthropic", "openai"):
            assert levels[name] == "ERROR"

    def test_invalid_level_falls_back_to_info_and_warns(self, tmp_path):
        levels, stderr = start_app(tmp_path, LOG_LEVEL="loud")

        assert levels["root"] == "INFO"
        assert "Invalid LOG_LEVEL 'loud'" in stderr
        assert "falling back to INFO" in stderr

    def test_level_can_come_from_dotenv(self, tmp_path):
        # .env is loaded before logging is configured, so it can set LOG_LEVEL.
        project = make_minimal_project(tmp_path, dotenv="LOG_LEVEL=WARNING\n")

        assert root_level_of(project, tmp_path) == "WARNING"

    def test_real_environment_wins_over_dotenv(self, tmp_path):
        project = make_minimal_project(tmp_path, dotenv="LOG_LEVEL=WARNING\n")

        assert root_level_of(project, tmp_path, LOG_LEVEL="DEBUG") == "DEBUG"

    def test_startup_line_reports_the_switches(self, tmp_path):
        _, stderr = start_app(tmp_path, LOG_LEVEL="INFO", SAVE_CONVERSATION_LOGS="true")
        assert "Console log level: INFO" in stderr
        assert "conversation logs in logs/: enabled" in stderr

        _, stderr = start_app(tmp_path)
        assert "conversation logs in logs/: disabled" in stderr


class TestPayloadLogsAreDebugOnly:
    """The one-line progress messages stay at INFO; the large payloads
    (backend bodies, user replies) only appear when LOG_LEVEL=DEBUG."""

    def test_backend_response_body_is_debug(self, caplog):
        from unittest.mock import MagicMock

        from app.utils import backend_utils

        response = MagicMock(status_code=200)
        response.json.return_value = {"secret": "PAYLOAD"}

        with caplog.at_level(logging.INFO, logger=backend_utils.logger.name):
            backend_utils._log_response(response)
        assert "Response status: 200" in caplog.text
        assert "PAYLOAD" not in caplog.text

        caplog.clear()
        with caplog.at_level(logging.DEBUG, logger=backend_utils.logger.name):
            backend_utils._log_response(response)
        assert "PAYLOAD" in caplog.text

    def test_non_json_backend_body_is_debug(self, caplog):
        from unittest.mock import MagicMock

        from app.utils import backend_utils

        response = MagicMock(status_code=500, text="RAW-TEXT")
        response.json.side_effect = ValueError("not json")

        with caplog.at_level(logging.INFO, logger=backend_utils.logger.name):
            backend_utils._log_response(response)
        assert "Response status: 500" in caplog.text
        assert "RAW-TEXT" not in caplog.text

        with caplog.at_level(logging.DEBUG, logger=backend_utils.logger.name):
            backend_utils._log_response(response)
        assert "RAW-TEXT" in caplog.text
