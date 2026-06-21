from fastapi import FastAPI

from aidp_server.health import router as health_router


def create_app() -> FastAPI:
    app = FastAPI(title="AI Development Platform", version="0.0.0")
    app.include_router(health_router)
    return app


app = create_app()
