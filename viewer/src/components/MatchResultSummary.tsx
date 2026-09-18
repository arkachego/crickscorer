import type { Match } from "@/lib/api/types";
import { computeMatchResult } from "@/lib/utils";

export function MatchResultSummary({ match }: { match: Match }) {
  const result = computeMatchResult(match);
  if (!result) return null;

  return (
    <div
      className="overflow-hidden rounded-xl border border-[var(--color-line)] bg-white/95 shadow-sm"
      role="region"
      aria-label="Match result summary"
    >
      <div className="bg-[var(--color-skyline)] px-4 py-3 text-white sm:px-5">
        <p className="text-xs uppercase tracking-wide text-white/70">
          Match result
        </p>
        {result.outcome.kind === "win" ? (
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <img
              src={result.outcome.winner.flag_url}
              alt=""
              className="h-8 w-12 rounded-sm object-cover shadow-sm"
            />
            <div>
              <p className="text-lg font-semibold tracking-tight sm:text-xl">
                {result.outcome.winner.name}
              </p>
              <p className="text-sm text-white/85">{result.outcome.margin}</p>
            </div>
          </div>
        ) : result.outcome.kind === "tie" ? (
          <p className="mt-2 text-lg font-semibold tracking-tight sm:text-xl">
            Match tied
          </p>
        ) : (
          <p className="mt-2 text-lg font-semibold tracking-tight sm:text-xl">
            Result unavailable
          </p>
        )}
      </div>

      <ul className="divide-y divide-[var(--color-line)]">
        {result.lines.map((line) => (
          <li
            key={`${line.inningsNumber}-${line.team.id}`}
            className="flex flex-wrap items-center justify-between gap-3 px-4 py-4 sm:px-5"
          >
            <div className="flex min-w-0 items-center gap-3">
              <img
                src={line.team.flag_url}
                alt=""
                className="h-7 w-10 shrink-0 rounded-sm object-cover"
              />
              <div className="min-w-0">
                <p className="truncate font-semibold text-[var(--color-skyline-deep)]">
                  {line.team.name}
                </p>
                <p className="text-xs text-[var(--color-muted)]">
                  Innings {line.inningsNumber} · RR {line.runRate.toFixed(2)}
                </p>
              </div>
            </div>
            <div className="text-right">
              <p
                className="text-2xl font-semibold tabular-nums text-[var(--color-skyline-deep)]"
                aria-label={`${line.team.name} ${line.runs} for ${line.wickets}`}
              >
                {line.runs}/{line.wickets}
              </p>
              <p className="text-xs tabular-nums text-[var(--color-muted)]">
                {line.oversDisplay} Ov
              </p>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
