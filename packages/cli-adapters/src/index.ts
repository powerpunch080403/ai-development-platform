export type AdapterRole = "owner" | "worker";

export type AdapterRunRequest = {
  role: AdapterRole;
  prompt: string;
  workingDirectory: string;
};

export type AdapterRunResult = {
  status: "succeeded" | "failed" | "cancelled";
  stdout?: string;
  stderr?: string;
};
