export type HealthStatus = {
  status: "ok";
  service: string;
};

export type AuthUser = {
  id: string;
  display_name: string;
  account_id: string | null;
  account_link_status: string;
};

export type AuthDevice = {
  id: string;
  display_name: string;
  device_type: string;
  created_at: string;
  last_seen_at: string | null;
  revoked_at: string | null;
};

export type AuthSession = {
  id: string;
  device_id: string;
  created_at: string;
  last_seen_at: string;
  idle_expires_at: string;
  absolute_expires_at: string;
  revoked_at: string | null;
};

export type AuthState = {
  user: AuthUser;
  device: AuthDevice;
  session: AuthSession;
};

export type ProjectDto = {
  id: string;
  name: string;
  description: string | null;
  status: "active" | "archived";
  created_at: string;
  updated_at: string;
  archived_at: string | null;
};

export type RepositoryRole = "primary" | "supporting" | "docs" | "infra" | "unknown";

export type ProjectRepositoryDto = {
  id: string;
  project_id: string;
  repository_path: string;
  repository_name: string;
  repository_role: RepositoryRole;
  vcs_type: "git" | "unknown";
  default_branch: string | null;
  current_branch: string | null;
  last_commit_sha: string | null;
  is_dirty: boolean;
  last_status_checked_at: string | null;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
};

export type GitRepositoryStatusDto = {
  repository_id: string;
  is_git_repository: boolean;
  repository_root: string | null;
  current_branch: string | null;
  default_branch: string | null;
  last_commit_sha: string | null;
  is_dirty: boolean | null;
  porcelain: string | null;
  checked_at: string | null;
  error_code: string | null;
  error_message: string | null;
};

export type CreateProjectRequest = { name: string; description?: string };
export type RegisterRepositoryRequest = {
  repository_path: string;
  repository_role?: RepositoryRole;
};

export type ConversationDto = { id: string; project_id: string | null; title: string; status: string; created_at: string; updated_at: string };
export type MessageDto = { id: string; conversation_id: string; agent_run_id: string | null; role: string; content: string; content_type: string; created_at: string };
export type AgentRunDto = { id: string; conversation_id: string | null; project_id: string | null; status: string; purpose: string; input_message_id: string | null; created_at: string; started_at: string | null; completed_at: string | null; failed_at: string | null; cancelled_at: string | null; error_code: string | null; error_message: string | null };
export type AgentRunStepDto = { id: string; agent_run_id: string; step_index: number; step_type: string; status: string; summary: string | null; created_at: string };
export type ToolRegistryEntryDto = { id: string; tool_name: string; tool_version: string; category: string; description: string; has_side_effect: boolean; default_risk_level: string; idempotency_required: boolean; approval_behavior: string; audit_required: boolean; enabled: boolean };
export type ToolCallDto = { id: string; tool_name: string; status: string; arguments_json: Record<string, unknown>; created_at: string };
export type AuditEventDto = { id: string; event_type: string; severity: string; message: string; created_at: string };
export type CreateConversationRequest = { project_id?: string; title?: string };
export type AppendMessageRequest = { role: "user" | "assistant" | "system"; content: string; content_type?: "text" | "json" | "markdown" | "error" };
export type CreateAgentRunRequest = { conversation_id?: string; project_id?: string; purpose: string; input_message_id?: string };
export type CreateToolCallRequest = { tool_name: string; tool_version?: string; idempotency_key?: string; arguments_json: Record<string, unknown> };
