import os
from pathlib import Path
from dotenv import load_dotenv
import logging

# Load environment variables from the project .env file if present. This must
# happen before logging is configured below: LOG_LEVEL (and the other switches
# in app.utils.settings) may live in .env. Real environment variables (docker
# -e, run.sh exports) always win over .env (override=False).
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path, override=False)
else:
    load_dotenv(override=False)

from app.utils.settings import configured_log_level, save_conversation_logs_enabled

# Console verbosity: LOG_LEVEL (DEBUG/INFO/WARNING/ERROR/CRITICAL), INFO if unset.
# A typo must not stop the service from starting: fall back to INFO and say so
# once logging is up (see _log_level_error below).
_log_level_error = None
try:
    _requested_log_level = configured_log_level()
except ValueError as exc:
    _requested_log_level = None
    _log_level_error = str(exc)
LOG_LEVEL = _requested_log_level if _requested_log_level is not None else logging.INFO

# Chatty client libraries log whole request/response payloads (prompts included)
# at DEBUG; keep them at INFO so LOG_LEVEL=DEBUG shows the app's own detail.
_NOISY_LOGGERS = ("httpcore", "hpack", "anthropic", "openai")

if os.environ.get("LOG_CONFIG_FILE") is None:
    LOG_FORMAT = (
        "%(asctime)s.%(msecs)03d [%(threadName)s] %(levelname)-5s "
        "%(name)s.%(funcName)s - %(message)s"
    )
    LOG_DATE_FORMAT = "%d-%m-%Y %H:%M:%S"

    logging.basicConfig(
        level=LOG_LEVEL,
        format=LOG_FORMAT,
        datefmt=LOG_DATE_FORMAT,
        force=True,
    )

    # Uvicorn configures its own handlers, so update those formatters (and
    # their level, so LOG_LEVEL also governs request/access lines) as well.
    uvicorn_formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.setLevel(LOG_LEVEL)
        for handler in uvicorn_logger.handlers:
            handler.setFormatter(uvicorn_formatter)

    for logger_name in _NOISY_LOGGERS:
        logging.getLogger(logger_name).setLevel(max(LOG_LEVEL, logging.INFO))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


# ---------------------------------------------------------------------------
# STARTUP VALIDATION
# ---------------------------------------------------------------------------
# Config the app cannot function without.
REQUIRED_ENV_VARS = ["BACKEND_URL"]


def validate_environment() -> None:
    missing = [name for name in REQUIRED_ENV_VARS if not os.environ.get(name)]
    if missing:
        raise RuntimeError(
            "Missing required environment variable(s): "
            f"{', '.join(missing)}. Set them (e.g. in .env) before starting the app."
        )


validate_environment()

from app.api.routes import router

app = FastAPI(
    title="Digital Twin Agent",
    version="0.1.0",
)

# Local setting
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(router)

if os.environ.get("LOG_CONFIG_FILE") is not None:
    from app.utils.logging_utils import setup_tracing

    setup_tracing(app)

    # The logging config file (applied when logging_utils is imported) owns the
    # handlers and formats. An explicit LOG_LEVEL still sets the verbosity, and
    # it must be applied here, after that file has been loaded.
    if _requested_log_level is not None:
        logging.getLogger().setLevel(_requested_log_level)
        for _name in _NOISY_LOGGERS:
            logging.getLogger(_name).setLevel(max(_requested_log_level, logging.INFO))

if _log_level_error is not None:
    logging.getLogger(__name__).warning(
        f"{_log_level_error}; falling back to INFO"
    )
logging.getLogger(__name__).info(
    f"Console log level: {logging.getLevelName(logging.getLogger().getEffectiveLevel())}; "
    f"conversation logs in logs/: "
    f"{'enabled' if save_conversation_logs_enabled() else 'disabled'}"
)
