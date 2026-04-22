import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="Digital Twin Agent",
    version="0.1.0",
)

#TODO: Restrict CORS in production
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_methods=["*"],
#     allow_headers=["*"],
#     allow_credentials=True,
# )
app.add_middleware(
    CORSMiddleware,
    # Coder workspaces run frontend/backend on sibling subdomains (e.g. 3000--... and 9000--...).
    # We allow those origins and enable credentials for authenticated cross-origin requests.
    allow_origins=[],
    allow_origin_regex=r"https://\d+--.*\.coder\.most\.atlas\.fbk\.eu",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)