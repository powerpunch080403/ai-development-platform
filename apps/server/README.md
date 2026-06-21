# Server

App-managed Local Runtime의 FastAPI server skeleton이다.

현재 구현은 `GET /health`만 제공한다. Local Control Plane, SQLite migration, Tool Contract, Worker Supervisor와 pairing/session은 후속 Slice에서 구현한다. `python -m aidp_server.main`은 application object를 import하고 종료할 뿐 개발 server를 실행하지 않으므로 uvicorn을 사용한다.

## Windows PowerShell

```powershell
cd apps/server
uv sync
uv run pytest
uv run uvicorn aidp_server.main:app --reload --host 127.0.0.1 --port 8000
```

저장소 루트에서 실행한다면 다음처럼 `--project`를 사용한다.

```powershell
uv sync --project apps/server
uv run --project apps/server pytest
uv run --project apps/server uvicorn aidp_server.main:app --reload --host 127.0.0.1 --port 8000
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

## Linux/macOS

명령 구조는 동일하며 health 확인에는 curl을 사용할 수 있다.

```bash
cd apps/server
uv sync
uv run pytest
uv run uvicorn aidp_server.main:app --reload --host 127.0.0.1 --port 8000
curl http://127.0.0.1:8000/health
```

응답:

```json
{"status":"ok","service":"aidp-server"}
```

## 환경 변수

`AIDP_ENV`, `AIDP_HOST`, `AIDP_PORT`, `AIDP_APP_DATA_DIR`, `AIDP_DATABASE_URL`, `AIDP_WEB_ORIGIN`을 지원하는 config skeleton이 있다. 예시는 루트 `.env.example`을 참고한다. 실제 `.env`, token, database와 runtime data는 commit하지 않는다.
