import type { HealthStatus } from "@aidp/shared-contracts";

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";

export async function getHealth(
  baseUrl: string = DEFAULT_API_BASE_URL,
): Promise<HealthStatus> {
  const response = await fetch(`${baseUrl}/health`);

  if (!response.ok) {
    throw new Error(`Health request failed with status ${response.status}`);
  }

  return (await response.json()) as HealthStatus;
}
