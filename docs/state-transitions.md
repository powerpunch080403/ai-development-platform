# State Transitions

이 상태 머신은 Personal Mode MVP 기준이며 Team Mode에서는 확장될 수 있다.

서버의 `state_transitions` 모듈이 Task, TaskAttempt, GitWorktree, WorkerRun과 Worker의 허용 전이를 정의한다. 동일 상태로의 요청은 idempotent no-op으로 허용하지만, 허용 목록에 없는 전이는 `409 Conflict`와 `STATE_TRANSITION_NOT_ALLOWED`로 거부하고 audit event를 남긴다.

## 생성 상태

- Task는 항상 `draft`로 생성한다.
- TaskAttempt는 항상 `created`로 생성한다.
- 생성 요청에 `status`가 포함되어도 호환성을 위해 무시하며 서버의 초기 상태를 사용한다.

## Public status endpoint 경계

`POST /tasks/{task_id}/status`와 `POST /task-attempts/{attempt_id}/status`는 운영 상태의 제한된 전이만 제공한다.

다음 결과 상태는 generic status endpoint로 만들 수 없다.

- Task: `waiting_for_review`, `completed`
- TaskAttempt: `committed`, `reviewing`, `accepted`, `rejected`, `merge_ready`, `merged`

`committed`, `accepted`, `merged`, `completed` 같은 상태는 commit, review, approval, squash merge 전용 application service가 관련 Git 및 승인 조건을 검증한 뒤에만 만든다. 이는 ADR-0009의 상태 머신과 공식 결과 기록을 보호하기 위한 경계다.

## 주요 내부 흐름

```text
Task
draft -> running -> waiting_for_review -> completed

TaskAttempt
created -> running_worker -> committed -> merged

GitWorktree
creating -> ready -> dirty_result -> committed -> cleanup_pending -> cleaned

WorkerRun
created -> running -> succeeded | failed | cancelled

Worker
available -> claimed -> available
```

실패, 취소, 재시도와 review rejection 전이도 서버 transition map에 명시되어 있다. 내부 application service는 Worker claim, result commit, review와 merge에 필요한 보호 상태 전이를 소유하며 public generic endpoint는 이를 대신하지 않는다.

Result commit 전에는 Task의 `write_scope`에 대해 모든 변경 경로를 검증한다. 위반 시 Worktree는 commit 상태로, TaskAttempt는 `committed`로, Task는 `waiting_for_review`로 전이하지 않는다.
