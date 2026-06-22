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

현재 repository는 Work Item / Task / Task Attempt + Worker Claim Lease baseline 단계다. Work tree와 재시도 Attempt를 보존하고 Worker의 단일 active claim, 5분 lease, heartbeat, release와 revoke를 기록한다.

이 Slice의 Git 동작은 status/read-only 확인에 한정한다. Dirty repository도 등록과 읽기·분석은 허용하지만 후속 Worker 실행은 dirty 상태에서 차단할 예정이다. Conversation/Tool/Task/Worker, worktree/branch/commit/merge, CLI Adapter, Remote Test Runner와 Desktop packaging은 아직 구현하지 않았다.

이번 Slice의 Tool Call은 실행기가 아니라 추적 Envelope다. 실제 Owner LLM/CLI, Policy/Approval 실행, Worker와 Tool 부작용은 후속이며 Conversation History, Run State와 장기 Memory는 섞지 않는다.

이번 Worker는 registry/claim 상태일 뿐 process나 Adapter가 아니다. Worker는 Task Attempt 없이 실행하지 않으며 dirty repository 검사, worktree/branch/commit/artifact/review/merge는 후속 slice에서 연결한다.
