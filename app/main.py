import os
from pathlib import Path
from dotenv import load_dotenv
import logging

LOG_FORMAT = (
    "%(asctime)s.%(msecs)03d [%(threadName)s] %(levelname)-5s "
    "%(name)s.%(funcName)s - %(message)s"
)
LOG_DATE_FORMAT = "%d-%m-%Y %H:%M:%S"

logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    datefmt=LOG_DATE_FORMAT,
    force=True,
)

# Uvicorn configures its own handlers, so update those formatters as well.
uvicorn_formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
    for handler in logging.getLogger(logger_name).handlers:
        handler.setFormatter(uvicorn_formatter)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load environment variables from the project .env file if present
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path, override=False)
else:
    load_dotenv(override=False)


# ---------------------------------------------------------------------------
# STARTUP VALIDATION
# ---------------------------------------------------------------------------
# Config the app cannot function without.
REQUIRED_ENV_VARS = ["BACKEND_URL", "ANTHROPIC_API_KEY"]


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
