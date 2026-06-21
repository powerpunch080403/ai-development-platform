import type { AuthState, HealthStatus } from "@aidp/shared-contracts";

const DEFAULT_API_BASE_URL = "http://localhost:8000";
const API_BASE_URL = import.meta.env.VITE_AIDP_API_BASE_URL ?? DEFAULT_API_BASE_URL;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init?.headers },
  });

  if (!response.ok) {
    throw new Error(response.status === 401 ? "Not authenticated" : "Request failed");
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
