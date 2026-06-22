# Server

App-managed Local Runtime의 FastAPI server skeleton이다.

현재 구현은 기존 기록 계층 위에 Work Item/Task/Task Attempt와 Worker registry/claim lease를 제공한다. 실제 Owner 모델과 Worker process는 아직 구현하지 않았다. `python -m aidp_server.main`은 개발 server를 실행하지 않으므로 uvicorn을 사용한다.

## Windows PowerShell

```powershell
cd apps/server
uv sync
uv run alembic upgrade head
uv run python -m aidp_server.cli auth pairing-code
uv run pytest
uv run uvicorn aidp_server.main:app --reload --host 127.0.0.1 --port 8000
```

저장소 루트에서 실행한다면 다음처럼 `--project`를 사용한다.

```powershell
uv sync --project apps/server
uv run --project apps/server alembic upgrade head
uv run --project apps/server python -m aidp_server.cli auth pairing-code
uv run --project apps/server pytest
uv run --project apps/server uvicorn aidp_server.main:app --reload --host 127.0.0.1 --port 8000
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/system/status
```

## Linux/macOS

명령 구조는 동일하며 health 확인에는 curl을 사용할 수 있다.

```bash
cd apps/server
uv sync
uv run alembic upgrade head
uv run python -m aidp_server.cli auth pairing-code
uv run pytest
uv run uvicorn aidp_server.main:app --reload --host 127.0.0.1 --port 8000
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/system/status
```

응답:

```json
{"status":"ok","service":"aidp-server"}
```

## 환경 변수

`AIDP_ENV`, `AIDP_HOST`, `AIDP_PORT`, `AIDP_APP_DATA_DIR`, `AIDP_DATABASE_URL`, `AIDP_WEB_ORIGIN`을 지원한다. 예시는 루트 `.env.example`을 참고한다. 실제 `.env`, token, database와 runtime data는 commit하지 않는다. CORS는 `AIDP_WEB_ORIGIN` 한 곳만 허용하고 credentials를 사용하므로 Web UI 주소와 정확히 일치해야 한다.

`AIDP_APP_DATA_DIR` 기본값은 `./runtime-data`다. `AIDP_DATABASE_URL`을 생략하면 `<app-data-dir>/aidev.sqlite3`를 사용한다. Schema 변경은 `Base.metadata.create_all()`이 아니라 Alembic migration으로 수행한다.

## Pairing과 session API

`python -m aidp_server.cli auth pairing-code`는 10분 유효한 `web_ui` code를 원문으로 한 번 표시한다. 원문 code와 session token은 로그나 DB에 저장하지 않는다. 다음 endpoint를 제공한다.

- `POST /auth/pair`: code를 한 번 사용하고 Web UI device/session을 만든 뒤 HttpOnly cookie 설정
- `GET /auth/me`: 현재 user/device/session 조회; 인증 실패는 `401`
- `POST /auth/logout`: 현재 session 폐기와 cookie 삭제
- `GET /devices`, `GET /sessions`: 현재 local user 범위 조회
- `POST /sessions/{id}/revoke`, `POST /devices/{id}/revoke`: session 또는 device 폐기

Device 폐기는 해당 device의 활성 session도 함께 폐기한다. 개발 환경 cookie는 HTTP localhost에서 동작하며 production 환경에서는 Secure cookie가 설정되므로 HTTPS가 필요하다.

## Project와 repository API

모든 endpoint는 인증된 local session을 요구하고 현재 local user 범위로 제한한다.

- `POST /projects`, `GET /projects`, `GET /projects/{id}`
- `POST /projects/{id}/repositories`, `GET /projects/{id}/repositories`
- `GET /repositories/{id}/status`: DB에 저장된 마지막 status
- `POST /repositories/{id}/refresh-status`: 실제 Git status를 읽어 DB 갱신

등록 경로는 실제 Git root의 normalized absolute path로 저장한다. 같은 Project의 같은 root와 두 번째 활성 `primary`는 `409`로 거절한다. Role 미지정 시 첫 repository는 `primary`, 이후 repository는 `unknown`이다.

Git 확인은 argument array, `shell=False`, timeout을 사용해 `rev-parse`, `status --porcelain`, `branch --show-current`, `rev-parse HEAD`와 local ref만 읽는다. Remote fetch와 Git write operation은 없다. Dirty에는 staged, unstaged와 untracked file이 모두 포함되며 dirty 상태도 등록과 분석은 허용한다.

## Conversation, Agent Run과 Tool 기록 API

- Conversation/Message: `POST/GET /conversations`, `POST/GET /conversations/{id}/messages`
- Agent Run: `POST /agent-runs`, `GET /agent-runs/{id}`, Conversation별 목록, status와 step 기록
- Tool: `GET /tool-registry`, `POST/GET /tool-calls`, Tool Call status 기록
- Audit: `GET /audit-events`와 project/conversation/agent-run filter

Conversation History와 Agent Run 상태는 별도 테이블이다. Tool Call은 enabled registry 항목만 Envelope로 기록하며 어떤 부작용도 실행하지 않는다. Side-effect 후보 Tool은 idempotency key가 필수이고 같은 tool/key/project/repository scope는 `409`로 차단한다. Audit Event는 Conversation, Message, Run과 Tool Call의 주요 변경을 추적하며 secret을 metadata에 저장하지 않는다.

## Work, Task와 Worker API

- Project별 Work Item/Task 생성·목록과 status 변경
- Task별 Attempt 생성·목록과 status 변경
- Worker 등록·목록·heartbeat·revoke
- `POST /workers/{id}/claim`, `POST /workers/{id}/release`

Work Item 기본 status는 `active`, Task는 `draft`, Attempt는 `created`다. Attempt number는 Task별 1부터 증가한다. Claim은 Attempt를 `running_worker`, Task를 `running`, Worker를 `claimed`로 바꾸고 5분 lease를 설정한다. Heartbeat는 Worker의 active lease를 5분 연장한다. Release는 claim/lease/claimed-at을 지우고 Worker를 `available`로 만들며, 요청한 제한된 next status만 적용한다. 만료 lease 재claim 시 이전 Worker는 `expired`가 된다.

Claimed Attempt는 `POST /task-attempts/{id}/worktree`로 격리 worktree를 만들 수 있다. 원본 repository dirty 상태는 `409`로 차단한다. Worktree status/diff 조회 후 `POST /worktrees/{id}/commit-result`가 작업 branch에만 자동 commit하고 Attempt를 `committed`, Task를 `waiting_for_review`로 바꾼다. Diff patch, pre-commit status와 commit log는 app data artifact 파일로 저장한다.

Committed Attempt는 review-ready 목록과 상세 diff로 조회한다. Approve는 session 기반 사용자 승인 기록만 만들고 merge하지 않는다. Prepare와 squash 시 source clean, current branch와 base HEAD를 다시 확인하며 stale/dirty는 `409`다. 승인 후에만 `merge --squash`와 단일 local commit을 수행하고 Attempt를 `merged`, Worktree를 `cleanup_pending`, Task를 `completed`로 바꾼다. Remote push는 없다.

Merge 후 Worktree는 `cleanup_pending`이다. `GET /worktrees/cleanup-pending`과 `POST /worktrees/{id}/cleanup`은 app data Worktree root, symlink 여부, source path 비중첩, filesystem과 `git worktree list --porcelain` 일치를 검사한다. 성공 시 `cleaned`와 `cleanup_at`을 기록한다. Artifacts, source repository와 DB row는 유지하며 force cleanup은 거절한다.

전체 README 수정 회귀 테스트:

```powershell
uv run pytest tests/test_golden_path_readme_e2e.py
```

수동 절차와 기대 상태 전이는 `docs/golden-path-readme.md`를 참고한다.
