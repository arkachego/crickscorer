import type { LiveConnectionStatus } from "@/lib/api/types";

function liveStatusLabel(status: LiveConnectionStatus): string {
  switch (status) {
    case "live":
      return "Live";
    case "connecting":
      return "Connecting…";
    case "reconnecting":
      return "Reconnecting…";
    case "disconnected":
      return "Disconnected";
    case "error":
      return "Live offline";
  }
}

export function LiveStatusBadge({
  status,
}: {
  status: LiveConnectionStatus;
}) {
  const label = liveStatusLabel(status);
  return (
    <p
      role="status"
      aria-live="polite"
      aria-label={`Connection ${label}`}
      className="inline-flex min-h-11 items-center gap-1.5 rounded-md border border-[var(--color-line)] bg-white px-3 py-2 text-xs font-medium text-[var(--color-muted)]"
    >
      <span aria-hidden="true">
        {status === "live"
          ? "●"
          : status === "reconnecting" || status === "connecting"
            ? "…"
            : "○"}
      </span>
      {label}
    </p>
  );
}
