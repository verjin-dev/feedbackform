import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    accounts,
    assignments,
    auth,
    evaluations,
    exports,
    participation,
    reference,
    reports,
)
from app.core.config import get_settings

settings = get_settings()

# Uvicorn configures its own loggers but leaves the root logger at WARNING, so
# anything the application logs is dropped. That matters most for the console
# mail backend, which exists precisely to be seen: without this, an unconfigured
# deployment prints nothing at all, which is the silent failure the backend is
# supposed to replace. basicConfig is a no-op when handlers already exist.
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

if settings.is_production and settings.secret_key == "insecure-local-only-key":
    raise RuntimeError(
        "SECRET_KEY must be set outside local development. Refusing to start "
        "with the built-in placeholder."
    )

app = FastAPI(
    title="Faculty Evaluation API",
    version="0.1.0",
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth.router)
app.include_router(reference.router)
app.include_router(accounts.router)
app.include_router(assignments.router)
app.include_router(evaluations.router)
app.include_router(reports.router)
app.include_router(participation.router)
app.include_router(exports.router)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}
