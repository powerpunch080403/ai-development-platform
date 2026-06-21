from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from aidp_server.auth import router as auth_router
from aidp_server.config import get_settings
from aidp_server.devices import router as devices_router
from aidp_server.health import router as health_router
from aidp_server.system import router as system_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="AI Development Platform", version="0.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.include_router(health_router)
    app.include_router(system_router)
    app.include_router(auth_router)
    app.include_router(devices_router)
    return app


app = create_app()
