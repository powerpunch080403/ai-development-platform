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
