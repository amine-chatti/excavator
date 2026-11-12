from __future__ import annotations

from fastapi import FastAPI

from excavator.api.routes.health import router as health_router
from excavator.config import Settings
from excavator.logging import configure_logging


def create_app() -> FastAPI:
    settings = Settings()
    configure_logging(settings)

    app = FastAPI(title="Excavator")
    app.include_router(health_router)
    return app
