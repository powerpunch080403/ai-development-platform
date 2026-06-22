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

현재 repository는 Owner Review / 사용자 승인 Squash Merge baseline 단계다. Review 기록, diff, dirty/stale base 검사를 거쳐 명시적 승인 후 local base branch에 단일 squash commit을 만든다.

Merge 후 Worktree는 `cleanup_pending`이며 명시적 safe cleanup으로 `cleaned`가 된다. Cleanup은 app-managed path와 Git registration이 일치할 때만 Worktree directory를 제거하고 artifacts와 기록은 보존한다.

README Edit Golden Path는 pairing부터 Project/Task/Attempt/claim/worktree/manual edit/result commit/review/approve/squash merge/artifact/audit까지 하나의 pytest E2E로 고정했다. 이는 현재 1차 MVP 기록·Git 흐름의 회귀 기준이며 실제 AI Worker 통합 완료를 뜻하지 않는다.

이 Slice의 Git 동작은 status/read-only 확인에 한정한다. Dirty repository도 등록과 읽기·분석은 허용하지만 후속 Worker 실행은 dirty 상태에서 차단할 예정이다. Conversation/Tool/Task/Worker, worktree/branch/commit/merge, CLI Adapter, Remote Test Runner와 Desktop packaging은 아직 구현하지 않았다.

이번 Slice의 Tool Call은 실행기가 아니라 추적 Envelope다. 실제 Owner LLM/CLI, Policy/Approval 실행, Worker와 Tool 부작용은 후속이며 Conversation History, Run State와 장기 Memory는 섞지 않는다.

실제 AI Worker/Adapter와 중앙 Approval Group/merge queue는 없으며 remote push도 하지 않는다. Worktree cleanup과 고급 충돌 복구는 후속이다.
