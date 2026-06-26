import { type FormEvent, useEffect, useState } from "react";
import type { AuthState } from "@aidp/shared-contracts";

import { getMe, logout, pair } from "./api/client";
import { PersonalModeDashboard } from "./components/dashboard/PersonalModeDashboard";

const defaultDeviceName = `Web UI on ${navigator.userAgent.includes("Windows") ? "Windows" : "this device"}`;

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

  async function handleLogout() {
    await logout();
    setAuth(null);
  }

  return (
    <main className="app-shell">
      {loading ? (
        <p className="status">Checking Local Runtime session…</p>
      ) : auth ? (
        <>
          <button type="button" className="session-logout secondary" onClick={handleLogout}>
            로그아웃
          </button>
          <PersonalModeDashboard />
        </>
      ) : (
        <form className="panel pairing-panel" onSubmit={submitPairing}>
          <p className="status">Pair this browser with the Local Runtime.</p>
          <label>
            Pairing code
            <input value={code} onChange={(event) => setCode(event.target.value)} placeholder="1234-5678" required />
          </label>
          <label>
            Device name
            <input value={deviceName} onChange={(event) => setDeviceName(event.target.value)} required />
          </label>
          {error && <p className="error" role="alert">{error}</p>}
          <button type="submit">Pair Web UI</button>
        </form>
      )}
    </main>
  );
}
