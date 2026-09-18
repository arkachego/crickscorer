import { cn } from "@/lib/utils";

/** Status chip: colour + text so state is not colour-only. */
export function StatusChip({
  label,
  tone = "neutral",
  className,
}: {
  label: string;
  tone?: "neutral" | "live" | "warn" | "danger" | "success";
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-semibold uppercase tracking-wide",
        tone === "neutral" &&
          "border-[var(--color-line)] bg-white text-[var(--color-muted)]",
        tone === "live" &&
          "border-[var(--color-success)]/40 bg-[var(--color-success)]/10 text-[var(--color-success)]",
        tone === "warn" &&
          "border-[var(--color-accent)]/50 bg-[var(--color-accent)]/10 text-[var(--color-accent)]",
        tone === "danger" &&
          "border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10 text-[var(--color-danger)]",
        tone === "success" &&
          "border-[var(--color-success)]/40 bg-[var(--color-success)]/10 text-[var(--color-success)]",
        className,
      )}
    >
      <span aria-hidden="true" className="text-[0.65rem]">
        {tone === "live" || tone === "success"
          ? "●"
          : tone === "warn"
            ? "▲"
            : tone === "danger"
              ? "!"
              : "○"}
      </span>
      {label}
    </span>
  );
}
