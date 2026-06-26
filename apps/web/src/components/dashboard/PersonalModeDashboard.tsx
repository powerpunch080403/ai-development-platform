import { useEffect, useMemo, useState } from "react";
import type {
  AgentRunDto,
  AgentRunStepDto,
  ApprovalRequestDto,
  ArtifactRefDto,
  ConversationDto,
  GitWorktreeDto,
  MessageDto,
  ProjectDto,
  ProjectRepositoryDto,
  SettingsSummaryDto,
  TaskAttemptDto,
  TaskDto,
  ToolCallDto,
  WorkerRunDto,
  WorktreeDiffDto,
} from "@aidp/shared-contracts";
import {
  appendMessage,
  createAgentRun,
  createConversation,
  getSettingsSummary,
  getWorktree,
  getWorktreeDiff,
  listAgentRuns,
  listAgentRunSteps,
  listApprovalRequests,
  listAttempts,
  listArtifacts,
  listConversations,
  listMessages,
  listProjects,
  listRepositories,
  listTasks,
  listToolCalls,
  listWorkerRuns,
  openProjectInFileManager,
  readArtifact,
  removeProject,
  startAgentRun,
  updateProject,
} from "../../api/client";
import { ActionMenu, ConfirmDialog, TextInputDialog } from "../ui/AppPrimitives";
import "./inspector-review.css";

type FeedItem =
  | { kind: "message"; time: number; item: MessageDto }
  | { kind: "step"; time: number; item: AgentRunStepDto }
  | { kind: "tool"; time: number; item: ToolCallDto };

type ProjectLight = "green" | "yellow" | "red" | "gray";
type InspectorMode = "overview" | "review";
type DiffLineKind = "add" | "remove" | "context" | "meta";

type DiffLine = {
  kind: DiffLineKind;
  oldLine: number | null;
  newLine: number | null;
  text: string;
};

type DiffFile = {
  id: string;
  path: string;
  additions: number;
  deletions: number;
  lines: DiffLine[];
};

const PIN_STORAGE_KEY = "aidp.pinnedProjectIds";
const THREAD_PIN_STORAGE_KEY = "aidp.pinnedConversationIds";
const DEFAULT_API_BASE_URL = "http://localhost:8000";
const API_BASE_URL = import.meta.env.VITE_AIDP_API_BASE_URL ?? DEFAULT_API_BASE_URL;

async function conversationRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string | { message?: string } } | null;
    const detail = typeof body?.detail === "string" ? body.detail : body?.detail?.message;
    throw new Error(detail ?? "Request failed");
  }
  return (await response.json()) as T;
}

function shortId(id?: string | null) {
  return id ? id.slice(0, 8) : "none";
}

function formatDate(value?: string | null) {
  if (!value) return "unknown";
  return new Date(value).toLocaleString();
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${Math.ceil(value / 1024)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function artifactName(artifact: ArtifactRefDto) {
  const parts = artifact.storage_path.split(/[\\/]/).filter(Boolean);
  return parts.at(-1) ?? artifact.kind;
}

function statusClass(status?: string | null) {
  if (!status) return "status-pill";
  if (["completed", "merged", "cleaned", "approved", "success", "succeeded"].includes(status)) {
    return "status-pill success";
  }
  if (["failed", "worker_failed", "rejected", "expired", "error", "blocked"].includes(status)) {
    return "status-pill danger";
  }
  if (["running", "running_worker", "waiting_for_review", "reviewing", "created", "queued"].includes(status)) {
    return "status-pill active";
  }
  return "status-pill";
}

function statusLabel(status?: string | null) {
  switch (status) {
    case "active":
      return "활성";
    case "archived":
      return "제거됨";
    case "created":
    case "queued":
      return "대기 중";
    case "running":
    case "running_worker":
      return "실행 중";
    case "waiting_for_review":
    case "reviewing":
      return "검토 대기";
    case "committed":
      return "결과 생성됨";
    case "accepted":
    case "approved":
      return "승인됨";
    case "merged":
      return "병합됨";
    case "rejected":
      return "거절됨";
    case "failed":
    case "worker_failed":
      return "실패";
    case "cleanup_pending":
      return "정리 대기";
    case "completed":
    case "succeeded":
      return "완료";
    default:
      return status ?? "알 수 없음";
  }
}

function projectLightLabel(light: ProjectLight) {
  switch (light) {
    case "green":
      return "정상";
    case "yellow":
      return "확인 필요";
    case "red":
      return "문제 있음";
    case "gray":
      return "상태 미확인";
  }
}

function primaryRepository(repositories: ProjectRepositoryDto[]) {
  return repositories.find((item) => item.repository_role === "primary") ?? repositories[0];
}

function diffPathFromHeader(line: string) {
  const match = /^diff --git a\/(.+?) b\/(.+)$/.exec(line);
  return match?.[2] ?? line.replace(/^diff --git\s+/, "");
}

function parseUnifiedDiff(diffText?: string | null): DiffFile[] {
  if (!diffText?.trim()) return [];

  const files: DiffFile[] = [];
  let current: DiffFile | null = null;
  let oldLine = 0;
  let newLine = 0;

  function pushLine(line: DiffLine) {
    if (!current) {
      current = {
        id: "unified-diff",
        path: "Unified diff",
        additions: 0,
        deletions: 0,
        lines: [],
      };
      files.push(current);
    }
    current.lines.push(line);
  }

  for (const rawLine of diffText.split("\n")) {
    if (rawLine.startsWith("diff --git ")) {
      const path = diffPathFromHeader(rawLine);
      current = { id: `${files.length}-${path}`, path, additions: 0, deletions: 0, lines: [] };
      files.push(current);
      pushLine({ kind: "meta", oldLine: null, newLine: null, text: rawLine });
      continue;
    }

    if (rawLine.startsWith("@@")) {
      const hunk = /@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/.exec(rawLine);
      if (hunk) {
        oldLine = Number(hunk[1]);
        newLine = Number(hunk[2]);
      }
      pushLine({ kind: "meta", oldLine: null, newLine: null, text: rawLine });
      continue;
    }

    if (rawLine.startsWith("+++") || rawLine.startsWith("---") || rawLine.startsWith("index ")) {
      pushLine({ kind: "meta", oldLine: null, newLine: null, text: rawLine });
      continue;
    }

    if (rawLine.startsWith("+")) {
      if (current) current.additions += 1;
      pushLine({ kind: "add", oldLine: null, newLine, text: rawLine });
      newLine += 1;
      continue;
    }

    if (rawLine.startsWith("-")) {
      if (current) current.deletions += 1;
      pushLine({ kind: "remove", oldLine, newLine: null, text: rawLine });
      oldLine += 1;
      continue;
    }

    if (rawLine.startsWith(" ")) {
      pushLine({ kind: "context", oldLine, newLine, text: rawLine });
      oldLine += 1;
      newLine += 1;
      continue;
    }

    pushLine({ kind: "meta", oldLine: null, newLine: null, text: rawLine });
  }

  return files.filter((file) => file.lines.length > 0);
}

export function PersonalModeDashboard() {
  const [projects, setProjects] = useState<ProjectDto[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [repositories, setRepositories] = useState<ProjectRepositoryDto[]>([]);
  const [conversations, setConversations] = useState<ConversationDto[]>([]);
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [settings, setSettings] = useState<SettingsSummaryDto | null>(null);

  const [tasks, setTasks] = useState<TaskDto[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [attempts, setAttempts] = useState<TaskAttemptDto[]>([]);
  const [selectedAttemptId, setSelectedAttemptId] = useState<string | null>(null);

  const [workerRuns, setWorkerRuns] = useState<WorkerRunDto[]>([]);
  const [worktree, setWorktree] = useState<GitWorktreeDto | null>(null);
  const [diff, setDiff] = useState<WorktreeDiffDto | null>(null);
  const [artifacts, setArtifacts] = useState<ArtifactRefDto[]>([]);
  const [approvals, setApprovals] = useState<ApprovalRequestDto[]>([]);

  const [agentRuns, setAgentRuns] = useState<AgentRunDto[]>([]);
  const [selectedAgentRunId, setSelectedAgentRunId] = useState<string | null>(null);
  const [messages, setMessages] = useState<MessageDto[]>([]);
  const [agentRunSteps, setAgentRunSteps] = useState<AgentRunStepDto[]>([]);
  const [toolCalls, setToolCalls] = useState<ToolCallDto[]>([]);

  const [activeInspectorMode, setActiveInspectorMode] = useState<InspectorMode>("overview");
  const [expandedDiffFileIds, setExpandedDiffFileIds] = useState<string[]>([]);
  const [selectedArtifactId, setSelectedArtifactId] = useState<string | null>(null);
  const [artifactText, setArtifactText] = useState<string | null>(null);
  const [artifactError, setArtifactError] = useState<string | null>(null);
  const [artifactLoading, setArtifactLoading] = useState(false);
  const [isInspectorOpen, setIsInspectorOpen] = useState(true);
  const [renameProject, setRenameProject] = useState<ProjectDto | null>(null);
  const [removeProjectTarget, setRemoveProjectTarget] = useState<ProjectDto | null>(null);
  const [renameConversation, setRenameConversation] = useState<ConversationDto | null>(null);
  const [removeConversationTarget, setRemoveConversationTarget] = useState<ConversationDto | null>(null);
  const [pinnedProjectIds, setPinnedProjectIds] = useState<string[]>(() => {
    if (typeof window === "undefined") return [];
    try {
      return JSON.parse(window.localStorage.getItem(PIN_STORAGE_KEY) ?? "[]") as string[];
    } catch {
      return [];
    }
  });
  const [pinnedConversationIds, setPinnedConversationIds] = useState<string[]>(() => {
    if (typeof window === "undefined") return [];
    try {
      return JSON.parse(window.localStorage.getItem(THREAD_PIN_STORAGE_KEY) ?? "[]") as string[];
    } catch {
      return [];
    }
  });
  const [isLoadingConversations, setIsLoadingConversations] = useState(true);
  const [draftMessage, setDraftMessage] = useState("");
  const [isSendingMessage, setIsSendingMessage] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  async function refreshProjects() {
    const items = await listProjects();
    setProjects(items);
    setSelectedProjectId((current) =>
      current && items.some((item) => item.id === current) ? current : items[0]?.id ?? null,
    );
  }

  async function refreshConversations() {
    const items = await listConversations();
    setConversations(items);
    setSelectedConversationId((current) =>
      current && items.some((item) => item.id === current) ? current : items[0]?.id ?? null,
    );
  }

  useEffect(() => {
    getSettingsSummary().then(setSettings).catch(console.error);
    refreshProjects().catch(console.error);
    refreshConversations().catch(console.error).finally(() => setIsLoadingConversations(false));
    listApprovalRequests().then(setApprovals).catch(console.error);
  }, []);

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(PIN_STORAGE_KEY, JSON.stringify(pinnedProjectIds));
    }
  }, [pinnedProjectIds]);

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(THREAD_PIN_STORAGE_KEY, JSON.stringify(pinnedConversationIds));
    }
  }, [pinnedConversationIds]);

  useEffect(() => {
    if (!selectedProjectId) {
      setRepositories([]);
      setTasks([]);
      setSelectedTaskId(null);
      return;
    }

    listRepositories(selectedProjectId).then(setRepositories).catch(console.error);
    listTasks(selectedProjectId)
      .then((items) => {
        setTasks(items);
        setSelectedTaskId((current) =>
          current && items.some((item) => item.id === current) ? current : items[0]?.id ?? null,
        );
      })
      .catch(console.error);
  }, [selectedProjectId]);

  useEffect(() => {
    if (!selectedTaskId) {
      setAttempts([]);
      setSelectedAttemptId(null);
      return;
    }

    listAttempts(selectedTaskId)
      .then((items) => {
        setAttempts(items);
        setSelectedAttemptId((current) =>
          current && items.some((item) => item.id === current)
            ? current
            : items.at(-1)?.id ?? null,
        );
      })
      .catch(console.error);
  }, [selectedTaskId]);

  useEffect(() => {
    if (!selectedAttemptId) {
      setWorkerRuns([]);
      setArtifacts([]);
      setWorktree(null);
      setDiff(null);
      setSelectedArtifactId(null);
      return;
    }

    listWorkerRuns(selectedAttemptId).then(setWorkerRuns).catch(console.error);
    listArtifacts(selectedAttemptId).then(setArtifacts).catch(console.error);
    getWorktree(selectedAttemptId)
      .then((item) => {
        setWorktree(item);
        if (item) {
          getWorktreeDiff(item.id).then(setDiff).catch(() => setDiff(null));
        } else {
          setDiff(null);
        }
      })
      .catch(() => {
        setWorktree(null);
        setDiff(null);
      });
  }, [selectedAttemptId]);

  const selectedConversation =
    conversations.find((item) => item.id === selectedConversationId) ??
    (selectedProjectId ? conversations.find((item) => item.project_id === selectedProjectId) : undefined) ??
    conversations.find((item) => !item.project_id) ??
    conversations[0];

  useEffect(() => {
    if (!selectedConversation) {
      setMessages([]);
      setAgentRuns([]);
      setSelectedAgentRunId(null);
      return;
    }

    listMessages(selectedConversation.id).then(setMessages).catch(console.error);
    listAgentRuns(selectedConversation.id)
      .then((items) => {
        setAgentRuns(items);
        setSelectedAgentRunId((current) =>
          current && items.some((item) => item.id === current) ? current : items[0]?.id ?? null,
        );
      })
      .catch(console.error);
  }, [selectedConversation?.id]);

  useEffect(() => {
    if (!selectedAgentRunId) {
      setAgentRunSteps([]);
      setToolCalls([]);
      return;
    }

    listAgentRunSteps(selectedAgentRunId).then(setAgentRunSteps).catch(console.error);
    listToolCalls(selectedAgentRunId).then(setToolCalls).catch(console.error);
  }, [selectedAgentRunId]);

  const selectedProject = projects.find((item) => item.id === selectedProjectId);
  const selectedTask = tasks.find((item) => item.id === selectedTaskId);
  const selectedAttempt = attempts.find((item) => item.id === selectedAttemptId);
  const latestWorkerRun = workerRuns.at(-1);
  const selectedRepository = primaryRepository(repositories);
  const selectedArtifact = artifacts.find((artifact) => artifact.id === selectedArtifactId) ?? null;
  const diffFiles = useMemo(() => parseUnifiedDiff(diff?.diff), [diff?.diff]);
  const totalAdditions = diffFiles.reduce((sum, file) => sum + file.additions, 0);
  const totalDeletions = diffFiles.reduce((sum, file) => sum + file.deletions, 0);

  useEffect(() => {
    setExpandedDiffFileIds(diffFiles.map((file) => file.id));
  }, [diffFiles.map((file) => file.id).join("|")]);

  const sortedProjects = useMemo(() => {
    return [...projects].sort((a, b) => {
      const aPinned = pinnedProjectIds.includes(a.id);
      const bPinned = pinnedProjectIds.includes(b.id);
      if (aPinned !== bPinned) return aPinned ? -1 : 1;
      return a.name.localeCompare(b.name);
    });
  }, [pinnedProjectIds, projects]);

  const pinnedConversations = useMemo(
    () => conversations.filter((item) => pinnedConversationIds.includes(item.id)),
    [conversations, pinnedConversationIds],
  );

  const projectConversationMap = useMemo(() => {
    const map = new Map<string, ConversationDto[]>();
    for (const conversation of conversations) {
      if (!conversation.project_id || pinnedConversationIds.includes(conversation.id)) continue;
      const items = map.get(conversation.project_id) ?? [];
      items.push(conversation);
      map.set(conversation.project_id, items);
    }
    return map;
  }, [conversations, pinnedConversationIds]);

  const globalConversations = useMemo(
    () => conversations.filter((item) => !item.project_id && !pinnedConversationIds.includes(item.id)).slice(0, 12),
    [conversations, pinnedConversationIds],
  );

  const visibleApprovals = useMemo(
    () => approvals.filter((item) => !selectedProjectId || item.project_id === selectedProjectId || item.project_id === null),
    [approvals, selectedProjectId],
  );

  const feedItems = useMemo<FeedItem[]>(
    () =>
      [
        ...messages.map((item) => ({
          kind: "message" as const,
          time: new Date(item.created_at).getTime(),
          item,
        })),
        ...agentRunSteps.map((item) => ({
          kind: "step" as const,
          time: new Date(item.created_at).getTime(),
          item,
        })),
        ...toolCalls.map((item) => ({
          kind: "tool" as const,
          time: new Date(item.created_at).getTime(),
          item,
        })),
      ].sort((a, b) => a.time - b.time),
    [agentRunSteps, messages, toolCalls],
  );

  function getProjectLight(project: ProjectDto): ProjectLight {
    if (project.status === "archived") return "red";
    if (project.id !== selectedProjectId) return "gray";
    if (latestWorkerRun?.status === "failed" || latestWorkerRun?.status === "worker_failed") return "red";
    if (visibleApprovals.length > 0) return "yellow";
    if (repositories.some((repository) => repository.is_dirty)) return "yellow";
    if (repositories.length === 0) return "gray";
    return "green";
  }

  function toggleDiffFile(fileId: string) {
    setExpandedDiffFileIds((current) =>
      current.includes(fileId) ? current.filter((id) => id !== fileId) : [...current, fileId],
    );
  }

  function collapseAllDiffFiles() {
    setExpandedDiffFileIds([]);
  }

  function expandAllDiffFiles() {
    setExpandedDiffFileIds(diffFiles.map((file) => file.id));
  }

  async function openArtifactPanel(artifact: ArtifactRefDto) {
    setSelectedArtifactId(artifact.id);
    setArtifactText(null);
    setArtifactError(null);
    setArtifactLoading(true);
    setIsInspectorOpen(true);
    setActiveInspectorMode("overview");
    try {
      const result = await readArtifact(artifact.id);
      setArtifactText(result.text);
    } catch (error) {
      setArtifactError(error instanceof Error ? error.message : String(error));
    } finally {
      setArtifactLoading(false);
    }
  }

  async function handleGeneralChat() {
    setActionError(null);
    try {
      const conversation = await createConversation({ title: "새 채팅" });
      await refreshConversations();
      setSelectedConversationId(conversation.id);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    }
  }

  async function handleProjectChat(project: ProjectDto) {
    setActionError(null);
    try {
      const conversation = await createConversation({
        project_id: project.id,
        title: `${project.name} 채팅`,
      });
      await refreshConversations();
      setSelectedProjectId(project.id);
      setSelectedConversationId(conversation.id);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    }
  }

  async function handleRenameConversation(conversation: ConversationDto, nextTitle: string) {
    setActionError(null);
    try {
      await conversationRequest<ConversationDto>(`/conversations/${conversation.id}`, {
        method: "PATCH",
        body: JSON.stringify({ title: nextTitle }),
      });
      await refreshConversations();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    }
  }

  async function handleRemoveConversation(conversation: ConversationDto) {
    setActionError(null);
    try {
      await conversationRequest<ConversationDto>(`/conversations/${conversation.id}`, { method: "DELETE" });
      setPinnedConversationIds((current) => current.filter((id) => id !== conversation.id));
      await refreshConversations();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    }
  }

  function togglePinnedConversation(conversation: ConversationDto) {
    setPinnedConversationIds((current) =>
      current.includes(conversation.id)
        ? current.filter((id) => id !== conversation.id)
        : [conversation.id, ...current],
    );
  }

  async function handleRenameProject(project: ProjectDto, nextName: string) {
    setActionError(null);
    try {
      await updateProject(project.id, { name: nextName });
      await refreshProjects();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    }
  }

  async function handleRemoveProject(project: ProjectDto) {
    setActionError(null);
    try {
      await removeProject(project.id);
      await refreshProjects();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    }
  }

  async function handleOpenProject(project: ProjectDto) {
    setActionError(null);
    try {
      await openProjectInFileManager(project.id);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    }
  }

  function togglePinnedProject(project: ProjectDto) {
    setPinnedProjectIds((current) =>
      current.includes(project.id)
        ? current.filter((id) => id !== project.id)
        : [project.id, ...current],
    );
  }

  async function handleSendMessage() {
    if (!draftMessage.trim() || !selectedConversation) return;

    setIsSendingMessage(true);
    setSendError(null);
    try {
      const message = await appendMessage(selectedConversation.id, {
        role: "user",
        content: draftMessage.trim(),
        content_type: "text",
      });
      const purpose =
        draftMessage.trim().slice(0, 50) + (draftMessage.trim().length > 50 ? "..." : "");
      const run = await createAgentRun({
        conversation_id: selectedConversation.id,
        project_id: selectedConversation.project_id || undefined,
        purpose,
        input_message_id: message.id,
      });

      await startAgentRun(run.id);
      setDraftMessage("");
      setMessages(await listMessages(selectedConversation.id));
      setAgentRuns(await listAgentRuns(selectedConversation.id));
      setSelectedAgentRunId(run.id);
      setAgentRunSteps(await listAgentRunSteps(run.id));
      setToolCalls(await listToolCalls(run.id));
    } catch (error) {
      setSendError(error instanceof Error ? error.message : String(error));
    } finally {
      setIsSendingMessage(false);
    }
  }

  function renderConversationRow(conversation: ConversationDto, variant: "sidebar" | "project" | "pinned") {
    const isPinned = pinnedConversationIds.includes(conversation.id);
    const rowClass = variant === "project" ? "project-chat-row" : "sidebar-row";
    return (
      <li key={conversation.id} className="conversation-row-shell">
        <button
          type="button"
          className={conversation.id === selectedConversation?.id ? `${rowClass} active` : rowClass}
          onClick={() => setSelectedConversationId(conversation.id)}
        >
          <span>{isPinned ? "★ " : ""}{conversation.title}</span>
        </button>
        <ActionMenu
          ariaLabel="채팅 더보기"
          items={[
            { label: isPinned ? "채팅 고정 해제" : "채팅 고정", onSelect: () => togglePinnedConversation(conversation) },
            { label: "채팅 이름 변경", onSelect: () => setRenameConversation(conversation) },
            { label: "제거하기", destructive: true, onSelect: () => setRemoveConversationTarget(conversation) },
          ]}
        />
      </li>
    );
  }

  function renderArtifactPanel() {
    if (!selectedArtifact) return null;
    return (
      <section className="artifact-inspector-panel">
        <header className="artifact-inspector-header">
          <button type="button" className="secondary compact-button" onClick={() => setSelectedArtifactId(null)}>
            ← Overview
          </button>
          <div>
            <h3>{artifactName(selectedArtifact)}</h3>
            <p>{selectedArtifact.kind} · {formatBytes(selectedArtifact.size_bytes)} · {selectedArtifact.content_type}</p>
          </div>
        </header>
        <div className="artifact-meta-grid">
          <span>ID</span><code>{selectedArtifact.id}</code>
          <span>Created</span><small>{formatDate(selectedArtifact.created_at)}</small>
          <span>Checksum</span><code>{shortId(selectedArtifact.checksum)}</code>
        </div>
        {artifactLoading && <p className="empty-state">Artifact를 불러오는 중...</p>}
        {artifactError && <p className="error-inline">Artifact를 읽지 못했습니다: {artifactError}</p>}
        {artifactText !== null && <pre className="artifact-text-view">{artifactText}</pre>}
      </section>
    );
  }

  return (
    <div className={isInspectorOpen ? "codex-layout" : "codex-layout inspector-collapsed"}>
      <aside className="codex-sidebar">
        <nav className="app-rail" aria-label="앱 탐색">
          <button type="button" className="rail-button" onClick={() => void handleGeneralChat()}>
            ✎ <span>새 채팅</span>
          </button>
          <button type="button" className="rail-button" onClick={() => setActionError("검색은 다음 UI foundation PR에서 Command Palette로 연결합니다.")}>⌕ <span>검색</span></button>
        </nav>

        {pinnedConversations.length > 0 && (
          <section className="side-group pinned-group">
            <div className="side-title">고정된 스레드</div>
            <ul className="sidebar-list">
              {pinnedConversations.map((conversation) => renderConversationRow(conversation, "pinned"))}
            </ul>
          </section>
        )}

        <section className="side-group">
          <div className="side-title">프로젝트</div>
          <ul className="project-list">
            {sortedProjects.map((project) => {
              const light = getProjectLight(project);
              const isPinned = pinnedProjectIds.includes(project.id);
              const projectChats = projectConversationMap.get(project.id) ?? [];
              return (
                <li key={project.id} className="project-stack">
                  <div className="project-row-shell">
                    <button
                      type="button"
                      className={project.id === selectedProjectId ? "project-row active" : "project-row"}
                      onClick={() => setSelectedProjectId(project.id)}
                    >
                      <span className={`project-light ${light}`} title={projectLightLabel(light)} />
                      <span className="project-name">{isPinned ? "★ " : ""}{project.name}</span>
                    </button>
                    <button type="button" className="project-icon-button" title="프로젝트 새 채팅" onClick={() => void handleProjectChat(project)}>＋</button>
                    <ActionMenu
                      ariaLabel="프로젝트 더보기"
                      items={[
                        { label: isPinned ? "프로젝트 고정 해제" : "프로젝트 고정", onSelect: () => togglePinnedProject(project) },
                        { label: "탐색기에서 열기", onSelect: () => void handleOpenProject(project) },
                        { label: "프로젝트 이름 변경", onSelect: () => setRenameProject(project) },
                        { label: "제거하기", destructive: true, onSelect: () => setRemoveProjectTarget(project) },
                      ]}
                    />
                  </div>
                  {project.id === selectedProjectId && projectChats.length > 0 && (
                    <ul className="project-chat-list">
                      {projectChats.map((conversation) => renderConversationRow(conversation, "project"))}
                    </ul>
                  )}
                </li>
              );
            })}
          </ul>
          {projects.length === 0 && <p className="empty-state">프로젝트가 없습니다.</p>}
        </section>

        <section className="side-group">
          <div className="side-title">채팅</div>
          <ul className="sidebar-list">
            {globalConversations.map((conversation) => renderConversationRow(conversation, "sidebar"))}
          </ul>
          {!isLoadingConversations && globalConversations.length === 0 && <p className="empty-state">채팅이 없습니다.</p>}
        </section>

        <section className="side-group bottom-group">
          <div className="side-title">설정</div>
          <p className="settings-line">승인: {settings?.approval_mode ?? "unknown"}</p>
          <p className="settings-line">어댑터: {settings?.adapter_summary ?? "unknown"}</p>
        </section>
      </aside>

      <main className="codex-chat">
        <header className="chat-topbar">
          <div>
            <h2>{selectedConversation?.title ?? "대화 없음"}</h2>
            <p>{selectedProject?.name ?? "프로젝트 미선택"}</p>
          </div>
          {!isInspectorOpen && (
            <button type="button" className="secondary" onClick={() => setIsInspectorOpen(true)}>패널 열기</button>
          )}
        </header>

        <section className="chat-feed">
          {isLoadingConversations ? (
            <p className="empty-state">대화를 불러오는 중...</p>
          ) : feedItems.length > 0 || artifacts.length > 0 ? (
            <>
              {feedItems.map((feedItem) => {
                if (feedItem.kind === "message") {
                  const message = feedItem.item;
                  return (
                    <article key={`message-${message.id}`} className={message.role === "user" ? "chat-bubble user" : "chat-bubble assistant"}>
                      <div className="bubble-label">{message.role === "user" ? "사용자" : "Owner"}</div>
                      <pre>{message.content}</pre>
                    </article>
                  );
                }

                if (feedItem.kind === "step") {
                  const step = feedItem.item;
                  return (
                    <article key={`step-${step.id}`} className="event-card step">
                      <strong>Owner 작업</strong>
                      <span className={statusClass(step.status)}>{statusLabel(step.status)}</span>
                      <p>{step.summary ?? step.step_type}</p>
                    </article>
                  );
                }

                const tool = feedItem.item;
                return (
                  <article key={`tool-${tool.id}`} className="event-card tool">
                    <strong>Owner가 도구를 사용했습니다</strong>
                    <span className={statusClass(tool.status)}>{statusLabel(tool.status)}</span>
                    <p>{tool.tool_name}</p>
                  </article>
                );
              })}
              {artifacts.length > 0 && (
                <article className="chat-bubble assistant artifact-feed-card">
                  <div className="bubble-label">Artifacts</div>
                  <p>현재 Attempt에서 생성된 파일입니다. 클릭하면 오른쪽에서 내용을 확인할 수 있습니다.</p>
                  <div className="artifact-chip-list">
                    {artifacts.map((artifact) => (
                      <button
                        type="button"
                        key={artifact.id}
                        className={artifact.id === selectedArtifactId ? "artifact-chip active" : "artifact-chip"}
                        onClick={() => void openArtifactPanel(artifact)}
                      >
                        <span>{artifact.kind}</span>
                        <strong>{artifactName(artifact)}</strong>
                        <small>{formatBytes(artifact.size_bytes)}</small>
                      </button>
                    ))}
                  </div>
                </article>
              )}
            </>
          ) : (
            <div className="chat-empty">
              <h2>Owner에게 작업을 요청하세요</h2>
              <p>왼쪽에서 프로젝트와 채팅을 고르면 사용자와 Owner의 대화가 여기에 표시됩니다.</p>
            </div>
          )}
        </section>

        <footer className="composer">
          <input
            type="text"
            value={draftMessage}
            onChange={(event) => setDraftMessage(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") void handleSendMessage();
            }}
            placeholder="Owner에게 작업을 부탁하세요"
            disabled={isSendingMessage || !selectedConversation}
          />
          <button type="button" onClick={handleSendMessage} disabled={!draftMessage.trim() || isSendingMessage || !selectedConversation}>
            {isSendingMessage ? "전송 중" : "보내기"}
          </button>
        </footer>
        {sendError && <p className="error">전송 실패: {sendError}</p>}
        {actionError && <p className="error">작업 실패: {actionError}</p>}
      </main>

      {isInspectorOpen && (
        <aside className="codex-review antigravity-review-shell">
          <header className="review-topbar antigravity-review-topbar">
            <button type="button" className={activeInspectorMode === "overview" ? "tab-button active" : "tab-button"} onClick={() => setActiveInspectorMode("overview")}>Overview</button>
            <button type="button" className={activeInspectorMode === "review" ? "tab-button active" : "tab-button"} onClick={() => setActiveInspectorMode("review")}>Review</button>
            <button type="button" className="panel-toggle" onClick={() => setIsInspectorOpen(false)}>숨기기</button>
          </header>

          {selectedArtifact ? renderArtifactPanel() : activeInspectorMode === "overview" ? (
            <section className="review-panel overview-inspector-panel">
              <header className="review-changes-titlebar">
                <h3>Overview</h3>
                <span className={statusClass(selectedAttempt?.status)}>{statusLabel(selectedAttempt?.status)}</span>
              </header>
              <div className="overview-grid">
                <article className="status-card">
                  <span>Task</span>
                  {selectedTask ? (
                    <>
                      <strong>{selectedTask.title}</strong>
                      <span className={statusClass(selectedTask.status)}>{statusLabel(selectedTask.status)}</span>
                      <p>{selectedTask.instructions}</p>
                    </>
                  ) : (
                    <p className="empty-state">선택된 Task가 없습니다.</p>
                  )}
                </article>
                <article className="status-card">
                  <span>Attempt</span>
                  {selectedAttempt ? (
                    <>
                      <strong>Attempt #{selectedAttempt.attempt_number}</strong>
                      <span className={statusClass(selectedAttempt.status)}>{statusLabel(selectedAttempt.status)}</span>
                      {selectedAttempt.result_summary && <p>{selectedAttempt.result_summary}</p>}
                      <code>{selectedAttempt.id}</code>
                    </>
                  ) : (
                    <p className="empty-state">선택된 Attempt가 없습니다.</p>
                  )}
                </article>
                {latestWorkerRun && (
                  <article className="status-card">
                    <span>WorkerRun</span>
                    <strong>{shortId(latestWorkerRun.id)}</strong>
                    <span className={statusClass(latestWorkerRun.status)}>{statusLabel(latestWorkerRun.status)}</span>
                    <small>{latestWorkerRun.adapter_kind}</small>
                    {latestWorkerRun.error_message && <p className="error-inline">{latestWorkerRun.error_message}</p>}
                  </article>
                )}
                {worktree && (
                  <article className="status-card">
                    <span>Worktree</span>
                    <strong>{statusLabel(worktree.status)}</strong>
                    <code>{worktree.branch_name}</code>
                    <small>{worktree.worktree_path}</small>
                  </article>
                )}
                {selectedRepository && (
                  <article className="status-card">
                    <span>Repository</span>
                    <strong>{selectedRepository.repository_name}</strong>
                    <small>{selectedRepository.repository_path}</small>
                  </article>
                )}
                <article className="status-card">
                  <span>Artifacts</span>
                  {artifacts.length > 0 ? (
                    <div className="artifact-mini-list">
                      {artifacts.map((artifact) => (
                        <button type="button" key={artifact.id} className="artifact-mini-row" onClick={() => void openArtifactPanel(artifact)}>
                          <strong>{artifact.kind}</strong>
                          <small>{artifactName(artifact)} · {formatBytes(artifact.size_bytes)}</small>
                        </button>
                      ))}
                    </div>
                  ) : (
                    <p className="empty-state">생성된 artifact가 없습니다.</p>
                  )}
                </article>
                <article className="status-card">
                  <span>AgentRun</span>
                  <select value={selectedAgentRunId || ""} onChange={(event) => setSelectedAgentRunId(event.target.value || null)}>
                    <option value="">실행 선택</option>
                    {agentRuns.map((run) => (
                      <option key={run.id} value={run.id}>{shortId(run.id)} · {statusLabel(run.status)} · {run.purpose}</option>
                    ))}
                  </select>
                </article>
                {visibleApprovals.length > 0 && (
                  <article className="status-card">
                    <span>Approval Requests</span>
                    {visibleApprovals.map((approval) => (
                      <p key={approval.id}>{approval.title} · {statusLabel(approval.status)}</p>
                    ))}
                  </article>
                )}
                {toolCalls.length > 0 && (
                  <article className="status-card">
                    <span>Raw Tool Calls</span>
                    <pre>{JSON.stringify(toolCalls, null, 2)}</pre>
                  </article>
                )}
                <article className="grant-card">
                  <h3>권한</h3>
                  <p>{settings?.active_grant_placeholder || "[Grant 정보 없음]"}</p>
                  <small>Updated {formatDate(selectedConversation?.updated_at)}</small>
                </article>
              </div>
            </section>
          ) : (
            <section className="review-panel review-changes-panel">
              <header className="review-changes-titlebar">
                <div>
                  <h3>Review Changes</h3>
                  <p>{selectedTask?.title ?? "선택된 Task 없음"}</p>
                </div>
                <div className="review-actions">
                  <button type="button" className="review-icon-button" title="전체 펼치기" onClick={expandAllDiffFiles}>▦</button>
                  <button type="button" className="review-icon-button" title="전체 접기" onClick={collapseAllDiffFiles}>⌃</button>
                  <button type="button" className="review-icon-button" title="검색은 다음 PR에서 연결">⌕</button>
                </div>
              </header>

              <div className="review-change-summary">
                <span>{diffFiles.length} files changed</span>
                <strong className="diff-addition">+{totalAdditions}</strong>
                <strong className="diff-deletion">-{totalDeletions}</strong>
                {diff?.truncated && <span className="status-pill danger">truncated</span>}
              </div>

              {diffFiles.length > 0 ? (
                <div className="changed-file-list">
                  {diffFiles.map((file) => {
                    const expanded = expandedDiffFileIds.includes(file.id);
                    return (
                      <article key={file.id} className="changed-file-card">
                        <button type="button" className="changed-file-header" onClick={() => toggleDiffFile(file.id)}>
                          <span className="file-icon">◆</span>
                          <strong>{file.path}</strong>
                          <span className="diff-addition">+{file.additions}</span>
                          <span className="diff-deletion">-{file.deletions}</span>
                          <span>{expanded ? "⌄" : "›"}</span>
                        </button>
                        {expanded && (
                          <div className="diff-line-table">
                            {file.lines.map((line, index) => (
                              <div key={`${file.id}-${index}`} className={`diff-line ${line.kind}`}>
                                <span className="diff-line-no">{line.oldLine ?? ""}</span>
                                <span className="diff-line-no">{line.newLine ?? ""}</span>
                                <code>{line.text}</code>
                              </div>
                            ))}
                          </div>
                        )}
                      </article>
                    );
                  })}
                </div>
              ) : (
                <div className="empty-review">
                  <h2>표시할 코드 변경이 없습니다</h2>
                  <p>Worker가 result commit을 만들거나 worktree diff가 생기면 여기에 파일별 변경 내용이 표시됩니다.</p>
                </div>
              )}
            </section>
          )}
        </aside>
      )}

      <TextInputDialog
        open={renameProject !== null}
        title="프로젝트 이름 변경"
        label="프로젝트 이름"
        initialValue={renameProject?.name ?? ""}
        onOpenChange={(open) => !open && setRenameProject(null)}
        onSubmit={(value) => renameProject && handleRenameProject(renameProject, value)}
      />
      <ConfirmDialog
        open={removeProjectTarget !== null}
        title="프로젝트 제거"
        description="이 프로젝트를 목록에서 제거합니다. 로컬 파일은 삭제하지 않습니다."
        confirmLabel="제거하기"
        destructive
        onOpenChange={(open) => !open && setRemoveProjectTarget(null)}
        onConfirm={() => removeProjectTarget && handleRemoveProject(removeProjectTarget)}
      />
      <TextInputDialog
        open={renameConversation !== null}
        title="채팅 이름 변경"
        label="채팅 이름"
        initialValue={renameConversation?.title ?? ""}
        onOpenChange={(open) => !open && setRenameConversation(null)}
        onSubmit={(value) => renameConversation && handleRenameConversation(renameConversation, value)}
      />
      <ConfirmDialog
        open={removeConversationTarget !== null}
        title="채팅 제거"
        description="이 채팅을 목록에서 제거합니다."
        confirmLabel="제거하기"
        destructive
        onOpenChange={(open) => !open && setRemoveConversationTarget(null)}
        onConfirm={() => removeConversationTarget && handleRemoveConversation(removeConversationTarget)}
      />
    </div>
  );
}
