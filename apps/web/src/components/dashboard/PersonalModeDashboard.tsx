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
} from "../../api/client";

type FeedItem =
  | { kind: "message"; time: number; item: MessageDto }
  | { kind: "step"; time: number; item: AgentRunStepDto }
  | { kind: "tool"; time: number; item: ToolCallDto };

function shortId(id?: string | null) {
  return id ? id.slice(0, 8) : "none";
}

function formatDate(value?: string | null) {
  if (!value) return "unknown";
  return new Date(value).toLocaleString();
}

function statusClass(status?: string | null) {
  if (!status) return "status-pill";
  if (["completed", "merged", "cleaned", "approved", "success"].includes(status)) {
    return "status-pill success";
  }
  if (["failed", "worker_failed", "rejected", "expired", "error"].includes(status)) {
    return "status-pill danger";
  }
  if (["running", "running_worker", "waiting_for_review", "reviewing"].includes(status)) {
    return "status-pill active";
  }
  return "status-pill";
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

  const [activeInspectorTab, setActiveInspectorTab] = useState<"review" | "changes" | "status">("review");
  const [isLoadingConversations, setIsLoadingConversations] = useState(true);
  const [draftMessage, setDraftMessage] = useState("");
  const [isSendingMessage, setIsSendingMessage] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);

  useEffect(() => {
    getSettingsSummary().then(setSettings).catch(console.error);
    listProjects()
      .then((items) => {
        setProjects(items);
        if (items.length > 0) setSelectedProjectId(items[0].id);
      })
      .catch(console.error);

    listConversations()
      .then((items) => {
        setConversations(items);
        if (items.length > 0) setSelectedConversationId(items[0].id);
      })
      .catch(console.error)
      .finally(() => setIsLoadingConversations(false));

    listApprovalRequests().then(setApprovals).catch(console.error);
  }, []);

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

  const projectConversations = useMemo(() => {
    if (!selectedProjectId) return conversations;
    return conversations.filter((item) => item.project_id === selectedProjectId || !item.project_id);
  }, [conversations, selectedProjectId]);

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
        project_id: selectedProjectId || undefined,
        purpose,
        input_message_id: message.id,
      });

      setDraftMessage("");
      setMessages(await listMessages(selectedConversation.id));
      setAgentRuns(await listAgentRuns(selectedConversation.id));
      setSelectedAgentRunId(run.id);
    } catch (error) {
      setSendError(error instanceof Error ? error.message : String(error));
    } finally {
      setIsSendingMessage(false);
    }
  }

  return (
    <div className="codex-layout">
      <aside className="codex-sidebar">
        <div className="sidebar-actions">
          <button type="button" className="ghost-button" disabled>＋ 새 채팅</button>
          <button type="button" className="ghost-button" disabled>⌕ 검색</button>
        </div>

        <section className="side-group">
          <div className="side-title">프로젝트</div>
          <select
            value={selectedProjectId || ""}
            onChange={(event) => setSelectedProjectId(event.target.value || null)}
          >
            <option value="">프로젝트 선택</option>
            {projects.map((project) => (
              <option key={project.id} value={project.id}>{project.name}</option>
            ))}
          </select>
          {selectedProject ? (
            <p className="side-note">{selectedProject.description || "설명 없음"}</p>
          ) : (
            <p className="empty-state">프로젝트가 없습니다.</p>
          )}
        </section>

        <section className="side-group">
          <div className="side-title">채팅</div>
          <ul className="sidebar-list">
            {projectConversations.map((conversation) => (
              <li key={conversation.id}>
                <button
                  type="button"
                  className={
                    conversation.id === selectedConversation?.id
                      ? "sidebar-row active"
                      : "sidebar-row"
                  }
                  onClick={() => setSelectedConversationId(conversation.id)}
                >
                  <span>{conversation.title}</span>
                  <small>{conversation.status}</small>
                </button>
              </li>
            ))}
          </ul>
          {!isLoadingConversations && projectConversations.length === 0 && (
            <p className="empty-state">채팅이 없습니다.</p>
          )}
        </section>

        <section className="side-group">
          <div className="side-title">워커-오너 룸</div>
          <ul className="sidebar-list">
            {tasks.map((task) => (
              <li key={task.id}>
                <button
                  type="button"
                  className={task.id === selectedTaskId ? "sidebar-row active" : "sidebar-row"}
                  onClick={() => setSelectedTaskId(task.id)}
                >
                  <span>{task.title}</span>
                  <small>{task.status}</small>
                </button>
              </li>
            ))}
          </ul>
          {tasks.length === 0 && <p className="empty-state">작업 룸이 없습니다.</p>}
        </section>

        <section className="side-group">
          <div className="side-title">저장소</div>
          <ul className="repo-compact-list">
            {repositories.map((repository) => (
              <li key={repository.id}>
                <code>{repository.repository_name}</code>
                <small>{repository.is_dirty ? "dirty" : "clean"} · {repository.current_branch ?? "detached"}</small>
              </li>
            ))}
          </ul>
          {repositories.length === 0 && <p className="empty-state">등록된 저장소가 없습니다.</p>}
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
            <p>
              {selectedProject?.name ?? "프로젝트 미선택"}
              {selectedConversation ? ` · ${selectedConversation.status}` : ""}
            </p>
          </div>
          <div className="chat-actions">
            <select
              value={selectedAgentRunId || ""}
              onChange={(event) => setSelectedAgentRunId(event.target.value || null)}
            >
              <option value="">실행 선택</option>
              {agentRuns.map((run) => (
                <option key={run.id} value={run.id}>
                  {shortId(run.id)} · {run.status} · {run.purpose}
                </option>
              ))}
            </select>
          </div>
        </header>

        <section className="chat-feed">
          {isLoadingConversations ? (
            <p className="empty-state">대화를 불러오는 중...</p>
          ) : feedItems.length > 0 ? (
            feedItems.map((feedItem) => {
              if (feedItem.kind === "message") {
                const message = feedItem.item;
                return (
                  <article
                    key={`message-${message.id}`}
                    className={message.role === "user" ? "chat-bubble user" : "chat-bubble assistant"}
                  >
                    <div className="bubble-label">{message.role}</div>
                    <pre>{message.content}</pre>
                  </article>
                );
              }

              if (feedItem.kind === "step") {
                const step = feedItem.item;
                return (
                  <article key={`step-${step.id}`} className="event-card step">
                    <strong>{step.step_type}</strong>
                    <span className={statusClass(step.status)}>{step.status}</span>
                    <p>{step.summary ?? "No summary"}</p>
                  </article>
                );
              }

              const tool = feedItem.item;
              return (
                <article key={`tool-${tool.id}`} className="event-card tool">
                  <strong>{tool.tool_name}</strong>
                  <span className={statusClass(tool.status)}>{tool.status}</span>
                  <pre>{JSON.stringify(tool.arguments_json ?? {}, null, 2)}</pre>
                </article>
              );
            })
          ) : (
            <div className="chat-empty">
              <h2>작업을 시작하세요</h2>
              <p>왼쪽에서 프로젝트와 채팅을 고르면 Owner 대화와 실행 기록이 여기에 표시됩니다.</p>
            </div>
          )}
        </section>

        <footer className="composer">
          <button type="button" className="icon-button" disabled>＋</button>
          <input
            type="text"
            value={draftMessage}
            onChange={(event) => setDraftMessage(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") void handleSendMessage();
            }}
            placeholder="후속 변경 사항을 부탁하세요"
            disabled={isSendingMessage || !selectedConversation}
          />
          <button
            type="button"
            onClick={handleSendMessage}
            disabled={!draftMessage.trim() || isSendingMessage || !selectedConversation}
          >
            {isSendingMessage ? "전송 중" : "보내기"}
          </button>
        </footer>
        {sendError && <p className="error">전송 실패: {sendError}</p>}
      </main>

      <aside className="codex-review">
        <header className="review-topbar">
          <button
            type="button"
            className={activeInspectorTab === "review" ? "tab-button active" : "tab-button"}
            onClick={() => setActiveInspectorTab("review")}
          >
            검토
          </button>
          <button
            type="button"
            className={activeInspectorTab === "changes" ? "tab-button active" : "tab-button"}
            onClick={() => setActiveInspectorTab("changes")}
          >
            변경
          </button>
          <button
            type="button"
            className={activeInspectorTab === "status" ? "tab-button active" : "tab-button"}
            onClick={() => setActiveInspectorTab("status")}
          >
            상태
          </button>
        </header>

        {activeInspectorTab === "review" && (
          <section className="review-panel">
            <h3>스테이징되지 않음</h3>
            {approvals.length > 0 ? (
              approvals.map((approval) => (
                <article key={approval.id} className="review-card">
                  <strong>{approval.title}</strong>
                  <p>{approval.action_type}</p>
                  <span className={statusClass(approval.status)}>{approval.status}</span>
                  <span className="status-pill">{approval.risk_level}</span>
                </article>
              ))
            ) : (
              <div className="empty-review">
                <h2>스테이징되지 않은 변경 사항 없음</h2>
                <p>코드 변경 사항이 여기 나타납니다.</p>
              </div>
            )}
          </section>
        )}

        {activeInspectorTab === "changes" && (
          <section className="review-panel">
            <h3>Diff / Artifacts</h3>
            {diff ? (
              <pre className="diff-view">{diff.diff}</pre>
            ) : (
              <p className="empty-state">표시할 diff가 없습니다.</p>
            )}
            {artifacts.length > 0 && (
              <ul className="artifact-list">
                {artifacts.map((artifact) => (
                  <li key={artifact.id}>
                    <strong>{artifact.kind}</strong>
                    <small>{artifact.size_bytes} bytes</small>
                    <code>{artifact.storage_path}</code>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        {activeInspectorTab === "status" && (
          <section className="review-panel">
            <h3>Task / Worker</h3>
            {selectedTask ? (
              <div className="status-stack">
                <article className="status-card">
                  <span>Task</span>
                  <strong>{selectedTask.title}</strong>
                  <span className={statusClass(selectedTask.status)}>{selectedTask.status}</span>
                  <p>{selectedTask.instructions}</p>
                </article>

                {selectedAttempt ? (
                  <article className="status-card">
                    <span>Attempt #{selectedAttempt.attempt_number}</span>
                    <strong>{shortId(selectedAttempt.id)}</strong>
                    <span className={statusClass(selectedAttempt.status)}>{selectedAttempt.status}</span>
                    {selectedAttempt.result_summary && <p>{selectedAttempt.result_summary}</p>}
                  </article>
                ) : (
                  <p className="empty-state">선택된 Attempt가 없습니다.</p>
                )}

                {latestWorkerRun && (
                  <article className="status-card">
                    <span>WorkerRun</span>
                    <strong>{shortId(latestWorkerRun.id)} · {latestWorkerRun.adapter_kind}</strong>
                    <span className={statusClass(latestWorkerRun.status)}>{latestWorkerRun.status}</span>
                    {latestWorkerRun.summary && <p>{latestWorkerRun.summary}</p>}
                    {latestWorkerRun.error_message && <p className="error">{latestWorkerRun.error_message}</p>}
                  </article>
                )}

                {worktree && (
                  <article className="status-card">
                    <span>Worktree</span>
                    <strong>{worktree.status}</strong>
                    <code>{worktree.branch_name}</code>
                    <small>{worktree.worktree_path}</small>
                  </article>
                )}
              </div>
            ) : (
              <p className="empty-state">선택된 작업이 없습니다.</p>
            )}

            <div className="grant-card">
              <h3>권한</h3>
              <p>{settings?.active_grant_placeholder || "[Grant 정보 없음]"}</p>
              <small>Updated {formatDate(selectedConversation?.updated_at)}</small>
            </div>
          </section>
        )}
      </aside>
    </div>
  );
}

