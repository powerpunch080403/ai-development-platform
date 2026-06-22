import type {
  AuthState,
  CreateProjectRequest,
  GitRepositoryStatusDto,
  HealthStatus,
  ProjectDto,
  ProjectRepositoryDto,
  RegisterRepositoryRequest,
  ConversationDto,
  MessageDto,
  AgentRunDto,
  ToolRegistryEntryDto,
  CreateConversationRequest,
  AppendMessageRequest,
  CreateAgentRunRequest,
  WorkItemDto, TaskDto, TaskAttemptDto, WorkerDto, CreateWorkItemRequest, CreateTaskRequest, RegisterWorkerRequest,
  GitWorktreeDto,WorktreeStatusDto,WorktreeDiffDto,ArtifactRefDto,
} from "@aidp/shared-contracts";

const DEFAULT_API_BASE_URL = "http://localhost:8000";
const API_BASE_URL = import.meta.env.VITE_AIDP_API_BASE_URL ?? DEFAULT_API_BASE_URL;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init?.headers },
  });

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as
      | { detail?: string | { message?: string } }
      | null;
    const detail = typeof body?.detail === "string" ? body.detail : body?.detail?.message;
    throw new Error(detail ?? (response.status === 401 ? "Not authenticated" : "Request failed"));
  }
  return (await response.json()) as T;
}

export async function getHealth(
  baseUrl: string = DEFAULT_API_BASE_URL,
): Promise<HealthStatus> {
  const response = await fetch(`${baseUrl}/health`, { credentials: "include" });

  if (!response.ok) {
    throw new Error(`Health request failed with status ${response.status}`);
  }

  return (await response.json()) as HealthStatus;
}

export function getMe(): Promise<AuthState> {
  return request<AuthState>("/auth/me");
}

export function pair(code: string, deviceName: string): Promise<AuthState> {
  return request<AuthState>("/auth/pair", {
    method: "POST",
    body: JSON.stringify({ code, device_name: deviceName, device_type: "web_ui" }),
  });
}

export function logout(): Promise<{ status: string }> {
  return request<{ status: string }>("/auth/logout", { method: "POST" });
}

export function listProjects(): Promise<ProjectDto[]> {
  return request<ProjectDto[]>("/projects");
}

export function createProject(input: CreateProjectRequest): Promise<ProjectDto> {
  return request<ProjectDto>("/projects", { method: "POST", body: JSON.stringify(input) });
}

export function listRepositories(projectId: string): Promise<ProjectRepositoryDto[]> {
  return request<ProjectRepositoryDto[]>(`/projects/${projectId}/repositories`);
}

export function registerRepository(
  projectId: string,
  input: RegisterRepositoryRequest,
): Promise<ProjectRepositoryDto> {
  return request<ProjectRepositoryDto>(`/projects/${projectId}/repositories`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function refreshRepositoryStatus(repositoryId: string): Promise<GitRepositoryStatusDto> {
  return request<GitRepositoryStatusDto>(`/repositories/${repositoryId}/refresh-status`, {
    method: "POST",
  });
}

export function listConversations(): Promise<ConversationDto[]> { return request<ConversationDto[]>("/conversations"); }
export function createConversation(input: CreateConversationRequest): Promise<ConversationDto> { return request<ConversationDto>("/conversations", { method: "POST", body: JSON.stringify(input) }); }
export function listMessages(id: string): Promise<MessageDto[]> { return request<MessageDto[]>(`/conversations/${id}/messages`); }
export function appendMessage(id: string, input: AppendMessageRequest): Promise<MessageDto> { return request<MessageDto>(`/conversations/${id}/messages`, { method: "POST", body: JSON.stringify(input) }); }
export function listAgentRuns(id: string): Promise<AgentRunDto[]> { return request<AgentRunDto[]>(`/conversations/${id}/agent-runs`); }
export function createAgentRun(input: CreateAgentRunRequest): Promise<AgentRunDto> { return request<AgentRunDto>("/agent-runs", { method: "POST", body: JSON.stringify(input) }); }
export function listToolRegistry(): Promise<ToolRegistryEntryDto[]> { return request<ToolRegistryEntryDto[]>("/tool-registry"); }
export function listWorkItems(projectId:string):Promise<WorkItemDto[]>{return request<WorkItemDto[]>(`/projects/${projectId}/work-items`)}
export function createWorkItem(projectId:string,input:CreateWorkItemRequest):Promise<WorkItemDto>{return request<WorkItemDto>(`/projects/${projectId}/work-items`,{method:"POST",body:JSON.stringify(input)})}
export function listTasks(projectId:string):Promise<TaskDto[]>{return request<TaskDto[]>(`/projects/${projectId}/tasks`)}
export function createTask(projectId:string,input:CreateTaskRequest):Promise<TaskDto>{return request<TaskDto>(`/projects/${projectId}/tasks`,{method:"POST",body:JSON.stringify(input)})}
export function listAttempts(taskId:string):Promise<TaskAttemptDto[]>{return request<TaskAttemptDto[]>(`/tasks/${taskId}/attempts`)}
export function createAttempt(taskId:string):Promise<TaskAttemptDto>{return request<TaskAttemptDto>(`/tasks/${taskId}/attempts`,{method:"POST",body:"{}"})}
export function listWorkers():Promise<WorkerDto[]>{return request<WorkerDto[]>("/workers")}
export function registerWorker(input:RegisterWorkerRequest):Promise<WorkerDto>{return request<WorkerDto>("/workers",{method:"POST",body:JSON.stringify(input)})}
export function heartbeatWorker(id:string):Promise<WorkerDto>{return request<WorkerDto>(`/workers/${id}/heartbeat`,{method:"POST"})}
export function revokeWorker(id:string):Promise<WorkerDto>{return request<WorkerDto>(`/workers/${id}/revoke`,{method:"POST"})}
export function claimAttempt(workerId:string,attemptId:string):Promise<TaskAttemptDto>{return request<TaskAttemptDto>(`/workers/${workerId}/claim`,{method:"POST",body:JSON.stringify({task_attempt_id:attemptId})})}
export function releaseAttempt(workerId:string,attemptId:string):Promise<TaskAttemptDto>{return request<TaskAttemptDto>(`/workers/${workerId}/release`,{method:"POST",body:JSON.stringify({task_attempt_id:attemptId,next_status:"created"})})}
export function createWorktree(attemptId:string):Promise<GitWorktreeDto>{return request<GitWorktreeDto>(`/task-attempts/${attemptId}/worktree`,{method:"POST"})}
export function getWorktree(attemptId:string):Promise<GitWorktreeDto>{return request<GitWorktreeDto>(`/task-attempts/${attemptId}/worktree`)}
export function getWorktreeStatus(id:string):Promise<WorktreeStatusDto>{return request<WorktreeStatusDto>(`/worktrees/${id}/status`)}
export function getWorktreeDiff(id:string):Promise<WorktreeDiffDto>{return request<WorktreeDiffDto>(`/worktrees/${id}/diff`)}
export function commitWorktree(id:string,message:string):Promise<GitWorktreeDto>{return request<GitWorktreeDto>(`/worktrees/${id}/commit-result`,{method:"POST",body:JSON.stringify({commit_message:message})})}
export function listArtifacts(attemptId:string):Promise<ArtifactRefDto[]>{return request<ArtifactRefDto[]>(`/task-attempts/${attemptId}/artifacts`)}
export function readArtifact(id:string):Promise<{id:string;text:string}>{return request<{id:string;text:string}>(`/artifacts/${id}/text`)}
