from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any

from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from aidp_server.audit import record_audit_event
from aidp_server.config import Settings
from aidp_server.db.models import (
    RecordStatus,
    ToolCall,
    ToolCallerType,
    ToolCallStatus,
    WorkerRun,
    utc_now,
)
from aidp_server.db.session import get_session_factory
from aidp_server.worker_liveness import recover_stale_worker_runs


def run_worker_liveness_tick(
    session: Session,
    *,
    settings: Settings,
    trigger: str = "scheduler_tick",
) -> dict[str, Any]:
    now = utc_now()
    user_ids = session.scalars(
        select(WorkerRun.local_user_id)
        .where(WorkerRun.status == RecordStatus.RUNNING)
        .distinct()
    ).all()

    recovered_count = 0
    tool_call_ids: list[str] = []

    for local_user_id in user_ids:
        tool_call = ToolCall(
            tool_name="worker.recover_stale_runs",
            tool_version="1.0",
            tool_category="worker",
            caller_type=ToolCallerType.SYSTEM,
            caller_id="worker_liveness.scheduler",
            user_id=local_user_id,
            risk_level="R1",
            arguments_json={
                "timeout_seconds": settings.worker_run_stale_timeout_seconds,
                "trigger": trigger,
            },
            status=ToolCallStatus.RUNNING,
            started_at=now,
        )
        session.add(tool_call)
        session.flush()

        result = recover_stale_worker_runs(
            session,
            tool_call=tool_call,
            now=now,
            timeout_seconds=settings.worker_run_stale_timeout_seconds,
        )

        if tool_call.status is not ToolCallStatus.FAILED:
            tool_call.status = ToolCallStatus.SUCCEEDED
        tool_call.result_json = result
        tool_call.completed_at = utc_now()
        tool_call_ids.append(tool_call.id)

        recovered_for_user = int(result.get("recovered_count", 0))
        recovered_count += recovered_for_user

        record_audit_event(
            session,
            event_type="worker_liveness.tick",
            message="Worker liveness tick completed",
            local_user_id=local_user_id,
            tool_call_id=tool_call.id,
            metadata={
                "trigger": trigger,
                "running_user_count": len(user_ids),
                "recovered_count": recovered_for_user,
                "scheduler_enabled": settings.enable_worker_liveness_scheduler,
            },
        )

    session.flush()

    return {
        "status": "succeeded",
        "trigger": trigger,
        "running_user_count": len(user_ids),
        "recovered_count": recovered_count,
        "tool_call_ids": tool_call_ids,
    }


class WorkerLivenessScheduler:
    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory or get_session_factory()
        self._task: asyncio.Task[None] | None = None
        self._tick_running = False

    @property
    def enabled(self) -> bool:
        return self.settings.enable_worker_liveness_scheduler

    def start_background(self) -> None:
        if not self.enabled:
            return
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._run_forever())

    async def stop(self) -> None:
        if not self._task:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def tick_once(self, *, trigger: str = "scheduler_tick") -> dict[str, Any]:
        if self._tick_running:
            return {
                "status": "skipped",
                "reason": "tick_already_running",
                "trigger": trigger,
            }

        self._tick_running = True
        try:
            with self.session_factory() as session:
                result = run_worker_liveness_tick(
                    session,
                    settings=self.settings,
                    trigger=trigger,
                )
                session.commit()
                return result
        finally:
            self._tick_running = False

    async def _run_forever(self) -> None:
        interval = max(1, self.settings.worker_liveness_scheduler_interval_seconds)
        while True:
            await asyncio.sleep(interval)
            try:
                await self.tick_once()
            except Exception:
                # Keep the loop alive; individual failures are visible through app logs.
                # A later scheduler PR can promote this to structured scheduler health state.
                continue


def configure_worker_liveness_scheduler(app: FastAPI, settings: Settings) -> None:
    scheduler = WorkerLivenessScheduler(settings=settings)
    app.state.worker_liveness_scheduler = scheduler

    async def _startup() -> None:
        scheduler.start_background()

    async def _shutdown() -> None:
        await scheduler.stop()

    app.router.on_startup.append(_startup)
    app.router.on_shutdown.append(_shutdown)
