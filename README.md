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

현재 저장소는 **초기 skeleton 단계**다. Local Worker, pairing/session, CLI Adapter와 Remote Test Runner의 실제 기능은 아직 구현하지 않았다.

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

## 빠른 시작

아직 skeleton이므로 dependency 설치와 실행은 선택 사항이다.

```powershell
uv sync --project apps/server
uv run --project apps/server fastapi dev apps/server/src/aidp_server/main.py

pnpm install
pnpm web:dev
```

정확한 통합 개발 명령은 다음 구현 Slice에서 보완한다.
