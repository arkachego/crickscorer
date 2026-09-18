import { Link, useParams } from "react-router-dom";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { LiveStatusBadge } from "@/components/LiveStatusBadge";
import { LoadingBlock } from "@/components/LoadingBlock";
import { StatusChip } from "@/components/StatusChip";
import {
  useCompleteInnings,
  useMatch,
  useStartMatch,
  useStartNextInnings,
} from "@/hooks/use-match-lifecycle";
import { useMatchLiveSocket } from "@/hooks/use-match-live-socket";
import { ApiError, type Innings, type Match } from "@/lib/api/types";

function formatLabel(format: string): string {
  if (format === "ONE_DAY") return "One Day";
  if (format === "CUSTOM") return "Custom";
  return format;
}

function statusLabel(status: string): string {
  return status.replaceAll("_", " ");
}

function activeInnings(match: Match): Innings | undefined {
  return (match.innings ?? []).find((item) => item.status === "IN_PROGRESS");
}

export function MatchDetailPage() {
  const { matchId } = useParams<{ matchId: string }>();
  const matchQuery = useMatch(matchId);
  const live = useMatchLiveSocket(matchId);
  const startMatch = useStartMatch(matchId);
  const startNext = useStartNextInnings(matchId);
  const complete = useCompleteInnings(matchId);

  const pending =
    startMatch.isPending || startNext.isPending || complete.isPending;

  async function runAction(action: () => Promise<unknown>) {
    try {
      await action();
    } catch {
      // Error surfaced via mutation.error
    }
  }

  const mutationError =
    startMatch.error ?? startNext.error ?? complete.error ?? null;

  if (matchQuery.isLoading) {
    return <LoadingBlock label="Loading match…" lines={4} />;
  }

  if (matchQuery.isError) {
    const notFound =
      matchQuery.error instanceof ApiError && matchQuery.error.status === 404;
    return (
      <div className="space-y-4">
        <Alert tone="error" title={notFound ? "Match not found" : "Unable to load match"}>
          <p>
            {matchQuery.error instanceof ApiError
              ? matchQuery.error.message
              : "Please try again."}
          </p>
        </Alert>
      </div>
    );
  }

  const match = matchQuery.data;
  if (!match) return null;

  const active = activeInnings(match);
  const innings = [...(match.innings ?? [])].sort(
    (a, b) => a.innings_number - b.innings_number,
  );

  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-xl font-semibold tracking-tight text-[var(--color-pitch-deep)] sm:text-2xl">
            {match.team_1.name} vs {match.team_2.name}
          </h2>
          <p className="mt-1 text-sm text-[var(--color-muted)]">
            {formatLabel(match.format)} · {match.overs} overs · Batting first:{" "}
            {match.batting_first_team.name}
          </p>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <StatusChip
            label={statusLabel(match.status)}
            tone={
              match.status === "IN_PROGRESS"
                ? "live"
                : match.status === "INNINGS_BREAK"
                  ? "warn"
                  : match.status === "COMPLETED"
                    ? "success"
                    : "neutral"
            }
          />
          {match.status === "IN_PROGRESS" ? (
            <LiveStatusBadge status={live.status} />
          ) : null}
        </div>
      </div>

      {match.status === "IN_PROGRESS" && live.lastError ? (
        <Alert tone="error" title="Live connection">
          <p>{live.lastError}</p>
        </Alert>
      ) : null}

      <div className="rounded-xl border border-[var(--color-line)] bg-white/95 p-5 shadow-sm sm:p-7">
        <div className="space-y-3">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-muted)]">
            Innings
          </h3>
          {innings.length === 0 ? (
            <p className="text-sm text-[var(--color-muted)]">No innings yet.</p>
          ) : (
            <ul className="space-y-3">
              {innings.map((item) => (
                <li
                  key={item.id}
                  className="rounded-md border border-[var(--color-line)] bg-[var(--color-cream)] px-3 py-3 text-sm"
                >
                  <p className="font-semibold text-[var(--color-pitch-deep)]">
                    Innings {item.innings_number}
                  </p>
                  <p className="mt-1 text-[var(--color-ink)]">
                    {item.batting_team.name} batting · {item.bowling_team.name}{" "}
                    bowling
                  </p>
                  <p className="mt-1 text-[var(--color-muted)]">
                    Status: {statusLabel(item.status)}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="mt-6 space-y-3">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-muted)]">
            Scoring
          </h3>
          {match.status === "IN_PROGRESS" ||
          match.status === "INNINGS_BREAK" ||
          match.status === "COMPLETED" ? (
            <Link
              to={`/matches/${match.id}/scoring`}
              className="inline-flex h-11 items-center justify-center rounded-md bg-[var(--color-accent)] px-4 text-sm font-semibold text-white hover:bg-[var(--color-accent-hover)]"
            >
              Open Scoring
            </Link>
          ) : (
            <p className="text-sm text-[var(--color-muted)]">
              Start the match to open the scoring workspace.
            </p>
          )}
        </div>

        <div className="mt-6 space-y-3">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-muted)]">
            Action
          </h3>

          {match.status === "CREATED" ? (
            <Button
              type="button"
              disabled={pending}
              onClick={() => void runAction(() => startMatch.mutateAsync(match.id))}
            >
              {startMatch.isPending ? "Starting match…" : "Start Match"}
            </Button>
          ) : null}

          {match.status === "IN_PROGRESS" && active ? (
            <Button
              type="button"
              disabled={pending}
              onClick={() =>
                void runAction(() => complete.mutateAsync(active.id))
              }
            >
              {complete.isPending ? "Completing innings…" : "Complete Innings"}
            </Button>
          ) : null}

          {match.status === "INNINGS_BREAK" ? (
            <Button
              type="button"
              disabled={pending}
              onClick={() =>
                void runAction(() => startNext.mutateAsync(match.id))
              }
            >
              {startNext.isPending
                ? "Starting next innings…"
                : "Start Next Innings"}
            </Button>
          ) : null}

          {match.status === "COMPLETED" ? (
            <p className="text-sm text-[var(--color-muted)]">
              Match completed. No further lifecycle actions.
            </p>
          ) : null}
        </div>

        {mutationError ? (
          <Alert
            className="mt-4"
            tone="error"
            title="Lifecycle action failed"
          >
            {mutationError instanceof ApiError
              ? mutationError.message
              : "Unable to update the match. Please try again."}
          </Alert>
        ) : null}
      </div>
    </section>
  );
}
