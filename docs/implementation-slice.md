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

현재 repository는 Owner Review 및 Local Policy / Approval Request Baseline 단계다. 단순히 Review 상태만 저장하는 것이 아니라 `policy_decisions`에 기반하여 위험도(Risk Level)를 평가하고, Squash Merge(`merge.perform_squash`) 수행 시 해시 기반 Fingerprint로 묶인 명시적인 `approval_requests` 승인을 검증한다. Base branch가 변하거나 Result가 변경되면 Approval은 Stale 처리되어 안전을 보장한다.

Merge 후 Worktree는 `cleanup_pending`이며 명시적 safe cleanup으로 `cleaned`가 된다. Cleanup은 app-managed path와 Git registration이 일치할 때만 Worktree directory를 제거하고 artifacts와 기록은 보존한다.

README Edit Golden Path는 pairing부터 Project/Task/Attempt/claim/worktree/manual edit/result commit/review/approve/squash merge/artifact/audit까지 하나의 pytest E2E로 고정했다. 이는 현재 1차 MVP 기록·Git 흐름의 회귀 기준이며 실제 AI Worker 통합 완료를 뜻하지 않는다.

이 Slice의 Git 동작은 status/read-only 확인에 한정한다. Dirty repository도 등록과 읽기·분석은 허용하지만 후속 Worker 실행은 dirty 상태에서 차단할 예정이다. Conversation/Tool/Task/Worker, worktree/branch/commit/merge가 구현되었고, 외부 프로세스 실행을 캡슐화한 Process Runner Baseline(환경변수 allowlist 적용, 민감정보 차단)과 안전한 External CLI Adapter Contract (Dry Run)이 추가되었다. 실제 Codex/Antigravity CLI 연동, credential injection, Remote Test Runner와 Desktop packaging은 아직 구현하지 않는다.

이번 Slice에서 **Risk 분류와 접근 정책 결정을 단일 `ActionPolicyDefinition` 카탈로그로 통합**했으며, 주요 부작용(Side-effect) API(Mock/Manual Worker 실행, Dry-Run 등)에 `policy_decisions` 기록을 남기도록 보강했다.
Tool Call은 아직 실행기가 아니라 추적 Envelope다. 추후 **전체 Tool/Action Executor를 전면 개편**하여 모든 API가 단일화된 ToolCall 흐름을 강제하도록 발전시킬 계획이다. 실제 Owner LLM/CLI, Policy/Approval 실행, Worker와 Tool 부작용은 후속이며 Conversation History, Run State와 장기 Memory는 섞지 않는다.

Task와 TaskAttempt 생성 상태는 각각 `draft`, `created`로 서버가 고정한다. Generic status endpoint는 운영 상태의 제한된 전이만 허용하며 `committed`, `accepted`, `merged`, `completed` 같은 보호 결과 상태는 commit, review, approval와 squash merge 전용 application service에서만 생성한다. 허용되지 않은 상태 전이는 409로 거부하고 audit event로 기록한다.

Task의 Personal Mode MVP `write_scope`는 상대 경로 allowlist와 새 파일 허용 여부를 저장한다. 기본 `.`은 전체 worktree를 허용한다. Raw, Mock와 Manual 결과는 commit 직전에 Git changed path를 검증하며 scope 위반 시 commit과 review-ready 상태 전이를 차단한다. 후속 policy는 이 baseline을 더 세밀한 grant와 path policy로 확장할 수 있다.

실제 AI Worker/Adapter와 중앙 Approval Group/merge queue는 없으며 remote push도 하지 않는다. Worktree cleanup과 고급 충돌 복구는 후속이다.
