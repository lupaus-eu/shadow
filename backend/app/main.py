from fastapi import FastAPI

from app.api.v1.router import router as api_v1_router
from app.health.router import router as health_router


def create_app() -> FastAPI:
    app = FastAPI(title="Schatten API")
    app.include_router(health_router)
    app.include_router(api_v1_router)
    return app


app = create_app()
