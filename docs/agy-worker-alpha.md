# AGY Worker Alpha

Real AGY Worker Alpha is available for controlled, opt-in, local verification paths.
It is not yet a general free-form AI worker for arbitrary user projects.

## Current Status

- Local Worker MVP baseline exists.
- Real AGY Worker Alpha exists but is strictly opt-in.
- Real AGY execution is skipped by default in all tests.
- AGY execution currently supports controlled enum modes only.
- Free-form prompt is intentionally not exposed.
- `--dangerously-skip-permissions` remains disabled by default and requires explicit configuration.
- AGY runs only in assigned, isolated git worktrees.
- Source `main`/`default` branch is securely protected until explicit Owner review, approval, and squash merge.

## Supported Controlled Modes

The `ExternalCliRunExperimentalRequest.mode` enum strictly defines the allowed operations. The adapter blocks arbitrary payloads (e.g. `prompt`, `args`, `executable`) by using `ConfigDict(extra="forbid")`.

The currently supported modes are:
- `controlled_readme_test`: Instructs AGY to modify only `README.md` to test the success path.
- `controlled_scope_violation_test`: Instructs AGY to create `OUT_OF_SCOPE.txt` to test the failure path and validation boundaries.
- `controlled_timeout_test`: Instructs AGY to hang indefinitely to test the timeout and safe failure boundary.

## Safety Boundaries

- **opt-in only**: Real AGY integration is hidden behind environment variables and strict settings.
- **temp repo tested**: E2E tests target pytest `tmp_path` repositories. Implementation or user project repositories are actively avoided for real AGY targets.
- **assigned worktree only**: Code execution occurs in a safely branched Git Worktree, entirely detached from the active source branch.
- **write_scope validation**: Changes that fall outside the explicitly authorized file paths are intercepted and rejected by `apply_worktree_result`.
- **stdin DEVNULL**: Background process invocation specifically ties `stdin` to `subprocess.DEVNULL` to prevent infinite hang errors on interactive prompts.
- **env allowlist**: Process runner uses a restricted environment variable allowlist to prevent leakage of credentials.
- **no free-form prompt**: The prompt logic is hardcoded inside the adapter based on the selected mode enum.
- **no arbitrary command**: The executable and arguments are fully controlled by the server adapter.
- **no direct git commit by adapter**: The adapter makes raw file modifications. The server handles creating result commits via `apply_worktree_result`.
- **no automatic merge**: All results wait in `WAITING_FOR_REVIEW`. An explicit Approval action is required before the squash merge can proceed.

## Verified E2E Paths

The pipeline provides complete end-to-end verification for the following lifecycle paths:

1. **Success / Review / Merge**
   - Real AGY execution → `README.md` modified
   - `apply_worktree_result` detects changes and creates a result commit
   - State transition to `WAITING_FOR_REVIEW`
   - Owner explicitly provides Approval
   - Squash merge executed
   - Target source branch correctly updated
   - Pending worktree safely cleaned up

2. **Write Scope Violation**
   - Real AGY execution → `OUT_OF_SCOPE.txt` created
   - `apply_worktree_result` detects paths outside `write_scope`
   - `WRITE_SCOPE_VIOLATION` triggered
   - Result commit generation aborted
   - `WorkerRun` marked as FAILED
   - Review and merge state actively prevented

3. **Timeout / Process Failure**
   - Real AGY execution → Process times out or fails (non-zero)
   - ProcessRunner captures failure/timeout status
   - `WorkerRun` and `ProcessRun` correctly marked as `TIMED_OUT` or `FAILED`
   - No file or commit side effects
   - Review and merge state actively prevented

## Required Environment Variables for Real AGY Tests

To manually invoke the Real AGY E2E test paths, the following environment variables are required:

```powershell
AIDP_RUN_REAL_AGY_TESTS=true
AIDP_ENABLE_EXPERIMENTAL_ANTIGRAVITY_CLI=true
AIDP_ANTIGRAVITY_CLI_PATH=C:\Users\user2\AppData\Local\agy\bin\agy.exe
AIDP_ANTIGRAVITY_CLI_ALLOW_DANGEROUS_SKIP_PERMISSIONS=true
```

Without these, the tests will safely skip and no real execution will occur.

## Known Limitations

- Real Antigravity CLI Worker is strictly limited to isolated local tests.
- It cannot yet run free-form user intents or arbitrary scripts.
- Process logs are recorded but stream tracking (streaming responses to the UI) is pending.

## Next Recommended Slices

- Exposing process execution logs to the Web UI for better observability.
- Expanding the API to support controlled parameter inputs without opening up free-form prompts.
- Transitioning towards safe, remote execution containers (Remote Test Runner) for expanded capability outside local environments.
