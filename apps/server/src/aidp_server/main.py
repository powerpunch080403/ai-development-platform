from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from aidp_server.auth import router as auth_router
from aidp_server.config import get_settings
from aidp_server.devices import router as devices_router
from aidp_server.health import router as health_router
from aidp_server.projects import router as projects_router
from aidp_server.conversations import router as conversations_router
from aidp_server.tool_calls import router as tool_calls_router
from aidp_server.process_runs import router as process_runs_router
from aidp_server.work import router as work_router
from aidp_server.task_workspace import router as task_workspace_router
from aidp_server.worktrees import router as worktrees_router
from aidp_server.reviews import router as reviews_router
from aidp_server.system import router as system_router
from aidp_server.approval_routes import router as approvals_router
from aidp_server.external_cli_adapters import router as external_cli_adapters_router
from aidp_server.settings import router as settings_router


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
    app.include_router(projects_router)
    app.include_router(conversations_router)
    app.include_router(tool_calls_router)
    app.include_router(process_runs_router)
    app.include_router(work_router)
    app.include_router(task_workspace_router)
    app.include_router(worktrees_router)
    app.include_router(reviews_router)
    app.include_router(approvals_router)
    app.include_router(external_cli_adapters_router)
    app.include_router(settings_router)
    return app


app = create_app()
