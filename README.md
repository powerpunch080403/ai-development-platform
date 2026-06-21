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

현재 저장소는 **bootstrap validation 단계**다. Windows에서 server dependency 설치, pytest, 실제 `/health` 요청, pnpm workspace 설치, Vite dev server와 production build를 검증했다. Local Worker, pairing/session, CLI Adapter와 Remote Test Runner의 실제 기능은 아직 구현하지 않았다.

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
