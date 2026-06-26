from fastapi import FastAPI

from app.health.router import router as health_router


def create_app() -> FastAPI:
    app = FastAPI(title="Schatten API")
    app.include_router(health_router)
    return app


app = create_app()
