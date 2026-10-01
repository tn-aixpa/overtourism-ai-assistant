import os
from pathlib import Path
from dotenv import load_dotenv
import logging
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

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
