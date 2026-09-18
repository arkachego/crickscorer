import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { LoadingBlock } from "@/components/LoadingBlock";
import { MatchCard } from "@/components/matches/MatchCard";
import { useMatches } from "@/hooks/use-matches";

export function MatchListPage() {
  const matchesQuery = useMatches();

  return (
    <section className="space-y-6" aria-label="Matches">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight text-[var(--color-skyline-deep)]">
          Matches
        </h2>
        <p className="mt-1 text-sm text-[var(--color-muted)]">
          Browse available matches. Open a match, then view its live scoreboard.
        </p>
      </div>

      {matchesQuery.isLoading ? (
        <LoadingBlock label="Loading matches…" lines={4} />
      ) : null}

      {matchesQuery.isError ? (
        <Alert tone="error" title="Unable to load matches">
          <div className="space-y-3">
            <p>Please try again.</p>
            <Button
              type="button"
              variant="secondary"
              onClick={() => void matchesQuery.refetch()}
            >
              Retry
            </Button>
          </div>
        </Alert>
      ) : null}

      {matchesQuery.isSuccess && matchesQuery.data.length === 0 ? (
        <Alert role="status" title="No matches available">
          Matches created in Admin will appear here. Nothing to open yet.
        </Alert>
      ) : null}

      {matchesQuery.isSuccess && matchesQuery.data.length > 0 ? (
        <ul className="grid gap-3" aria-label="Match list">
          {matchesQuery.data.map((match) => (
            <li key={match.id}>
              <MatchCard match={match} />
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
