# CLI Adapters

This package defines the contract, context packaging, and constraints for integrating external CLI agents (like Codex CLI or Antigravity CLI) into the AI Development Platform.

## Adapter Contract Principles

1. **No Direct Default Branch Merging**: Adapters operate within isolated Git worktrees tied to a specific `TaskAttempt`. They must never push or merge directly to the source repository's main/default branch.
2. **Process Runner Integration**: All external CLI executions must be routed through the platform's Process Runner to ensure robust timeout handling, scope validation, and log redaction.
3. **No Arbitrary Command UI**: The platform does not expose a general-purpose command runner UI. Instead, the server dictates the specific commands required to run the adapter.
4. **Context Packaging**: Before an adapter is executed, a Context Package is generated. This package provides the adapter with explicit boundaries, the assigned worktree path, constraints, and instructions.

## Supported Adapters (Future)

- **Codex CLI Adapter**: To be implemented.
- **Antigravity CLI Adapter**: To be implemented.
- **External CLI Dry Run**: Used for testing the adapter contract and Process Runner linkage without invoking any real AI/LLM models.
