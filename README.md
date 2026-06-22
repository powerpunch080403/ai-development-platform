# AI Development Platform

새로운 v2 AI 개발 플랫폼 구현 저장소다. 설계와 아키텍처 결정의 원천은 별도 `ai-development-platform-design` 저장소의 ADR-0001~0013이다.

기존 `ai-game-company-server`는 v1 참고 구현일 뿐이며 코드를 복사하거나 fork해 사용하지 않는다. 설계와 참고 구현이 충돌하면 design repository의 accepted ADR을 우선한다.

## 현재 방향

- Personal Mode MVP를 먼저 구현한다.
- 장기 제품 목표는 Desktop App이지만 초기 UI는 Desktop App Shell에서 재사용할 수 있는 Desktop-ready Web UI다.
- 첫 구현 목표는 Local Worker Golden Path다.
- 목표 Adapter는 Codex CLI Owner와 Antigravity CLI Worker다.
- Mock/Manual Adapter는 개발, pipeline 검증과 복구를 위한 fallback이다.
- Remote Test Runner는 MVP에 포함하지만 Local Worker Golden Path와 목표 CLI Adapter 통합 이후 구현한다.

현재 저장소는 **Git Worktree + Manual Result Commit + Artifact Ref baseline 단계**다. Claimed Attempt에 clean repository 기반 격리 worktree/branch를 만들고, 사용자가 직접 수정한 결과를 작업 branch에 commit해 diff/status/log artifact로 보존한다.

## Monorepo 구조

```text
apps/server             FastAPI 기반 App-managed Local Runtime
apps/web                React/TypeScript/Vite 기반 Desktop-ready Web UI
apps/runner-agent       Remote Test Runner Agent placeholder
packages/shared-contracts  API/Tool DTO와 공통 type placeholder
packages/cli-adapters      외부 Agent Process Adapter contract placeholder
docs                    구현 순서와 개발 문서
scripts                 Windows/Linux 개발 script
tests                   통합·Golden Path test 위치
```

## Public repository 주의사항

Secret, API key, token, local database, 사용자 project 내용, generated artifact, worktree, runtime log와 local credential을 commit하지 않는다. `.env`는 commit하지 않고 `.env.example`만 예시로 유지한다.

## 개발 도구

필수 도구:

- Python 3.11 이상
- Node.js
- uv
- pnpm

Windows에서 명령이 보이지 않으면 새 PowerShell을 열어 사용자 PATH 변경을 반영한다.

## Windows PowerShell 빠른 시작

```powershell
uv sync --project apps/server
uv run --project apps/server alembic upgrade head
uv run --project apps/server python -m aidp_server.cli auth pairing-code
uv run --project apps/server pytest
uv run --project apps/server uvicorn aidp_server.main:app --reload --host 127.0.0.1 --port 8000

pnpm install
pnpm -C apps/web build
pnpm web:dev
```

별도 PowerShell에서 health를 확인한다.

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

## Linux/macOS 빠른 시작

```bash
uv sync --project apps/server
uv run --project apps/server alembic upgrade head
uv run --project apps/server python -m aidp_server.cli auth pairing-code
uv run --project apps/server pytest
uv run --project apps/server uvicorn aidp_server.main:app --reload --host 127.0.0.1 --port 8000

pnpm install
pnpm -C apps/web build
pnpm web:dev
```

```bash
curl http://127.0.0.1:8000/health
```

Workspace 전체 TypeScript package build는 `pnpm -r build`로 검증한다. 통합 개발 launcher는 아직 구현하지 않았으며 `scripts/dev.ps1`과 `scripts/dev.sh`는 도구 버전과 실행 명령을 안내한다.

## Local Runtime data

기본 App Data Directory는 `./runtime-data`이며 기본 SQLite 파일은 그 아래 `aidev.sqlite3`다. `AIDP_APP_DATA_DIR`과 선택적 `AIDP_DATABASE_URL`로 바꿀 수 있다. Database schema는 Alembic migration으로 관리한다.

`runtime-data/`, SQLite DB, `.env`, token과 credential은 source repository에 commit하지 않는다. Pairing code 원문은 CLI에 한 번만 표시되고 DB에는 hash만 저장된다. Web session token도 HttpOnly cookie로만 전달되며 DB에는 hash만 저장된다.

## Web UI pairing

Migration과 server를 실행한 뒤 별도 터미널에서 pairing code를 발급하고 `http://localhost:5173`의 Web UI에 입력한다. 인증되지 않았거나 만료·폐기된 session으로 보호 endpoint를 호출하면 `401`을 반환한다. Pairing code 발급은 CLI 전용이며 unauthenticated HTTP 발급 endpoint는 제공하지 않는다.

## Project와 Git repository 등록

로그인 후 Project를 만들고 로컬 Git repository 경로를 등록할 수 있다. 첫 repository의 role은 생략 시 `primary`, 이후 생략된 role은 `unknown`이며 Project당 활성 `primary`는 하나만 허용한다.

등록과 refresh는 `git rev-parse`, `git status --porcelain`, branch와 HEAD 조회만 수행한다. fetch, branch/commit/worktree 생성이나 merge는 수행하지 않는다. Dirty repository도 등록과 읽기·분석은 허용한다. 후속 Worker slice에서는 해당 repository가 dirty이면 작업 시작을 차단할 예정이다.

## Conversation과 실행 기록

Conversation은 사용자에게 보이는 채팅 기록이고 Agent Run은 하나의 요청 또는 시스템 목적을 처리하는 상태 기록이다. 이번 단계는 Message, Run/Step과 Tool Call Envelope를 SQLite에 기록할 뿐 실제 모델이나 Tool 부작용을 실행하지 않는다. Tool Registry는 서버가 통제할 기능의 version, risk, idempotency와 audit 요구를 설명하며 Audit Event는 주요 기록 생성과 상태 변경을 추적한다.

## Work와 Worker lease

Work Item은 사람이 보는 목표/기능 트리, Task는 Owner가 Worker에게 맡길 실행 단위, Task Attempt는 덮어쓰지 않는 1회 실행 기록이다. Worker는 Task Attempt 없이 독립 실행할 수 없다. Claim은 5분 lease를 만들고 heartbeat가 갱신한다. Active lease는 한 Worker만 소유하며 만료된 lease는 재claim할 수 있다. 이 단계는 점유 기록만 제공하며 process, worktree, branch, commit과 merge는 만들지 않는다.

작업 branch는 `aidp/task-<task8>/attempt-<number>-<attempt8>` 형식이며 충돌 시 suffix를 붙인다. Worktree는 app data의 `worktrees/<project8>/<repository8>/<attempt12>`에 생성한다. 원본 repository가 dirty이면 생성하지 않는다. Commit은 worktree branch에만 만들고 기본 branch merge/squash는 수행하지 않는다. Artifact 파일은 app data `artifacts/`에 저장하고 SQLite에는 SHA-256 metadata만 둔다.
