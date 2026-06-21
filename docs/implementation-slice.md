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

현재 repository는 Project / Repository Registration + Git Status 단계다. 인증된 local user가 Project를 만들고 여러 ProjectRepository를 등록하며, normalized root, role, branch, HEAD와 dirty 상태를 SQLite에 기록할 수 있다.

이 Slice의 Git 동작은 status/read-only 확인에 한정한다. Dirty repository도 등록과 읽기·분석은 허용하지만 후속 Worker 실행은 dirty 상태에서 차단할 예정이다. Conversation/Tool/Task/Worker, worktree/branch/commit/merge, CLI Adapter, Remote Test Runner와 Desktop packaging은 아직 구현하지 않았다.

현재 REST/application service는 후속 Tool Registry에서 `project.create`, `repository.register`, `repository.get_status`, `repository.check_dirty` 후보가 사용할 기반이다. 이번 Slice에서는 Tool Call Envelope나 Tool Registry 자체를 구현하지 않는다.
