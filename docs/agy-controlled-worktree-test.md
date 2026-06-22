# Controlled AGY CLI Worktree Test

This document outlines the procedure to run a real `agy` execution against an isolated worktree via the Experimental Antigravity CLI Worker Adapter.

## Prerequisites

Ensure that the real `agy` CLI path and features are enabled by setting these environment variables on the backend:

```powershell
$env:AIDP_ENABLE_EXPERIMENTAL_ANTIGRAVITY_CLI="true"
$env:AIDP_ANTIGRAVITY_CLI_PATH="C:\Users\user2\AppData\Local\agy\bin\agy.exe"
$env:AIDP_RUN_REAL_AGY_TESTS="true"
```

*Note: The `--dangerously-skip-permissions` flag is intentionally left out by default unless you explicitly enable `AIDP_ANTIGRAVITY_CLI_ALLOW_DANGEROUS_SKIP_PERMISSIONS=true`.*

*Note: The Process Runner explicitly closes `stdin` (redirects to `DEVNULL`) for all background workers. This prevents CLIs like `agy` from hanging indefinitely while waiting for interactive input in non-interactive pipeline environments.*

## Verification Steps

1. **Create Test Repository**
   Create a new blank repository locally with a single `README.md` file. Do NOT use the actual implementation repo (`ai-development-platform`).

2. **Register Project & Repository**
   Register the new repository in the local AIDP server instance.

3. **Create the Task**
   Create a Task that explicitly has `write_scope` restricted:
   ```json
   {
     "mode": "paths",
     "paths": ["README.md"],
     "allow_new_files": false
   }
   ```

4. **Create Worktree & Claim Attempt**
   Through the UI or API, accept the task, create a task attempt, and generate a Git worktree. The worker must then claim the attempt.

5. **Invoke Controlled Endpoint**
   Execute the controlled experimental endpoint:
   ```http
   POST /task-attempts/{task_attempt_id}/external-cli/antigravity/run-experimental
   {
     "adapter_kind": "antigravity_cli",
     "worker_id": "<worker-id>",
     "mode": "controlled_readme_test"
   }
   ```

6. **Review Artifacts**
   Wait for the execution to finish. The system will create artifacts containing `stdout`, `stderr`, and the `WorkerRun` report.

7. **Verify Result Commit**
   If successful, the endpoint will invoke `apply_worktree_result` and create a Result Commit reflecting the added line in `README.md`.

8. **Verify Source Integrity**
   Verify that the target source repository's `HEAD` has not been altered, and the changes exist purely as a pending result commit. The implementation repo must also remain completely untouched.

9. **Complete the Golden Path**
   Proceed manually to review, approve, and squash-merge the result commit using the standard UI actions.

## Write Scope Violation Path (Failure Path) E2E

- Real AGY `write_scope` violation is explicitly covered by an opt-in E2E test.
- This Violation E2E test exclusively uses a temporary repository to ensure source safety.
- AGY is instructed by a controlled enum mode (`controlled_scope_violation_test`), **not a free-form prompt**, avoiding arbitrary command execution.
- If AGY creates `OUT_OF_SCOPE.txt` while the task's `write_scope` allows only `README.md`, `apply_worktree_result` detects the violation and securely rejects the execution.
- No result commit is created in the Git worktree.
- The Owner review/merge state is completely skipped/prevented.
- Real AGY tests, both success and violation paths, are skipped by default in the test suite.
- `--dangerously-skip-permissions` remains completely disabled by default on the server and is securely governed by environment toggles.

## Opt-in Review/Merge E2E

`test_real_agy_controlled_result_can_be_reviewed_and_squash_merged` verifies the complete controlled result path through Owner review, explicit approval, squash preparation, squash merge and `cleanup_pending`. It creates and targets only a pytest `tmp_path` repository; neither the implementation repository nor a user project is used as the AGY target.

The test is skipped by default and runs only when `AIDP_RUN_REAL_AGY_TESTS`, `AIDP_ENABLE_EXPERIMENTAL_ANTIGRAVITY_CLI`, `AIDP_ANTIGRAVITY_CLI_PATH` and `AIDP_ANTIGRAVITY_CLI_ALLOW_DANGEROUS_SKIP_PERMISSIONS` are explicitly configured. Current background automation requires `--dangerously-skip-permissions`, but the corresponding setting remains `false` by default. AGY creates only the isolated result; Owner review, approval and squash merge remain separate explicit API actions.
