from fastapi import FastAPI
from app.api.routes import router

app = FastAPI(
    title="Digital Twin Agent",
    version="0.1.0",
)

app.include_router(router)