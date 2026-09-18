import { useParams } from "react-router-dom";
import { ChaseSummaryPanel } from "@/components/ChaseSummaryPanel";
import { InningsScorecard } from "@/components/InningsScorecard";
import { MatchResultSummary } from "@/components/MatchResultSummary";
import { LoadingBlock } from "@/components/LoadingBlock";
import { StatusChip } from "@/components/StatusChip";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useMatchLiveSocket } from "@/hooks/use-match-live-socket";
import { useInningsDeliveries, useMatch } from "@/hooks/use-matches";
import {
  ApiError,
  type DeliveryHistoryItem,
  type Innings,
  type LiveConnectionStatus,
  type Match,
} from "@/lib/api/types";
import {
  computeChaseSummary,
  formatDeliveryOutcome,
  formatLabel,
  formatOversDisplay,
  isBowlerChangeRequired,
  statusLabel,
} from "@/lib/utils";

function scoreboardInnings(match: Match): Innings | undefined {
  const ordered = [...(match.innings ?? [])].sort(
    (a, b) => a.innings_number - b.innings_number,
  );
  const active = ordered.find((item) => item.status === "IN_PROGRESS");
  if (active) return active;
  return ordered.at(-1);
}

function recentDeliveries(items: DeliveryHistoryItem[]): DeliveryHistoryItem[] {
  return [...items].reverse().slice(0, 12);
}

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

function statusTone(
  status: string,
): "neutral" | "live" | "warn" | "success" {
  if (status === "IN_PROGRESS") return "live";
  if (status === "INNINGS_BREAK") return "warn";
  if (status === "COMPLETED") return "success";
  return "neutral";
}

export function ScoreboardPage() {
  const { matchId } = useParams<{ matchId: string }>();
  const matchQuery = useMatch(matchId);
  const match = matchQuery.data;
  const innings = match ? scoreboardInnings(match) : undefined;
  const deliveriesQuery = useInningsDeliveries(
    match?.status === "CREATED" ? undefined : innings?.id,
    matchId,
  );
  const live = useMatchLiveSocket(matchId);

  if (matchQuery.isLoading) {
    return <LoadingBlock label="Loading scoreboard…" lines={4} />;
  }

  if (matchQuery.isError || !match) {
    const notFound =
      matchQuery.error instanceof ApiError && matchQuery.error.status === 404;
    return (
      <div className="space-y-4">
        <Alert
          tone="error"
          title={notFound ? "Match not found" : "Unable to load scoreboard"}
        >
          <p>
            {matchQuery.error instanceof ApiError
              ? matchQuery.error.message
              : "Please try again."}
          </p>
          <Button
            className="mt-3"
            type="button"
            variant="secondary"
            onClick={() => void matchQuery.refetch()}
          >
            Retry
          </Button>
        </Alert>
      </div>
    );
  }

  return (
    <section className="space-y-5" aria-label="Match scoreboard">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-xl font-semibold tracking-tight text-[var(--color-skyline-deep)] sm:text-2xl">
            {match.team_1.name} vs {match.team_2.name}
          </h2>
          <p className="mt-1 text-sm text-[var(--color-muted)]">
            {formatLabel(match.format)} · {match.overs} overs
          </p>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <StatusChip
            label={statusLabel(match.status)}
            tone={statusTone(match.status)}
          />
          {match.status === "IN_PROGRESS" ? (
            <p
              role="status"
              aria-live="polite"
              aria-label={`Connection ${liveStatusLabel(live.status)}`}
              className="inline-flex items-center gap-1.5 rounded-md border border-[var(--color-line)] bg-white px-3 py-2 text-xs font-medium text-[var(--color-muted)]"
            >
              <span aria-hidden="true">
                {live.status === "live"
                  ? "●"
                  : live.status === "reconnecting" || live.status === "connecting"
                    ? "…"
                    : "○"}
              </span>
              {liveStatusLabel(live.status)}
            </p>
          ) : null}
        </div>
      </div>

      {match.status === "IN_PROGRESS" && live.lastError ? (
        <Alert tone="error" title="Live connection">
          <p>{live.lastError}</p>
        </Alert>
      ) : null}

      {match.status === "CREATED" ? (
        <Alert role="status" title="Match not started">
          <p>
            This match has not started yet. The scoreboard will show live
            scoring state once Admin starts the match.
          </p>
        </Alert>
      ) : null}

      {match.status === "INNINGS_BREAK" ? (
        <Alert role="status" title="Innings break">
          <p>
            Innings 1 is complete. Waiting for Innings 2 to start. This view is
            read-only.
          </p>
        </Alert>
      ) : null}

      {match.status === "COMPLETED" ? (
        <>
          <MatchResultSummary match={match} />
          <div className="space-y-4">
            {[...(match.innings ?? [])]
              .sort((a, b) => a.innings_number - b.innings_number)
              .map((item) => (
                <InningsScorecard key={item.id} innings={item} />
              ))}
          </div>
        </>
      ) : null}

      {!innings && match.status !== "CREATED" && match.status !== "COMPLETED" ? (
        <Alert title="No innings available">
          Innings data is not available for this match yet.
        </Alert>
      ) : null}

      {innings && match.status !== "COMPLETED" ? (
        <ScoreboardBody
          match={match}
          innings={innings}
          deliveries={deliveriesQuery.data ?? []}
          deliveriesLoading={deliveriesQuery.isLoading}
          deliveriesError={deliveriesQuery.isError}
          onRetryDeliveries={() => void deliveriesQuery.refetch()}
        />
      ) : null}
    </section>
  );
}

function ScoreboardBody({
  match,
  innings,
  deliveries,
  deliveriesLoading,
  deliveriesError,
  onRetryDeliveries,
}: {
  match: Match;
  innings: Innings;
  deliveries: DeliveryHistoryItem[];
  deliveriesLoading: boolean;
  deliveriesError: boolean;
  onRetryDeliveries: () => void;
}) {
  const total = innings.innings_total_runs ?? 0;
  const wickets = innings.wickets ?? 0;
  const overs = formatOversDisplay(innings.legal_delivery_count ?? 0);
  const freeHit = Boolean(innings.free_hit_pending);
  const recent = recentDeliveries(deliveries);
  const bowlerChangeRequired =
    isBowlerChangeRequired(innings) && !innings.replacement_required;
  const chase = computeChaseSummary({
    inningsNumber: innings.innings_number,
    target: innings.target,
    runs: total,
    legalDeliveryCount: innings.legal_delivery_count ?? 0,
    matchOvers: match.overs,
  });

  return (
    <>
      <div className="rounded-xl border border-[var(--color-line)] bg-white/95 p-5 shadow-sm sm:p-7">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-wide text-[var(--color-muted)]">
              Innings {innings.innings_number} · {statusLabel(innings.status)}
            </p>
            <p className="mt-2 text-sm font-medium text-[var(--color-ink)]">
              {innings.batting_team.name}
              <span className="font-normal text-[var(--color-muted)]">
                {" "}
                batting · {innings.bowling_team.name} bowling
              </span>
            </p>
            <p
              className="mt-3 text-6xl font-semibold tabular-nums leading-none tracking-tight text-[var(--color-skyline-deep)] sm:text-7xl"
              aria-live="polite"
              aria-label={`Score ${total} for ${wickets}`}
            >
              {total}/{wickets}
            </p>
            <p className="mt-3 text-base text-[var(--color-muted)]">
              {overs} overs
            </p>
          </div>
          <div className="flex flex-wrap items-start gap-3">
            {chase ? <ChaseSummaryPanel chase={chase} /> : null}
            {freeHit ? (
              <p
                role="status"
                aria-label="Free Hit pending"
                className="max-w-[11rem] rounded-md border-2 border-[var(--color-accent)] bg-[var(--color-sand)] px-3 py-2 text-sm font-semibold text-[var(--color-accent)]"
              >
                <span aria-hidden="true" className="mr-1">
                  ▲
                </span>
                FREE HIT
                <span className="mt-0.5 block text-xs font-medium normal-case tracking-normal text-[var(--color-ink)]">
                  Next ball protected
                </span>
              </p>
            ) : null}
          </div>
        </div>

        {innings.status === "COMPLETED" ? (
          <p className="mt-4 text-sm font-medium text-[var(--color-success)]">
            End of innings
          </p>
        ) : null}

        {innings.replacement_required ? (
          <p
            className="mt-4 inline-flex items-center gap-2 text-sm font-medium text-[var(--color-accent)]"
            role="status"
          >
            <StatusChip label="Waiting" tone="warn" />
            Replacement batter required (Admin).
          </p>
        ) : null}

        {bowlerChangeRequired ? (
          <p
            className="mt-4 inline-flex items-center gap-2 text-sm font-medium text-[var(--color-accent)]"
            role="status"
          >
            <StatusChip label="Waiting" tone="warn" />
            Replacement required — next bowler from {innings.bowling_team.name}{" "}
            (Admin).
          </p>
        ) : null}
      </div>

      <InningsScorecard innings={innings} />

      <div className="rounded-xl border border-[var(--color-line)] bg-white/95 p-5 shadow-sm sm:p-6">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-muted)]">
          Recent deliveries
        </h3>

        {deliveriesLoading ? (
          <div className="mt-3">
            <LoadingBlock label="Loading deliveries…" lines={2} />
          </div>
        ) : null}

        {deliveriesError ? (
          <Alert className="mt-3" tone="error" title="Unable to load deliveries">
            <Button type="button" variant="secondary" onClick={onRetryDeliveries}>
              Retry
            </Button>
          </Alert>
        ) : null}

        {!deliveriesLoading && !deliveriesError && recent.length === 0 ? (
          <p className="mt-3 text-sm text-[var(--color-muted)]">
            No deliveries yet. The board will update when Admin scores the first
            ball.
          </p>
        ) : null}

        {recent.length > 0 ? (
          <ul
            className="-mx-1 mt-4 flex gap-2 overflow-x-auto px-1 pb-1 sm:grid sm:grid-cols-2 sm:overflow-visible lg:grid-cols-3"
            aria-label="Recent deliveries"
          >
            {recent.map((delivery) => {
              const outcome = formatDeliveryOutcome(delivery);
              const isWicket = Boolean(delivery.wicket);
              return (
                <li
                  key={delivery.id}
                  className={
                    isWicket
                      ? "min-w-[9.5rem] shrink-0 rounded-md border border-[var(--color-danger)]/30 bg-[var(--color-danger)]/5 px-3 py-2 text-sm sm:min-w-0"
                      : "min-w-[9.5rem] shrink-0 rounded-md border border-[var(--color-line)] bg-[var(--color-sand)] px-3 py-2 text-sm sm:min-w-0"
                  }
                >
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="font-semibold tabular-nums text-[var(--color-skyline-deep)]">
                      {delivery.over_number}.{delivery.ball_in_over}
                    </span>
                    <span
                      className={
                        isWicket
                          ? "font-semibold text-[var(--color-danger)]"
                          : "font-semibold text-[var(--color-ink)]"
                      }
                      aria-label={
                        isWicket
                          ? `Wicket, ${delivery.wicket?.dismissed_player.name}`
                          : `Outcome ${outcome}`
                      }
                    >
                      {outcome}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-[var(--color-muted)]">
                    {String(delivery.delivery_type).replaceAll("_", " ")}
                    {delivery.is_free_hit ? " · Free Hit ball" : ""}
                    {delivery.wicket
                      ? ` · ${delivery.wicket.dismissed_player.name}`
                      : ""}
                  </p>
                </li>
              );
            })}
          </ul>
        ) : null}
      </div>

      {(match.innings?.length ?? 0) > 1 ? (
        <div className="space-y-4">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-muted)]">
            All innings
          </h3>
          {[...(match.innings ?? [])]
            .sort((a, b) => a.innings_number - b.innings_number)
            .filter((item) => item.id !== innings.id)
            .map((item) => (
              <InningsScorecard key={item.id} innings={item} />
            ))}
        </div>
      ) : null}
    </>
  );
}
