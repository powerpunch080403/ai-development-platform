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
