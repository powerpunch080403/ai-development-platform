import { useEffect, useState } from "react";
import {
  ProjectDto,
  ProjectRepositoryDto,
  ConversationDto,
  TaskDto,
  TaskAttemptDto,
  WorkerRunDto,
  GitWorktreeDto,
  SettingsSummaryDto,
  WorktreeDiffDto,
  ApprovalRequestDto,
  ArtifactRefDto,
} from "@aidp/shared-contracts";
import {
  listProjects,
  listRepositories,
  listConversations,
  getSettingsSummary,
  listTasks,
  listAttempts,
  listWorkerRuns,
  getWorktree,
  getWorktreeDiff,
  listArtifacts,
  listApprovalRequests,
} from "../../api/client";

export function PersonalModeDashboard() {
  const [projects, setProjects] = useState<ProjectDto[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [repositories, setRepositories] = useState<ProjectRepositoryDto[]>([]);
  const [conversations, setConversations] = useState<ConversationDto[]>([]);
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

  const [activeTab, setActiveTab] = useState<"diff" | "artifacts" | "logs">("diff");

  // Initial fetch
  useEffect(() => {
    getSettingsSummary().then(setSettings).catch(console.error);
    listProjects().then((ps) => {
      setProjects(ps);
      if (ps.length > 0) setSelectedProjectId(ps[0].id);
    }).catch(console.error);
    listConversations().then(setConversations).catch(console.error);
    listApprovalRequests().then(setApprovals).catch(console.error);
  }, []);

  // When project changes
  useEffect(() => {
    if (selectedProjectId) {
      listRepositories(selectedProjectId).then(setRepositories).catch(console.error);
      listTasks(selectedProjectId).then(ts => {
        setTasks(ts);
        if (ts.length > 0) {
          setSelectedTaskId(ts[0].id);
        } else {
          setSelectedTaskId(null);
        }
      }).catch(console.error);
    } else {
      setRepositories([]);
      setTasks([]);
      setSelectedTaskId(null);
    }
  }, [selectedProjectId]);

  // When task changes
  useEffect(() => {
    if (selectedTaskId) {
      listAttempts(selectedTaskId).then(ats => {
        setAttempts(ats);
        if (ats.length > 0) {
          setSelectedAttemptId(ats[ats.length - 1].id); // default to latest
        } else {
          setSelectedAttemptId(null);
        }
      }).catch(console.error);
    } else {
      setAttempts([]);
      setSelectedAttemptId(null);
    }
  }, [selectedTaskId]);

  // When attempt changes
  useEffect(() => {
    if (selectedAttemptId) {
      listWorkerRuns(selectedAttemptId).then(setWorkerRuns).catch(console.error);
      listArtifacts(selectedAttemptId).then(setArtifacts).catch(console.error);
      getWorktree(selectedAttemptId).then(wt => {
        setWorktree(wt);
        if (wt) {
          getWorktreeDiff(wt.id).then(setDiff).catch(console.error);
        } else {
          setDiff(null);
        }
      }).catch(() => {
        setWorktree(null);
        setDiff(null);
      });
    } else {
      setWorkerRuns([]);
      setArtifacts([]);
      setWorktree(null);
      setDiff(null);
    }
  }, [selectedAttemptId]);


  const selectedTask = tasks.find(t => t.id === selectedTaskId);
  const selectedAttempt = attempts.find(a => a.id === selectedAttemptId);

  return (
    <div className="dashboard-layout">
      {/* LEFT SIDEBAR */}
      <aside className="dashboard-sidebar">
        <div className="sidebar-section">
          <h3>Project & Repository</h3>
          <select
            value={selectedProjectId || ""}
            onChange={(e) => setSelectedProjectId(e.target.value)}
          >
            <option value="">Select a project...</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
          {repositories.length > 0 && (
            <div className="repo-list">
              <h4>Repositories</h4>
              <ul>
                {repositories.map((r) => (
                  <li key={r.id}>
                    <code>{r.repository_path}</code>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {projects.length === 0 && <p className="empty-state">No projects found.</p>}
        </div>

        <div className="sidebar-section">
          <h3>Work Items / Tasks</h3>
          {tasks.length > 0 ? (
            <ul className="task-list">
              {tasks.map(t => (
                <li
                  key={t.id}
                  className={t.id === selectedTaskId ? "active" : ""}
                  onClick={() => setSelectedTaskId(t.id)}
                  style={{ cursor: "pointer", fontWeight: t.id === selectedTaskId ? "bold" : "normal" }}
                >
                  {t.title} <span className="badge">[{t.status}]</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="empty-state">No tasks found for this project.</p>
          )}
        </div>

        <div className="sidebar-section">
          <h3>Settings Summary</h3>
          {settings ? (
            <ul className="settings-list">
              <li><strong>Approval Mode:</strong> {settings.approval_mode}</li>
              <li><strong>Danger Local Config:</strong> {String(settings.allow_danger_local_config)}</li>
              <li><strong>Adapter:</strong> {settings.adapter_summary}</li>
            </ul>
          ) : (
            <p>Loading settings...</p>
          )}
        </div>
      </aside>

      {/* MAIN PANEL */}
      <main className="dashboard-main">
        <div className="main-section">
          <h3>Owner Conversation</h3>
          <div className="conversation-shell placeholder">
            <p>[Placeholder: Owner Conversation Input & Messages]</p>
            {conversations.length > 0 ? (
              conversations.slice(0, 1).map((c) => (
                <div key={c.id}>Active Conversation: {c.title}</div>
              ))
            ) : (
              <p>No conversations found.</p>
            )}
          </div>
        </div>

        <div className="main-section">
          <h3>Task Detail</h3>
          <div className="task-detail-shell">
            {selectedTask ? (
              <div>
                <h4>{selectedTask.title}</h4>
                <p><strong>Status:</strong> {selectedTask.status} | <strong>Risk Level:</strong> {selectedTask.risk_level}</p>
                <p><strong>Instructions:</strong></p>
                <pre>{selectedTask.instructions}</pre>
                <p><strong>Write Scope:</strong> {JSON.stringify(selectedTask.write_scope)}</p>
              </div>
            ) : (
              <p className="empty-state">No task selected.</p>
            )}
          </div>
        </div>

        <div className="main-section tabs-section">
          <div className="tabs-header">
            <button className={activeTab === "diff" ? "active" : ""} onClick={() => setActiveTab("diff")}>Diff</button>
            <button className={activeTab === "artifacts" ? "active" : ""} onClick={() => setActiveTab("artifacts")}>Artifacts</button>
            <button className={activeTab === "logs" ? "active" : ""} onClick={() => setActiveTab("logs")}>Logs</button>
          </div>
          <div className="tabs-content">
            {activeTab === "diff" && (
              diff ? (
                <pre className="diff-view">{diff.diff}</pre>
              ) : (
                <p className="empty-state">No diff available.</p>
              )
            )}
            {activeTab === "artifacts" && (
              artifacts.length > 0 ? (
                <ul>
                  {artifacts.map(a => (
                    <li key={a.id}>{a.kind} - {a.storage_path} ({a.size_bytes} bytes)</li>
                  ))}
                </ul>
              ) : (
                <p className="empty-state">No artifacts available.</p>
              )
            )}
            {activeTab === "logs" && (
              workerRuns.length > 0 ? (
                <div>
                  <p>Worker runs: {workerRuns.length}</p>
                  {workerRuns.map(run => (
                    <div key={run.id} style={{marginBottom: "1em", borderBottom: "1px solid #ccc"}}>
                      <strong>{run.adapter_kind}</strong> [{run.status}]<br/>
                      {run.error_message && <span style={{color: "red"}}>{run.error_message}</span>}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="empty-state">No worker runs to display logs for.</p>
              )
            )}
          </div>
        </div>
      </main>

      {/* RIGHT PANEL */}
      <aside className="dashboard-right">
        <div className="right-section">
          <h3>Worker & Worktree Status</h3>
          <div className="status-shell">
            {selectedAttempt ? (
              <div>
                <p><strong>Attempt:</strong> #{selectedAttempt.attempt_number} [{selectedAttempt.status}]</p>
                {workerRuns.length > 0 && (
                  <p><strong>Latest Run:</strong> {workerRuns[workerRuns.length - 1].status} ({workerRuns[workerRuns.length - 1].adapter_kind})</p>
                )}
                {worktree ? (
                  <div>
                    <p><strong>Worktree:</strong> {worktree.status}</p>
                    <p><strong>Branch:</strong> {worktree.branch_name}</p>
                  </div>
                ) : (
                  <p>No worktree created yet.</p>
                )}
              </div>
            ) : (
              <p className="empty-state">No attempt selected.</p>
            )}
          </div>
        </div>

        <div className="right-section">
          <h3>Approval</h3>
          <div className="approval-card">
            {approvals.length > 0 ? (
              approvals.map(req => (
                <div key={req.id} style={{marginBottom: "1em", paddingBottom: "1em", borderBottom: "1px solid #ccc"}}>
                  <h4>{req.title}</h4>
                  <p><strong>Action:</strong> {req.action_type}</p>
                  <p><strong>Risk:</strong> {req.risk_level}</p>
                  <p><strong>Status:</strong> {req.status}</p>
                  <button disabled>Approve (Squash Merge)</button>
                  <button disabled>Reject</button>
                </div>
              ))
            ) : (
              <p className="empty-state">No pending approvals.</p>
            )}
          </div>
        </div>

        <div className="right-section">
          <h3>Grant Summary</h3>
          <div className="grant-summary placeholder">
            <p>{settings?.active_grant_placeholder || "[Placeholder: Loading Grant...]"}</p>
          </div>
        </div>
      </aside>
    </div>
  );
}
