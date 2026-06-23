# Codex CLI Owner Bridge Protocol Spike

*Note: This is a protocol spike, not the final bridge. Real Codex CLI Owner reasoning is not enabled by default. Tool call bridge is intentionally not implemented in this slice. Task/Worker/Approval side effects are not performed by Codex CLI directly.*

## Current local Codex CLI discovery
Based on local discovery, the `codex` command is available.
- Interactive app: `codex [PROMPT]`
- Non-interactive execution: `codex exec [PROMPT]`
- Supports inputting the prompt via arguments or `stdin` (if `-` or piped).
- Supports specifying the working directory using `-C <DIR>`.
- Supports outputting structured logs with `--json` (JSONL).
- Sandbox policies: `-s read-only`, `workspace-write`, `danger-full-access`.
- Approval flags: `-a untrusted|on-failure|on-request|never` (Interactive only).
- Output specific: `-o <FILE>` outputs the last message to a file.

## Proposed Owner provider invocation
The backend will use `codex exec` for non-interactive execution of the queued AgentRun.
- **Provider**: `CodexCliOwnerProvider`
- **Command**: `codex exec --json --ephemeral -C <project_dir> -s read-only "<prompt>"`
- Since this is an Owner runtime, it operates as the user's delegate. For safety during the spike, it should run with `-s read-only` and `--ephemeral`.

## AgentRun context packaging
The `AgentRun` contains a `purpose` and an optional `input_message_id`.
The backend will construct a `[PROMPT]` that wraps the conversation context, the user's latest input, and system instructions directing the Owner to use the provided tools (which bridge to the App's Tool Contract).

## Working directory policy
The Owner runtime needs to read the project files.
It will be executed with `-C <project_dir>` so it has access to the primary repository context.
It must not mutate the directory directly (`-s read-only`), but instead emit Tool Calls (e.g., `create_task`) which the backend catches and translates into app side effects.

## Input strategy
Pass the system prompt and context either as command line argument `[PROMPT]` or piped via `stdin`. For large contexts, `stdin` is safer to avoid shell argument length limits.

## Output/log capture strategy
Use `--json` to capture `stdout` as JSONL.
The backend will stream and parse this JSONL to record `AgentRunStep` transitions and capture Tool Calls.
`stderr` will be captured for error diagnostics and saved to the `AgentRun` error fields or process logs.

## Timeout/cancel/error mapping
- Executed via an asynchronous process runner with a configured timeout (`codex_cli_timeout_seconds`, default 120s).
- If the process exceeds the timeout or is cancelled by the user, the backend terminates the process tree and sets `AgentRunStatus` to `FAILED` or `CANCELLED`.
- Non-zero exit codes map to `FAILED` status, recording `exit_code` and `stderr` excerpts.

## Provider metadata
The following metadata will be saved in the `owner_runtime.skeleton_invoked` or equivalent audit events:
- `provider_kind`: "codex_cli"
- `bridge_spike`: true
- `real_provider_execution`: boolean
- `tool_loop_executed`: false
- `task_side_effects_performed`: false
- `worker_side_effects_performed`: false
- `approval_side_effects_performed`: false

## Tool call bridge placeholder
Currently, the Codex CLI might try to execute standard shell commands or its own tools.
The final bridge will need to provide a custom JSON schema (`--output-schema`) or inject custom tools via prompt instructions, intercepting them from the JSONL output.
For this spike, we do NOT execute or bridge any tools. `tool_loop_executed` remains `false`.

## Side-effect boundary
Codex CLI will NOT directly mutate the database.
Codex CLI will NOT create Worktrees directly.
All Task generation, Worker execution, and Approval workflows must flow through the Local Control Plane APIs (Tool Contract).
For this spike, `task_side_effects_performed`, `worker_side_effects_performed`, and `approval_side_effects_performed` are `false`.

## Open questions
- How to reliably inject custom Tool definitions into `codex exec` without relying solely on prompt adherence?
- Does `--output-schema` enforce tool call formatting well enough for the bridge?
- How to handle multi-turn conversations if `codex exec` is inherently single-turn/ephemeral? Do we re-feed the entire history JSONL each time?
