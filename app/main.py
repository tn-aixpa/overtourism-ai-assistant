from fastapi import FastAPI
from app.api.routes import router
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="Digital Twin Agent",
    version="0.1.0",
)

app.include_router(router)