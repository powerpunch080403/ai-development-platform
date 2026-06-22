import { type FormEvent, useEffect, useState } from "react";
import type {
  AuthState,
  ProjectDto,
  ProjectRepositoryDto,
  RepositoryRole,
  ConversationDto,
  MessageDto,
  AgentRunDto,
  ToolRegistryEntryDto,
} from "@aidp/shared-contracts";

import {
  createProject,
  getMe,
  listProjects,
  listRepositories,
  logout,
  pair,
  refreshRepositoryStatus,
  registerRepository,
  listConversations,
  createConversation,
  listMessages,
  appendMessage,
  listAgentRuns,
  createAgentRun,
  listToolRegistry,
} from "./api/client";

const defaultDeviceName = `Web UI on ${navigator.userAgent.includes("Windows") ? "Windows" : "this device"}`;

function RecordsPanel({ projects, selectedProjectId }: { projects: ProjectDto[]; selectedProjectId: string }) {
  const [conversations, setConversations] = useState<ConversationDto[]>([]);
  const [selectedConversationId, setSelectedConversationId] = useState("");
  const [messages, setMessages] = useState<MessageDto[]>([]);
  const [runs, setRuns] = useState<AgentRunDto[]>([]);
  const [tools, setTools] = useState<ToolRegistryEntryDto[]>([]);
  const [title, setTitle] = useState("");
  const [conversationProjectId, setConversationProjectId] = useState(selectedProjectId);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    listConversations().then((items) => { setConversations(items); setSelectedConversationId(items[0]?.id ?? ""); }).catch((e: Error) => setError(e.message));
    listToolRegistry().then(setTools).catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => { if (selectedProjectId) setConversationProjectId(selectedProjectId); }, [selectedProjectId]);
  useEffect(() => {
    if (!selectedConversationId) { setMessages([]); setRuns([]); return; }
    listMessages(selectedConversationId).then(setMessages).catch((e: Error) => setError(e.message));
    listAgentRuns(selectedConversationId).then(setRuns).catch((e: Error) => setError(e.message));
  }, [selectedConversationId]);

  async function submitConversation(event: FormEvent) {
    event.preventDefault(); setError("");
    try {
      const created = await createConversation({ title: title || undefined, project_id: conversationProjectId || undefined });
      setConversations((items) => [created, ...items]); setSelectedConversationId(created.id); setTitle("");
    } catch (e) { setError(e instanceof Error ? e.message : "Conversation creation failed"); }
  }

  async function submitMessage(event: FormEvent) {
    event.preventDefault(); if (!selectedConversationId) return;
    try { const created = await appendMessage(selectedConversationId, { role: "user", content: message }); setMessages((items) => [...items, created]); setMessage(""); }
    catch (e) { setError(e instanceof Error ? e.message : "Message append failed"); }
  }

  async function submitRun() {
    if (!selectedConversationId) return;
    const conversation = conversations.find((item) => item.id === selectedConversationId);
    try {
      const created = await createAgentRun({ conversation_id: selectedConversationId, project_id: conversation?.project_id ?? undefined, purpose: "owner_request", input_message_id: messages.at(-1)?.id });
      setRuns((items) => [created, ...items]);
    } catch (e) { setError(e instanceof Error ? e.message : "Agent run creation failed"); }
  }

  return <section className="records-grid">
    <section className="panel">
      <h2>Conversations</h2>
      <form className="nested-form" onSubmit={submitConversation}>
        <label>Title<input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="New Conversation" /></label>
        <label>Project<select value={conversationProjectId} onChange={(e) => setConversationProjectId(e.target.value)}><option value="">General conversation</option>{projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
        <button type="submit">Create conversation</button>
      </form>
      {conversations.length > 0 && <label>Selected conversation<select value={selectedConversationId} onChange={(e) => setSelectedConversationId(e.target.value)}>{conversations.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}</select></label>}
      {selectedConversationId && <>
        <div className="message-list">{messages.map((item) => <p key={item.id}><strong>{item.role}</strong> {item.content}</p>)}</div>
        <form className="nested-form" onSubmit={submitMessage}><label>User message<textarea value={message} onChange={(e) => setMessage(e.target.value)} required /></label><button type="submit">Append message</button></form>
        <button type="button" className="secondary" onClick={submitRun}>Create Agent Run record</button>
        <div>{runs.map((run) => <p key={run.id}><code>{run.id.slice(0, 8)}</code> · {run.status} · {run.purpose}</p>)}</div>
      </>}
    </section>
    <section className="panel"><h2>Tool Registry</h2><p className="muted">Record contracts only; no tools execute in this slice.</p>{tools.map((tool) => <div className="tool-row" key={tool.id}><code>{tool.tool_name}</code><span>{tool.enabled ? "enabled" : "disabled"} · {tool.default_risk_level}</span></div>)}</section>
    {error && <p className="error" role="alert">{error}</p>}
  </section>;
}

function Workspace({ auth, onLogout }: { auth: AuthState; onLogout: () => Promise<void> }) {
  const [projects, setProjects] = useState<ProjectDto[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [repositories, setRepositories] = useState<ProjectRepositoryDto[]>([]);
  const [projectName, setProjectName] = useState("");
  const [projectDescription, setProjectDescription] = useState("");
  const [repositoryPath, setRepositoryPath] = useState("");
  const [repositoryRole, setRepositoryRole] = useState<RepositoryRole | "">("");
  const [error, setError] = useState("");

  useEffect(() => {
    listProjects()
      .then((items) => {
        setProjects(items);
        setSelectedProjectId(items[0]?.id ?? "");
      })
      .catch((reason: Error) => setError(reason.message));
  }, []);

  useEffect(() => {
    if (!selectedProjectId) {
      setRepositories([]);
      return;
    }
    listRepositories(selectedProjectId)
      .then(setRepositories)
      .catch((reason: Error) => setError(reason.message));
  }, [selectedProjectId]);

  async function submitProject(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const created = await createProject({
        name: projectName,
        description: projectDescription || undefined,
      });
      setProjects((items) => [created, ...items]);
      setSelectedProjectId(created.id);
      setProjectName("");
      setProjectDescription("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Project creation failed");
    }
  }

  async function submitRepository(event: FormEvent) {
    event.preventDefault();
    if (!selectedProjectId) return;
    setError("");
    try {
      const created = await registerRepository(selectedProjectId, {
        repository_path: repositoryPath,
        repository_role: repositoryRole || undefined,
      });
      setRepositories((items) => [...items, created]);
      setRepositoryPath("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Repository registration failed");
    }
  }

  async function refresh(repository: ProjectRepositoryDto) {
    setError("");
    try {
      const refreshed = await refreshRepositoryStatus(repository.id);
      if (refreshed.error_code) throw new Error(refreshed.error_message ?? refreshed.error_code);
      setRepositories((items) =>
        items.map((item) =>
          item.id === repository.id
            ? {
                ...item,
                repository_path: refreshed.repository_root ?? item.repository_path,
                current_branch: refreshed.current_branch,
                default_branch: refreshed.default_branch,
                last_commit_sha: refreshed.last_commit_sha,
                is_dirty: refreshed.is_dirty ?? item.is_dirty,
                last_status_checked_at: refreshed.checked_at,
              }
            : item,
        ),
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Status refresh failed");
    }
  }

  return (
    <section className="workspace">
      <div className="session-bar">
        <span>{auth.user.display_name} · {auth.device.display_name}</span>
        <button type="button" className="secondary" onClick={onLogout}>Log out</button>
      </div>

      <form className="panel" onSubmit={submitProject}>
        <h2>Create project</h2>
        <label>Project name<input value={projectName} onChange={(e) => setProjectName(e.target.value)} required /></label>
        <label>Description<input value={projectDescription} onChange={(e) => setProjectDescription(e.target.value)} /></label>
        <button type="submit">Create project</button>
      </form>

      {projects.length > 0 && (
        <section className="panel">
          <label>
            Selected project
            <select value={selectedProjectId} onChange={(e) => setSelectedProjectId(e.target.value)}>
              {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
            </select>
          </label>
          <form className="nested-form" onSubmit={submitRepository}>
            <h2>Register Git repository</h2>
            <label>Repository path<input value={repositoryPath} onChange={(e) => setRepositoryPath(e.target.value)} required /></label>
            <label>
              Repository role
              <select value={repositoryRole} onChange={(e) => setRepositoryRole(e.target.value as RepositoryRole | "")}>
                <option value="">Automatic (first is primary)</option>
                {(["primary", "supporting", "docs", "infra", "unknown"] as const).map((role) => <option key={role} value={role}>{role}</option>)}
              </select>
            </label>
            <button type="submit">Register repository</button>
          </form>
        </section>
      )}

      {repositories.length > 0 && (
        <section className="repository-list">
          <h2>Repositories</h2>
          {repositories.map((repository) => (
            <article className="repository-card" key={repository.id}>
              <div><strong>{repository.repository_name}</strong> <span className="badge">{repository.repository_role}</span></div>
              <code>{repository.repository_path}</code>
              <dl>
                <div><dt>Current</dt><dd>{repository.current_branch ?? "detached"}</dd></div>
                <div><dt>Default</dt><dd>{repository.default_branch ?? "unknown"}</dd></div>
                <div><dt>Commit</dt><dd>{repository.last_commit_sha?.slice(0, 8) ?? "none"}</dd></div>
                <div><dt>Status</dt><dd className={repository.is_dirty ? "dirty" : "clean"}>{repository.is_dirty ? "Dirty" : "Clean"}</dd></div>
              </dl>
              <button type="button" className="secondary" onClick={() => refresh(repository)}>Refresh status</button>
            </article>
          ))}
        </section>
      )}
      <RecordsPanel projects={projects} selectedProjectId={selectedProjectId} />
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}

export function App() {
  const [auth, setAuth] = useState<AuthState | null>(null);
  const [loading, setLoading] = useState(true);
  const [code, setCode] = useState("");
  const [deviceName, setDeviceName] = useState(defaultDeviceName);
  const [error, setError] = useState("");

  useEffect(() => {
    getMe().then(setAuth).catch(() => setAuth(null)).finally(() => setLoading(false));
  }, []);

  async function submitPairing(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      setAuth(await pair(code, deviceName));
      setCode("");
    } catch {
      setError("Pairing failed. Check that the code is current and unused.");
    }
  }

  async function submitLogout() {
    await logout();
    setAuth(null);
  }

  return (
    <main className="app-shell">
      <p className="eyebrow">Personal Mode MVP</p>
      <h1>AI Development Platform</h1>
      {loading ? <p className="status">Checking Local Runtime session…</p> : auth ? (
        <Workspace auth={auth} onLogout={submitLogout} />
      ) : (
        <form className="panel" onSubmit={submitPairing}>
          <p className="status">Pair this browser with the Local Runtime.</p>
          <label>Pairing code<input value={code} onChange={(e) => setCode(e.target.value)} placeholder="1234-5678" required /></label>
          <label>Device name<input value={deviceName} onChange={(e) => setDeviceName(e.target.value)} required /></label>
          {error && <p className="error" role="alert">{error}</p>}
          <button type="submit">Pair Web UI</button>
        </form>
      )}
    </main>
  );
}
