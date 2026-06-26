# Working Rules

These rules guide implementation work for this repository.

## Product and architecture alignment

- Treat the implementation repository as the source of truth for current code state.
- Use the design repository to validate product direction and architectural boundaries.
- Do not make changes that alter the established design direction without an explicit user decision.
- Prefer long-term architectural correctness over short-term UI or implementation patches.

## Decision protocol

Before making a change that affects data model, provider boundaries, runtime behavior, workflow ordering, or product direction:

1. Describe the current implementation state.
2. Describe the problem.
3. Present the viable options.
4. Recommend one option with tradeoffs.
5. Ask for an explicit decision.
6. Apply only the approved decision.

## Personal Mode direction

- Owner is a domain role, not a vendor or runtime.
- Owner Runtime Provider is the execution mechanism.
- Codex CLI is the first concrete provider, not the product boundary.
- The platform must remain provider-aware and provider-agnostic at domain and UI boundaries.
- Provider-specific details belong in provider metadata, adapter code, or provider-specific error mapping.
- UI should render generic AgentRun, ToolCall, Task, WorkerRun, Review, and Approval records.

## Current MVP priority

The Personal Mode MVP should progress in this order:

1. Clean PR stack and make foundation changes merge-ready.
2. Provider-aware Owner runtime foundation.
3. Central chat status visibility using provider-aware AgentRun data.
4. Owner ToolCall loop for `task.create`.
5. Task ? Attempt ? Worktree ? WorkerRun ? Artifact/Diff.
6. Owner Review ? user approval ? squash merge.
