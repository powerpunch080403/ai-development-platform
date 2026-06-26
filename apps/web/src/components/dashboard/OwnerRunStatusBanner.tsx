import type { AgentRunDto } from "@aidp/shared-contracts";

type OwnerRunStatusBannerProps = {
  run?: AgentRunDto | null;
  isSending: boolean;
};

const RUNNING_MESSAGE = "Owner\uac00 \uc785\ub825 \uc911...";
const DEFAULT_FAILURE_MESSAGE = "Owner \uc2e4\ud589\uc774 \uc2e4\ud328\ud588\uc2b5\ub2c8\ub2e4.";

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

function providerLabel(run: AgentRunDto) {
  switch (run.provider_kind) {
    case "codex_cli":
      return "Codex CLI";
    case "openai_api":
      return "OpenAI API";
    case "local_ai":
      return "Local AI";
    case "fake":
      return "Fake Owner";
    default:
      return "Owner \ub7f0\ud0c0\uc784 provider";
  }
}

function firstMeaningfulLine(message?: string | null) {
  return message
    ?.split(/\r?\n/)
    .map((line) => line.trim())
    .find(Boolean)
    ?.replace(/^ERROR:\s*/i, "");
}

function retryAfterFromMessage(message?: string | null) {
  if (!message) return null;
  const match = /try again at\s+(.+?)(?:\.|\n|$)/i.exec(message);
  return match?.[1]?.trim() || null;
}

function quotaMessage(run: AgentRunDto) {
  const label = providerLabel(run);
  const retryAfter = run.retry_after?.trim() || retryAfterFromMessage(run.error_message);

  if (retryAfter) {
    return `${label} \uc0ac\uc6a9\ub7c9 \ud55c\ub3c4\uc5d0 \ub3c4\ub2ec\ud588\uc2b5\ub2c8\ub2e4. ${retryAfter} \uc774\ud6c4 \ub2e4\uc2dc \uc2dc\ub3c4\ud560 \uc218 \uc788\uc2b5\ub2c8\ub2e4.`;
  }

  return `${label} \uc0ac\uc6a9\ub7c9 \ud55c\ub3c4\uc5d0 \ub3c4\ub2ec\ud588\uc2b5\ub2c8\ub2e4. \ub098\uc911\uc5d0 \ub2e4\uc2dc \uc2dc\ub3c4\ud560 \uc218 \uc788\uc2b5\ub2c8\ub2e4.`;
}

function failureMessage(run: AgentRunDto) {
  const label = providerLabel(run);

  if (run.error_category === "quota_exceeded" || run.error_code === "owner_provider_quota_exceeded") {
    return quotaMessage(run);
  }

  if (
    run.error_category === "provider_not_connected" ||
    run.error_code === "owner_provider_not_connected"
  ) {
    return `${label}\uac00 \uc5f0\uacb0\ub418\uc5b4 \uc788\uc9c0 \uc54a\uc2b5\ub2c8\ub2e4. \uc124\uc815\uc744 \ud655\uc778\ud574\uc8fc\uc138\uc694.`;
  }

  if (
    run.error_category === "provider_not_implemented" ||
    run.error_code === "owner_provider_not_implemented"
  ) {
    return `${label}\ub294 \uc544\uc9c1 \uad6c\ud604\ub418\uc9c0 \uc54a\uc558\uc2b5\ub2c8\ub2e4.`;
  }

  if (run.error_category === "timeout" || run.error_code === "owner_provider_timeout") {
    return `${label} \uc2e4\ud589 \uc2dc\uac04\uc774 \ucd08\uacfc\ub410\uc2b5\ub2c8\ub2e4.`;
  }

  if (
    run.error_category === "provider_runtime_unavailable" ||
    run.error_code === "owner_provider_command_not_found"
  ) {
    return `${label} \ub7f0\ud0c0\uc784\uc744 \ucc3e\uc744 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4.`;
  }

  if (run.error_category === "empty_response" || run.error_code === "owner_provider_empty_response") {
    return `${label}\uac00 \uc751\ub2f5\uc744 \uc0dd\uc131\ud558\uc9c0 \uc54a\uc558\uc2b5\ub2c8\ub2e4.`;
  }

  return firstMeaningfulLine(run.error_message) || DEFAULT_FAILURE_MESSAGE;
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
        {RUNNING_MESSAGE}
      </div>
    );
  }

  return null;
}
