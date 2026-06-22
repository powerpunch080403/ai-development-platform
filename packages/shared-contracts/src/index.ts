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
export type WorkItemDto = { id:string; project_id:string; parent_work_item_id:string|null; title:string; description:string|null; work_item_type:string; status:string; priority:number|null };
export type TaskDto = { id:string; project_id:string; repository_id:string|null; work_item_id:string|null; title:string; instructions:string; status:string; risk_level:string; requested_worker_kind:string|null };
export type TaskAttemptDto = { id:string; task_id:string; project_id:string; repository_id:string|null; claimed_by_worker_id:string|null; status:string; attempt_number:number; lease_expires_at:string|null; result_summary:string|null };
export type WorkerDto = { id:string; display_name:string; worker_kind:string; status:string; capabilities:Record<string,unknown>|null; last_seen_at:string|null; registered_at:string; revoked_at:string|null };
export type CreateWorkItemRequest = { title:string; description?:string; parent_work_item_id?:string; work_item_type:string; priority?:number };
export type CreateTaskRequest = { title:string; instructions:string; repository_id?:string; work_item_id?:string; risk_level:string; requested_worker_kind?:string };
export type RegisterWorkerRequest = { display_name:string; worker_kind:string; capabilities?:Record<string,unknown> };
export type GitWorktreeDto={id:string;task_attempt_id:string;worktree_path:string;branch_name:string;base_branch:string|null;base_commit_sha:string|null;result_commit_sha:string|null;status:string;cleanup_at:string|null};
export type WorktreeStatusDto={is_dirty:boolean;porcelain:string;status:string};
export type WorktreeDiffDto={diff:string;truncated:boolean};
export type ArtifactRefDto={id:string;kind:string;storage_path:string;content_type:string;size_bytes:number;checksum:string;created_at:string};
export type AttemptReviewDto={task_attempt_id:string;task_id:string;task_title:string;repository_name:string;worktree_id:string;base_branch:string;base_commit_sha:string;result_branch:string;result_commit_sha:string;merge_commit_sha:string|null;review_status:string;diff:string;source_clean:boolean;base_head_matches:boolean;merge_possible:boolean};
export type PrepareSquashMergeResponse={merge_possible:boolean;source_clean:boolean;base_head_matches:boolean;current_branch:string|null;current_head:string|null};
