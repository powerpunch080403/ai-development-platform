# MVP Manual Smoke Checklist

This checklist verifies the minimum end-to-end product flow after the WorkerRun liveness, retry/follow-up, operations status, Task Workspace summary, and web UI guard work.

## Scope

This is a manual smoke test. It does not replace automated tests.

The goal is to prove that a user can:

1. create a project,
2. register a repository,
3. create a task,
4. create and run an attempt,
5. inspect task operations,
6. submit or review work safely,
7. see stale, attention, and follow-up signals clearly.

## Preconditions

- Server is running locally.
- Web app is running locally.
- User is authenticated in the web app.
- Local repository path is available and safe for testing.
- Database has been migrated to the latest schema.
- Worker liveness scheduler may remain disabled unless specifically testing scheduler behavior.

Recommended local commands:

    cd C:\Users\user2\Desktop\Projects\ai-development-platform
    Push-Location apps/server
    uv run alembic upgrade head
    uv run pytest tests/test_operations_observability.py tests/test_task_workspace_operations_summary.py tests/test_attempt_retry_policy.py -v
    Pop-Location
    pnpm -C packages/shared-contracts build
    pnpm -C apps/web build

## Smoke Path A: Basic Manual Worker Flow

### 1. Project and repository

- [ ] Open the web app.
- [ ] Create a project.
- [ ] Register a local Git repository.
- [ ] Confirm repository status can be refreshed.
- [ ] Confirm repository dirty/clean state is visible.

Expected result:

- Project appears in the project selector.
- Repository appears in the repository list.
- Refresh status succeeds or shows a clear error.

### 2. Task creation

- [ ] Create a work item.
- [ ] Create a task linked to the repository.
- [ ] Use a narrow write scope if possible.
- [ ] Select the created task.

Expected result:

- Task appears in the task selector.
- Allowed write scope is visible.
- Task operations panel appears.

### 3. Attempt creation and worker setup

- [ ] Register a manual worker.
- [ ] Create an attempt for the selected task.
- [ ] Claim the attempt with the manual worker.

Expected result:

- Attempt card appears.
- Claim button becomes disabled or no longer applicable after claim.
- Release button is available only when the attempt is claimed.
- Task operations summary updates after refresh.

### 4. Manual worker start

- [ ] Start Manual Worker.
- [ ] Confirm a worktree is created.
- [ ] Confirm WorkerRun status is visible on the Attempt card.
- [ ] Confirm Task operations shows active WorkerRun count.

Expected result:

- Worktree path is visible.
- Branch/base/result metadata is visible.
- WorkerRun status appears.
- Submit Manual Result is available only while the WorkerRun is valid/running.

### 5. Manual submit

- [ ] Make a safe test change in the worktree.
- [ ] Submit Manual Result.
- [ ] Refresh artifacts.
- [ ] View generated artifacts if present.

Expected result:

- Attempt status advances out of running state.
- Artifacts are visible if produced.
- Task operations no longer shows stale running WorkerRun.

## Smoke Path B: Operations Status

### 1. Project operations endpoint

- [ ] Call or inspect GET /projects/{project_id}/operations/status.
- [ ] Confirm task, attempt, and WorkerRun status counts are present.
- [ ] Confirm active/stale/attention counts are present.
- [ ] Confirm recent WorkerRuns are present when WorkerRuns exist.

Expected result:

- Endpoint returns only data for the selected project.
- No cross-project records are visible.
- Response is read-only and does not mutate state.

### 2. Task workspace operations summary

- [ ] Open a task in the web UI.
- [ ] Confirm the Task operations panel displays active Attempt count.
- [ ] Confirm the Task operations panel displays active WorkerRun count.
- [ ] Confirm the Task operations panel displays stale WorkerRun count.
- [ ] Confirm the Task operations panel displays attention count.
- [ ] Confirm the Task operations panel displays follow-up availability.
- [ ] Confirm the Task operations panel displays latest WorkerRun status.
- [ ] Use Refresh task operations.

Expected result:

- Summary refreshes without changing task state.
- Stale or attention states are clearly visible.

## Smoke Path C: Stale WorkerRun and Recovery Boundary

This path can be tested through fixtures, direct DB setup, or a controlled stale lease scenario.

- [ ] Create or identify a running WorkerRun with expired lease_expires_at.
- [ ] Open the selected task in the web UI.
- [ ] Confirm the stale WorkerRun warning appears.
- [ ] Confirm Submit Manual Result is disabled for an expired lease.
- [ ] Run stale recovery manually if available.
- [ ] Refresh Task operations.

Expected result:

- Expired lease is shown as attention.
- UI does not encourage submitting stale work.
- Recovery marks stale WorkerRun failed and linked running attempt worker_failed.
- Evidence/worktree/artifacts remain preserved.

## Smoke Path D: Explicit Follow-up Boundary

- [ ] Use a failed or worker_failed attempt.
- [ ] Confirm Task operations shows follow-up available when no blocking attempt exists.
- [ ] Create another active/adopted attempt for the same task.
- [ ] Refresh Task operations.
- [ ] Confirm follow-up is blocked and the blocking attempt is identified.

Expected result:

- Follow-up eligibility matches backend retry policy.
- UI shows blocked state instead of implying retry is always available.
- Existing active/adopted attempt prevents duplicate follow-up.

## Smoke Path E: Review and Cleanup

- [ ] Move an attempt to review-ready state through the normal flow.
- [ ] Open Owner Review / Squash Merge panel.
- [ ] Confirm review data loads.
- [ ] Approve or reject intentionally.
- [ ] If approved, prepare merge.
- [ ] Merge only when policy and approval state allow it.
- [ ] Open Worktree Cleanup panel.
- [ ] Confirm cleanup pending worktrees are visible.
- [ ] Cleanup only app-managed worktrees.

Expected result:

- Review panel does not bypass approval state.
- Merge action is gated by approval.
- Cleanup does not delete source repositories.
- Failed/stale/rejected attempt evidence remains inspectable unless explicitly cleaned by policy.

## Pass Criteria

The smoke run passes when:

- [ ] User can complete the basic manual worker path.
- [ ] Task operations panel reflects current state.
- [ ] Project operations endpoint reflects project-level state.
- [ ] Stale WorkerRun warning is visible.
- [ ] Unsafe action buttons are disabled or clearly guarded.
- [ ] Follow-up availability reflects backend policy.
- [ ] Review and cleanup boundaries are visible.
- [ ] No source repository is deleted during the flow.
- [ ] Failed/stale work evidence remains inspectable.

## Fail Criteria

The smoke run fails if:

- [ ] UI shows a destructive or unsafe action as available when backend policy should block it.
- [ ] Stale WorkerRun can be submitted without recovery.
- [ ] Follow-up can be created while another active/adopted attempt exists.
- [ ] Project operations leaks data from another project.
- [ ] Cleanup removes unmanaged files or source repositories.
- [ ] Task Workspace cannot explain why work is blocked or stale.

## Notes

This checklist should be updated whenever Task/Attempt/WorkerRun lifecycle semantics change.
