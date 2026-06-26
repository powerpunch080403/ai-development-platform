import type { AgentRunDto } from "@aidp/shared-contracts";

type OwnerRunStatusBannerProps = {
  run?: AgentRunDto | null;
  isSending: boolean;
};

function isActiveStatus(status?: string | null) {
  return [
    "queued",
    "preparing_context",
    "running_model",
    "executing_tool",
    "waiting_for_approval",
    "waiting_for_user",
    "waiting_for_worker",
    "reviewing_worker_result",
    "retry_scheduled",
  ].includes(status ?? "");
}

function usageLimitMessage(message: string) {
  const match = /try again at\s+(.+?)(?:\.|\n|$)/i.exec(message);
  if (match?.[1]) {
    return `Codex \uc0ac\uc6a9\ub7c9 \ud55c\ub3c4\uc5d0 \ub3c4\ub2ec\ud588\uc2b5\ub2c8\ub2e4. ${match[1].trim()}\uc5d0 \ub2e4\uc2dc \uc2dc\ub3c4\ud560 \uc218 \uc788\uc2b5\ub2c8\ub2e4.`;
  }
  return "Codex \uc0ac\uc6a9\ub7c9 \ud55c\ub3c4\uc5d0 \ub3c4\ub2ec\ud588\uc2b5\ub2c8\ub2e4. \ub098\uc911\uc5d0 \ub2e4\uc2dc \uc2dc\ub3c4\ud560 \uc218 \uc788\uc2b5\ub2c8\ub2e4.";
}

function failureMessage(run: AgentRunDto) {
  const raw = run.error_message?.trim();
  if (!raw) return "Owner \uc2e4\ud589\uc774 \uc2e4\ud328\ud588\uc2b5\ub2c8\ub2e4.";

  if (run.error_code === "owner_provider_usage_limit" || /usage limit/i.test(raw)) {
    return usageLimitMessage(raw);
  }

  const firstLine = raw
    .split("\n")
    .map((line: string) => line.trim())
    .find(Boolean);

  return firstLine?.replace(/^ERROR:\s*/i, "") || "Owner \uc2e4\ud589\uc774 \uc2e4\ud328\ud588\uc2b5\ub2c8\ub2e4.";
}

export function OwnerRunStatusBanner({ run, isSending }: OwnerRunStatusBannerProps) {
  if (run?.status === "failed") {
    return (
      <div className="owner-run-status-banner danger" role="status">
        {failureMessage(run)}
      </div>
    );
  }

  if (isSending || isActiveStatus(run?.status)) {
    return (
      <div className="owner-run-status-banner" role="status">
        Owner\uac00 \uc785\ub825 \uc911...
      </div>
    );
  }

  return null;
}
