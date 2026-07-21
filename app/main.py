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


from app.config import validate_environment

# Fail fast: if required config (BACKEND_URL, ANTHROPIC_API_KEY, ...) is
# missing, stop here with a clear error instead of booting successfully and
# failing deep inside the first request that needs it.
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