# Initial Implementation Slice

ADR-0013에 따라 첫 구현 목표는 Local Worker Golden Path다.

## 순서

1. Monorepo skeleton과 개발 환경
2. Local Runtime, SQLite migration과 Web UI pairing/session
3. Project, Conversation, Agent Run과 Tool Call 최소 상태
4. Task, Attempt, Worker claim/lease와 Git worktree
5. Mock Adapter와 Manual Adapter
6. 자동 commit, artifact reference, Owner review와 squash merge
7. Codex CLI Owner와 Antigravity CLI Worker Adapter
8. Remote Test Runner

Mock과 Manual Adapter는 실제 외부 CLI integration 전에 상태 머신과 Git pipeline을 검증하기 위한 fallback이며 제품 방향을 대체하지 않는다.

Remote Test Runner는 MVP에 포함하지만 Local Worker path 이후 구현한다. 작은 게임 제작은 첫 구현 대상이 아니라 Personal Alpha의 Golden Path 3 검증 시나리오다.

현재 repository는 Local User Bootstrap + Web UI Pairing Session 단계다. FastAPI/SQLite baseline 위에 `Local Owner` bootstrap, CLI 전용 일회용 pairing code, Web UI device와 HttpOnly cookie session, 인증 상태·logout·device/session 조회 및 폐기를 구현했다.

이 Slice는 local identity와 Web UI session 경계까지만 제공한다. 중앙 account 연결, OAuth, sync, Project/Conversation/Tool/Task/Worker, CLI Adapter, Remote Test Runner와 Desktop packaging은 아직 구현하지 않았다.
