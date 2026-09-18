import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { LoadingBlock } from "@/components/LoadingBlock";
import { StatusChip } from "@/components/StatusChip";
import { useMatches } from "@/hooks/use-match-lifecycle";
import { ApiError } from "@/lib/api/types";
import { Link } from "react-router-dom";

function formatLabel(format: string): string {
  if (format === "ONE_DAY") return "One Day";
  if (format === "CUSTOM") return "Custom";
  return format;
}

function statusLabel(status: string): string {
  return status.replaceAll("_", " ");
}

function statusTone(
  status: string,
): "neutral" | "live" | "warn" | "success" {
  if (status === "IN_PROGRESS") return "live";
  if (status === "INNINGS_BREAK") return "warn";
  if (status === "COMPLETED") return "success";
  return "neutral";
}

export function MatchListPage() {
  const matchesQuery = useMatches();

  return (
    <section className="space-y-6" aria-label="Matches">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight text-[var(--color-pitch-deep)]">
          Matches
        </h2>
        <p className="mt-1 text-sm text-[var(--color-muted)]">
          Open a match to manage its lifecycle or score live. Use Create Match
          in the header to start a new fixture.
        </p>
      </div>

      {matchesQuery.isLoading ? (
        <LoadingBlock label="Loading matches…" lines={4} />
      ) : null}

      {matchesQuery.isError ? (
        <Alert tone="error" title="Unable to load matches">
          <div className="space-y-3">
            <p>
              {matchesQuery.error instanceof ApiError
                ? matchesQuery.error.message
                : "Please try again."}
            </p>
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
        <Alert role="status" title="No matches yet">
          <p>
            Create a match from the header to begin the lifecycle.
          </p>
        </Alert>
      ) : null}

      {matchesQuery.isSuccess && matchesQuery.data.length > 0 ? (
        <ul className="grid gap-3" aria-label="Admin match list">
          {matchesQuery.data.map((match) => {
            const title = `${match.team_1.name} vs ${match.team_2.name}`;
            return (
              <li key={match.id}>
                <Link
                  to={`/matches/${match.id}`}
                  aria-label={`${title}. ${formatLabel(match.format)} · ${match.overs} overs. Status ${statusLabel(match.status)}.`}
                  className="block rounded-xl border border-[var(--color-line)] bg-white/95 p-4 shadow-sm transition hover:border-[var(--color-accent)]"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h3 className="text-lg font-semibold text-[var(--color-pitch-deep)]">
                        {title}
                      </h3>
                      <p className="mt-1 text-sm text-[var(--color-muted)]">
                        {formatLabel(match.format)} · {match.overs} overs
                      </p>
                    </div>
                    <StatusChip
                      label={statusLabel(match.status)}
                      tone={statusTone(match.status)}
                    />
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      ) : null}
    </section>
  );
}
