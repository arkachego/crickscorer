import type { ChaseSummary } from "@/lib/api/types";

export function ChaseSummaryPanel({
  chase,
  className,
}: {
  chase: ChaseSummary;
  className?: string;
}) {
  return (
    <div
      className={
        className ??
        "min-w-[11rem] rounded-md border border-[var(--color-line)] bg-[var(--color-cream)] px-3 py-2.5"
      }
      role="status"
      aria-label={
        chase.targetAchieved
          ? `Target ${chase.target} achieved`
          : `Target ${chase.target}, need ${chase.runsNeeded} runs from ${chase.ballsRemaining} balls`
      }
    >
      <p className="text-xs uppercase tracking-wide text-[var(--color-muted)]">
        Target
      </p>
      <p className="mt-0.5 text-2xl font-semibold tabular-nums text-[var(--color-pitch-deep)]">
        {chase.target}
      </p>
      {chase.targetAchieved ? (
        <p className="mt-2 text-sm font-medium text-[var(--color-success)]">
          Target achieved
        </p>
      ) : (
        <>
          <p className="mt-2 text-sm font-medium text-[var(--color-ink)]">
            Need{" "}
            <span className="tabular-nums font-semibold">{chase.runsNeeded}</span>{" "}
            from{" "}
            <span className="tabular-nums font-semibold">
              {chase.ballsRemaining}
            </span>{" "}
            balls
          </p>
          <p className="mt-1 text-sm text-[var(--color-muted)]">
            RRR{" "}
            <span className="tabular-nums font-semibold text-[var(--color-ink)]">
              {chase.requiredRunRate == null
                ? "—"
                : chase.requiredRunRate.toFixed(2)}
            </span>
          </p>
        </>
      )}
    </div>
  );
}
