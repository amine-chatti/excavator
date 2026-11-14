from __future__ import annotations

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from excavator.api.routes.analysis import router as analysis_router
from excavator.api.routes.health import router as health_router
from excavator.api.routes.repositories import router as repositories_router
from excavator.api.routes.symbols import router as symbols_router
from excavator.config import Settings
from excavator.logging import configure_logging


def create_app() -> FastAPI:
    settings = Settings()
    configure_logging(settings)

    app = FastAPI(title="Excavator")
    app.state.settings = settings
    app.include_router(health_router)
    app.include_router(repositories_router)
    app.include_router(analysis_router)
    app.include_router(symbols_router)

    @app.exception_handler(RequestValidationError)
    def validation_error_handler(
        _request: object,
        _exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": "invalid request"})

    return app
