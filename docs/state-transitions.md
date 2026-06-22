# State Transitions

이 상태 머신은 Personal Mode MVP 기준이며 Team Mode에서는 확장될 수 있다.

## Task

```text
draft
→ running
→ waiting_for_review
→ completed
```
*(실패 또는 취소 시: `failed`, `cancelled`)*

## TaskAttempt

```text
created
→ running_worker
→ committed
→ merged
```
*(실패 또는 거절 시: `failed`, `rejected`, `abandoned`)*

## GitWorktree

```text
ready
→ dirty_result
→ committed
→ cleanup_pending
→ cleaned
```
*(실패 시: `failed`)*

## Worker

```text
available
→ claimed
→ available
```
*(기타 상태: `offline`, `error`)*

## WorkerRun

```text
created
→ running
→ succeeded
```
*(실패 또는 취소 시: `failed`, `cancelled`)*

## ApprovalRequest

```text
pending
→ approved
→ stale / rejected / cancelled / expired
```
