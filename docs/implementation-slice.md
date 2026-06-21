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

현재 repository는 skeleton 단계이며 위 기능을 아직 구현하지 않았다.
