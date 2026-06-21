import { type FormEvent, useEffect, useState } from "react";
import type { AuthState } from "@aidp/shared-contracts";

import { getMe, logout, pair } from "./api/client";

const defaultDeviceName = `Web UI on ${navigator.userAgent.includes("Windows") ? "Windows" : "this device"}`;

export function App() {
  const [auth, setAuth] = useState<AuthState | null>(null);
  const [loading, setLoading] = useState(true);
  const [code, setCode] = useState("");
  const [deviceName, setDeviceName] = useState(defaultDeviceName);
  const [error, setError] = useState("");

  useEffect(() => {
    getMe()
      .then(setAuth)
      .catch(() => setAuth(null))
      .finally(() => setLoading(false));
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
      {loading ? (
        <p className="status">Checking Local Runtime session…</p>
      ) : auth ? (
        <section className="panel">
          <p className="status connected">Connected to Local Runtime</p>
          <dl>
            <div><dt>User</dt><dd>{auth.user.display_name}</dd></div>
            <div><dt>Device</dt><dd>{auth.device.display_name}</dd></div>
            <div><dt>Session</dt><dd>{auth.session.id}</dd></div>
          </dl>
          <button type="button" onClick={submitLogout}>Log out</button>
        </section>
      ) : (
        <form className="panel" onSubmit={submitPairing}>
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
