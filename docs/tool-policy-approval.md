# Tool, Policy, and Approval

## Tool Registry와 Tool Call Envelope

- **Tool Registry**: 서버가 통제할 기능의 version, risk, idempotency, audit 요구 사항을 설명한다. 이제 별도 하드코딩 없이 중앙화된 **Action Policy Catalog (`ACTION_CATALOG`)**를 통해 Tool Registry에 자동 Seed 및 동기화된다.
- **Tool Call Envelope**: 현재 구현 단계에서 Tool Call은 실제 실행기가 아니라 추적용 Envelope 역할만 한다. Message, Run/Step, Tool Call 기록만 저장하며, 모델/도구 부작용과 장기 Memory 기록은 포함하지 않는다. 추후 **Action Executor를 전면 개편**하여, 모든 시스템 부작용이 ToolCall을 통해서만 발생하고 제어되도록 강제할 계획이다.

## Local Policy Baseline

모든 action은 중앙화된 **Action Policy Catalog (`ACTION_CATALOG`)**를 통해 단일한 Risk Level과 접근 제어 방식(Allow, Deny, Approval Required)으로 평가되며, 주요 시스템 부작용 API 실행 시 사전에 `policy_decisions`에 그 결과가 평가 및 기록된다.

- **R1 (Allow)**: `worktree.commit_result`, `worker.run_mock`, `worker.run_manual`, `process_run.get`, `process_run.list_for_attempt`. 위험도가 낮은 일반 작업 및 조회.
- **R2 (Allow)**: `review.approve`, `process_run.create`, `process_run.cancel`. 리뷰어 권한이나 안전한 격리 환경 내의 실행 승인 동작.
- **R3 (Approval Required)**: `merge.perform_squash`. Squash Merge 등 저장소를 변경하는 파괴적/주요 동작은 사전에 생성된 유효한 ApprovalRequest를 필요로 한다.
- **R4 (Deny)**: 그 외 정의되지 않거나 극도로 위험한 동작은 현재 Deny로 처리된다.

## Approval Fingerprint 구성

Approval Request의 검증을 위해 12가지 필드를 포함하는 SHA-256 fingerprint가 사용된다:
- `action_type`
- `local_user_id`
- `project_id`
- `repository_id`
- `task_id`
- `task_attempt_id`
- `git_worktree_id`
- `base_branch`
- `base_commit_sha`
- `result_branch`
- `result_commit_sha`
- `risk_level`

## Stale Approval 조건

Approval Request 승인 이후, `base_commit_sha` 또는 `result_commit_sha`가 변경되면 해당 Approval은 유효하지 않은 것으로 취급되어 `stale` 상태로 변환된다. Squash Merge 등 실행 시 Fingerprint가 현재 컨텍스트와 일치하는 유효한 `pending/approved` 상태여야만 한다.

*(전체 Owner Grant, Autonomy Profile, Team Approval Group 등의 복잡한 인가 시스템은 MVP 이후 후속 과제이다.)*
