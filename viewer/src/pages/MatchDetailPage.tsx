import { Link, useParams } from "react-router-dom";
import { Alert } from "@/components/ui/alert";
import { useMatch } from "@/hooks/use-matches";
import { ApiError } from "@/lib/api/types";
import { formatLabel, statusLabel } from "@/lib/utils";

export function MatchDetailPage() {
  const { matchId } = useParams<{ matchId: string }>();
  const matchQuery = useMatch(matchId);

  if (matchQuery.isLoading) {
    return (
      <p role="status" className="text-sm text-[var(--color-muted)]">
        Loading match…
      </p>
    );
  }

  if (matchQuery.isError) {
    const error = matchQuery.error;
    const isNotFound = error instanceof ApiError && error.status === 404;

    return (
      <div className="space-y-4">
        <Alert
          tone="error"
          title={isNotFound ? "Match not found" : "Unable to load match"}
        >
          <p>
            {isNotFound
              ? "This match does not exist or is no longer available."
              : "Please try again."}
          </p>
        </Alert>
      </div>
    );
  }

  const match = matchQuery.data;
  if (!match) {
    return null;
  }

  return (
    <section className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight text-[var(--color-skyline-deep)]">
          {match.team_1.name} vs {match.team_2.name}
        </h2>
        <p className="mt-1 text-sm text-[var(--color-muted)]">
          Read-only match metadata. Open the scoreboard for current scoring
          state.
        </p>
      </div>

      <div className="rounded-xl border border-[var(--color-line)] bg-white/95 p-5 shadow-sm sm:p-7">
        <dl className="grid gap-4 sm:grid-cols-2">
          <div>
            <dt className="text-xs uppercase tracking-wide text-[var(--color-muted)]">
              Format
            </dt>
            <dd className="mt-1 text-[var(--color-ink)]">
              {formatLabel(match.format)}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-[var(--color-muted)]">
              Overs
            </dt>
            <dd className="mt-1 text-[var(--color-ink)]">{match.overs}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-[var(--color-muted)]">
              Status
            </dt>
            <dd className="mt-1 text-[var(--color-ink)]">
              {statusLabel(match.status)}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-[var(--color-muted)]">
              Batting first
            </dt>
            <dd className="mt-1 text-[var(--color-ink)]">
              {match.batting_first_team.name}
            </dd>
          </div>
        </dl>

        <div className="mt-6">
          <Link
            to={`/matches/${match.id}/scoreboard`}
            className="inline-flex h-11 items-center justify-center rounded-md bg-[var(--color-accent)] px-4 text-sm font-semibold text-white hover:bg-[var(--color-accent-hover)]"
          >
            View Scoreboard
          </Link>
        </div>
      </div>
    </section>
  );
}
