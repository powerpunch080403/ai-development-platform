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
  WorkItemDto, TaskDto, TaskAttemptDto, WorkerDto,
  GitWorktreeDto,ArtifactRefDto,
  AttemptReviewDto,
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
  listWorkItems, createWorkItem, listTasks, createTask, listAttempts, createAttempt,
  listWorkers, registerWorker, heartbeatWorker, revokeWorker, claimAttempt, releaseAttempt,
  createWorktree,getWorktreeStatus,getWorktreeDiff,commitWorktree,listArtifacts,readArtifact,
  listMergeReady,getReview,approveReview,rejectReview,prepareSquash,performSquash,
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

function WorkPanel({ projectId, repositories }: { projectId: string; repositories: ProjectRepositoryDto[] }) {
  const [items,setItems]=useState<WorkItemDto[]>([]); const [tasks,setTasks]=useState<TaskDto[]>([]);
  const [attempts,setAttempts]=useState<TaskAttemptDto[]>([]); const [workers,setWorkers]=useState<WorkerDto[]>([]);
  const [selectedTask,setSelectedTask]=useState(""); const [selectedWorker,setSelectedWorker]=useState("");
  const [workTitle,setWorkTitle]=useState(""); const [taskTitle,setTaskTitle]=useState(""); const [instructions,setInstructions]=useState("");
  const [workItemId,setWorkItemId]=useState(""); const [repositoryId,setRepositoryId]=useState(""); const [workerName,setWorkerName]=useState(""); const [error,setError]=useState("");
  const [worktrees,setWorktrees]=useState<Record<string,GitWorktreeDto>>({});const [diff,setDiff]=useState("");const [artifacts,setArtifacts]=useState<ArtifactRefDto[]>([]);const [artifactText,setArtifactText]=useState("");
  useEffect(()=>{if(!projectId){setItems([]);setTasks([]);return} listWorkItems(projectId).then(setItems);listTasks(projectId).then(v=>{setTasks(v);setSelectedTask(v[0]?.id??"")});listWorkers().then(v=>{setWorkers(v);setSelectedWorker(v[0]?.id??"")})},[projectId]);
  useEffect(()=>{if(selectedTask)listAttempts(selectedTask).then(setAttempts);else setAttempts([])},[selectedTask]);
  async function addWork(e:FormEvent){e.preventDefault();try{const v=await createWorkItem(projectId,{title:workTitle,work_item_type:"feature"});setItems(x=>[...x,v]);setWorkTitle("")}catch(x){setError(x instanceof Error?x.message:"Work item failed")}}
  async function addTask(e:FormEvent){e.preventDefault();try{const v=await createTask(projectId,{title:taskTitle,instructions,repository_id:repositoryId||undefined,work_item_id:workItemId||undefined,risk_level:"R1",requested_worker_kind:"manual"});setTasks(x=>[v,...x]);setSelectedTask(v.id);setTaskTitle("");setInstructions("")}catch(x){setError(x instanceof Error?x.message:"Task failed")}}
  async function addWorker(e:FormEvent){e.preventDefault();const v=await registerWorker({display_name:workerName,worker_kind:"manual",capabilities:{manual:true}});setWorkers(x=>[...x,v]);setSelectedWorker(v.id);setWorkerName("")}
  async function addAttempt(){if(!selectedTask)return;const v=await createAttempt(selectedTask);setAttempts(x=>[...x,v])}
  async function workerAction(kind:"heartbeat"|"revoke"){if(!selectedWorker)return;const v=kind==="heartbeat"?await heartbeatWorker(selectedWorker):await revokeWorker(selectedWorker);setWorkers(x=>x.map(w=>w.id===v.id?v:w))}
  async function lease(a:TaskAttemptDto,release=false){if(!selectedWorker)return;try{const v=release?await releaseAttempt(selectedWorker,a.id):await claimAttempt(selectedWorker,a.id);setAttempts(x=>x.map(i=>i.id===v.id?v:i));setWorkers(await listWorkers())}catch(x){setError(x instanceof Error?x.message:"Lease operation failed")}}
  async function makeWorktree(a:TaskAttemptDto){try{const v=await createWorktree(a.id);setWorktrees(x=>({...x,[a.id]:v}))}catch(x){setError(x instanceof Error?x.message:"Worktree failed")}}
  async function wtAction(a:TaskAttemptDto,kind:"status"|"diff"|"commit"){const w=worktrees[a.id];if(!w)return;try{if(kind==="status"){const s=await getWorktreeStatus(w.id);setWorktrees(x=>({...x,[a.id]:{...w,status:s.status}}))}else if(kind==="diff"){setDiff((await getWorktreeDiff(w.id)).diff)}else{const v=await commitWorktree(w.id,"chore: apply manual worker result");setWorktrees(x=>({...x,[a.id]:v}));setArtifacts(await listArtifacts(a.id))}}catch(x){setError(x instanceof Error?x.message:"Worktree action failed")}}
  async function showArtifact(id:string){setArtifactText((await readArtifact(id)).text)}
  if(!projectId)return null;
  return <section className="panel"><h2>Work / Tasks / Workers</h2>
    <div className="records-grid"><div><form className="nested-form" onSubmit={addWork}><label>Work item title<input value={workTitle} onChange={e=>setWorkTitle(e.target.value)} required/></label><button>Create work item</button></form>{items.map(i=><p key={i.id}><span className="badge">{i.status}</span> {i.title}</p>)}</div>
    <div><form className="nested-form" onSubmit={addWorker}><label>Worker name<input value={workerName} onChange={e=>setWorkerName(e.target.value)} required/></label><button>Register manual worker</button></form><select value={selectedWorker} onChange={e=>setSelectedWorker(e.target.value)}>{workers.map(w=><option key={w.id} value={w.id}>{w.display_name} · {w.status}</option>)}</select><div className="button-row"><button type="button" className="secondary" onClick={()=>workerAction("heartbeat")}>Heartbeat</button><button type="button" className="secondary" onClick={()=>workerAction("revoke")}>Revoke</button></div></div></div>
    <form className="nested-form" onSubmit={addTask}><label>Task title<input value={taskTitle} onChange={e=>setTaskTitle(e.target.value)} required/></label><label>Instructions<textarea value={instructions} onChange={e=>setInstructions(e.target.value)} required/></label><label>Repository<select value={repositoryId} onChange={e=>setRepositoryId(e.target.value)}><option value="">None</option>{repositories.map(r=><option key={r.id} value={r.id}>{r.repository_name}</option>)}</select></label><label>Work item<select value={workItemId} onChange={e=>setWorkItemId(e.target.value)}><option value="">None</option>{items.map(i=><option key={i.id} value={i.id}>{i.title}</option>)}</select></label><button>Create draft task</button></form>
    {tasks.length>0&&<><label>Selected task<select value={selectedTask} onChange={e=>setSelectedTask(e.target.value)}>{tasks.map(t=><option key={t.id} value={t.id}>{t.title} · {t.status}</option>)}</select></label><button type="button" onClick={addAttempt}>Create attempt</button>{attempts.map(a=>{const w=worktrees[a.id];return <article className="repository-card" key={a.id}><div>Attempt #{a.attempt_number} · <span className="badge">{a.status}</span></div><div>Lease: {a.lease_expires_at??"none"}</div><div className="button-row"><button type="button" onClick={()=>lease(a)}>Claim</button><button type="button" className="secondary" onClick={()=>lease(a,true)}>Release</button>{a.claimed_by_worker_id&&!w&&<button type="button" onClick={()=>makeWorktree(a)}>Create Worktree</button>}</div>{w&&<><code>{w.worktree_path}</code><div>Branch: {w.branch_name}</div><div>Base: {w.base_commit_sha?.slice(0,8)} · Result: {w.result_commit_sha?.slice(0,8)??"none"}</div><div className="button-row"><button type="button" onClick={()=>wtAction(a,"status")}>Refresh status</button><button type="button" onClick={()=>wtAction(a,"diff")}>View diff</button><button type="button" onClick={()=>wtAction(a,"commit")}>Commit result</button></div></>}</article>})}</>}
    {diff&&<pre className="diff-view">{diff}</pre>}{artifacts.map(v=><button key={v.id} type="button" className="secondary" onClick={()=>showArtifact(v.id)}>{v.kind}</button>)}{artifactText&&<pre className="diff-view">{artifactText}</pre>}
    {error&&<p className="error">{error}</p>}
  </section>
}

function ReviewPanel(){const[ready,setReady]=useState<AttemptReviewDto[]>([]);const[selected,setSelected]=useState<AttemptReviewDto|null>(null);const[summary,setSummary]=useState("");const[message,setMessage]=useState("");const[notice,setNotice]=useState("");const refresh=()=>listMergeReady().then(setReady).catch((e:Error)=>setNotice(e.message));useEffect(()=>{void refresh()},[]);async function choose(id:string){setSelected(await getReview(id))}async function action(kind:"approve"|"reject"|"prepare"|"merge"){if(!selected)return;try{if(kind==="approve")setSelected(await approveReview(selected.task_attempt_id,summary));else if(kind==="reject")setSelected(await rejectReview(selected.task_attempt_id,summary));else if(kind==="prepare"){const p=await prepareSquash(selected.task_attempt_id);setNotice(`Merge ready: ${p.merge_possible}`)}else setSelected(await performSquash(selected.task_attempt_id,message));void refresh()}catch(e){setNotice(e instanceof Error?e.message:"Review action failed")}}return <section className="panel"><h2>Owner Review / Squash Merge</h2><button type="button" className="secondary" onClick={refresh}>Refresh review ready</button><div>{ready.map(v=><button type="button" className="secondary" key={v.task_attempt_id} onClick={()=>choose(v.task_attempt_id)}>{v.task_title} · {v.repository_name}</button>)}</div>{selected&&<><dl><div><dt>Branches</dt><dd>{selected.base_branch} ← {selected.result_branch}</dd></div><div><dt>Commits</dt><dd>{selected.base_commit_sha.slice(0,8)} → {selected.result_commit_sha.slice(0,8)}</dd></div><div><dt>Checks</dt><dd>clean {String(selected.source_clean)} · base matches {String(selected.base_head_matches)} · approved {selected.review_status}</dd></div><div><dt>Merged</dt><dd>{selected.merge_commit_sha?.slice(0,8)??"not merged"}</dd></div></dl><pre className="diff-view">{selected.diff}</pre><label>Review summary<input value={summary} onChange={e=>setSummary(e.target.value)}/></label><label>Squash commit message<input value={message} onChange={e=>setMessage(e.target.value)}/></label><div className="button-row"><button type="button" onClick={()=>action("approve")}>Approve</button><button type="button" className="secondary" onClick={()=>action("reject")}>Reject</button><button type="button" onClick={()=>action("prepare")}>Prepare merge</button><button type="button" onClick={()=>action("merge")}>Squash merge</button></div></>}{notice&&<p className="status">{notice}</p>}</section>}

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
      <WorkPanel projectId={selectedProjectId} repositories={repositories} />
      <ReviewPanel />
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
