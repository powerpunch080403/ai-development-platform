# Server

App-managed Local Runtime의 FastAPI server skeleton이다.

현재 구현은 `GET /health`만 제공한다. Local Control Plane, SQLite migration, Tool Contract, Worker Supervisor와 pairing/session은 후속 Slice에서 구현한다.

```powershell
uv sync --project apps/server
uv run --project apps/server fastapi dev apps/server/src/aidp_server/main.py
uv run --project apps/server pytest apps/server/tests
```
