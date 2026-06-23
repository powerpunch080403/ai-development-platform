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
} from "@aidp/shared-contracts";
import {
  listProjects,
  listRepositories,
  listConversations,
  getSettingsSummary,
} from "../../api/client";

export function PersonalModeDashboard() {
  const [projects, setProjects] = useState<ProjectDto[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [repositories, setRepositories] = useState<ProjectRepositoryDto[]>([]);
  const [conversations, setConversations] = useState<ConversationDto[]>([]);
  const [settings, setSettings] = useState<SettingsSummaryDto | null>(null);

  // Shell states for UI demonstration
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"diff" | "artifacts" | "logs">("diff");

  useEffect(() => {
    getSettingsSummary().then(setSettings).catch(console.error);
    listProjects().then((ps) => {
      setProjects(ps);
      if (ps.length > 0) setSelectedProjectId(ps[0].id);
    }).catch(console.error);
    listConversations().then(setConversations).catch(console.error);
  }, []);

  useEffect(() => {
    if (selectedProjectId) {
      listRepositories(selectedProjectId).then(setRepositories).catch(console.error);
    } else {
      setRepositories([]);
    }
  }, [selectedProjectId]);

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
        </div>

        <div className="sidebar-section">
          <h3>Work Items / Tasks</h3>
          <p className="placeholder">[Placeholder: Task List for Project]</p>
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
            {conversations.slice(0, 1).map((c) => (
              <div key={c.id}>Active Conversation: {c.title}</div>
            ))}
          </div>
        </div>

        <div className="main-section">
          <h3>Task Detail</h3>
          <div className="task-detail-shell placeholder">
            <p>[Placeholder: Selected Task Detail]</p>
          </div>
        </div>

        <div className="main-section tabs-section">
          <div className="tabs-header">
            <button className={activeTab === "diff" ? "active" : ""} onClick={() => setActiveTab("diff")}>Diff</button>
            <button className={activeTab === "artifacts" ? "active" : ""} onClick={() => setActiveTab("artifacts")}>Artifacts</button>
            <button className={activeTab === "logs" ? "active" : ""} onClick={() => setActiveTab("logs")}>Logs</button>
          </div>
          <div className="tabs-content placeholder">
            {activeTab === "diff" && <p>[Placeholder: Worktree Diff View]</p>}
            {activeTab === "artifacts" && <p>[Placeholder: Artifact Store List]</p>}
            {activeTab === "logs" && <p>[Placeholder: Worker Process Logs]</p>}
          </div>
        </div>
      </main>

      {/* RIGHT PANEL */}
      <aside className="dashboard-right">
        <div className="right-section">
          <h3>Worker & Worktree Status</h3>
          <div className="status-shell placeholder">
            <p>[Placeholder: Current WorkerRun]</p>
            <p>[Placeholder: Current GitWorktree]</p>
            <p>[Placeholder: Task Attempt Status]</p>
          </div>
        </div>

        <div className="right-section">
          <h3>Approval</h3>
          <div className="approval-card placeholder">
            <p>[Placeholder: Pending Approval Request]</p>
            <button disabled>Approve (Squash Merge)</button>
            <button disabled>Reject</button>
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
