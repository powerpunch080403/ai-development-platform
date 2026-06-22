/**
 * External CLI Adapters
 *
 * This package defines the contract and boundaries for future external CLI adapters
 * such as Codex CLI or Antigravity CLI.
 *
 * Key Principles:
 * 1. Adapters MUST NOT execute arbitrary commands directly from user input.
 * 2. Adapters MUST operate exclusively within the provided Git Worktree.
 * 3. Adapters MUST NOT merge directly into the source repository's main/default branch.
 * 4. Adapters MUST leave review, approval, and squash merge to the Owner via the platform.
 * 5. Adapters MUST use the Process Runner baseline for execution and artifact storage.
 */

export * from "@aidp/shared-contracts";

// Future adapter implementations will be exported here.
