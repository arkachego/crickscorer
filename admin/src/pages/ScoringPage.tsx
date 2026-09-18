import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { ChaseSummaryPanel } from "@/components/ChaseSummaryPanel";
import { InningsScorecard } from "@/components/InningsScorecard";
import { LiveStatusBadge } from "@/components/LiveStatusBadge";
import { LoadingBlock } from "@/components/LoadingBlock";
import { MatchResultSummary } from "@/components/MatchResultSummary";
import { StatusChip } from "@/components/StatusChip";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  useInningsDeliveries,
  useMatch,
  useStartNextInnings,
  useSubmitDelivery,
  useSubmitReplacement,
  useTeamPlayers,
  useUndoDelivery,
} from "@/hooks/use-match-lifecycle";
import { useMatchLiveSocket } from "@/hooks/use-match-live-socket";
import {
  ApiError,
  DISMISSAL_OPTIONS,
  NO_BAT_RUNS_DISMISSALS,
  NORMAL_RUNS,
  computeChaseSummary,
  formatOversDisplay,
  isBowlerChangeRequired,
  isEligibleBatter,
  isEligibleBowler,
  type DeliveryCreatePayload,
  type DeliveryType,
  type DismissalType,
  type Innings,
  type Match,
  type Player,
} from "@/lib/api/types";

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

function scoringInnings(match: Match): Innings | undefined {
  const active = activeInnings(match);
  if (active) return active;
  const ordered = [...(match.innings ?? [])].sort(
    (a, b) => b.innings_number - a.innings_number,
  );
  return ordered[0];
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 0) {
      return (
        "Network interrupted before a response was received. " +
        "Refresh match state before scoring again — do not resubmit blindly."
      );
    }
    if (error.status === 409) {
      return (
        error.message ||
        "The match state changed. Refresh the latest score before continuing."
      );
    }
    if (error.status >= 500) {
      return "A server error occurred. Refresh match state, then try again.";
    }
    return error.message;
  }
  return "Unable to complete the request. Please try again.";
}

function errorCode(error: unknown): string | undefined {
  return error instanceof ApiError ? error.code : undefined;
}

type ExtraMode = "WIDE" | "NO_BALL" | "BYE" | "LEG_BYE" | null;

export function ScoringPage() {
  const { matchId } = useParams<{ matchId: string }>();
  const matchQuery = useMatch(matchId);
  const match = matchQuery.data;
  const innings = match ? scoringInnings(match) : undefined;

  const battingPlayersQuery = useTeamPlayers(innings?.batting_team.id);
  const bowlingPlayersQuery = useTeamPlayers(innings?.bowling_team.id);
  const deliveriesQuery = useInningsDeliveries(innings?.id, matchId);
  const live = useMatchLiveSocket(matchId);

  const submitDelivery = useSubmitDelivery(matchId, innings?.id);
  const submitReplacement = useSubmitReplacement(matchId, innings?.id);
  const undoDelivery = useUndoDelivery(matchId, innings?.id);
  const startNext = useStartNextInnings(matchId);

  const [strikerId, setStrikerId] = useState("");
  const [nonStrikerId, setNonStrikerId] = useState("");
  const [bowlerId, setBowlerId] = useState("");
  const [extraMode, setExtraMode] = useState<ExtraMode>(null);
  const [extraRuns, setExtraRuns] = useState("1");
  const [noBallBatRuns, setNoBallBatRuns] = useState("0");
  const [wicketOpen, setWicketOpen] = useState(false);
  const [dismissedId, setDismissedId] = useState("");
  const [dismissalType, setDismissalType] = useState<DismissalType>("BOWLED");
  const [wicketBatRuns, setWicketBatRuns] = useState("0");
  const [replacementId, setReplacementId] = useState("");
  const [confirmUndo, setConfirmUndo] = useState(false);
  const [pendingBowlerId, setPendingBowlerId] = useState("");
  const clearedBowlerForLegal = useRef<number | null>(null);

  const strikerSelectId = useId();
  const nonStrikerSelectId = useId();
  const bowlerSelectId = useId();
  const extraRunsId = useId();
  const noBallRunsId = useId();
  const dismissedSelectId = useId();
  const dismissalSelectId = useId();
  const wicketRunsId = useId();
  const replacementSelectId = useId();

  const battingPlayers = battingPlayersQuery.data ?? [];
  const bowlingPlayers = bowlingPlayersQuery.data ?? [];
  const dismissedIdList = innings?.dismissed_player_ids ?? [];

  const eligibleBatters = useMemo(() => {
    const dismissed = new Set(dismissedIdList);
    return battingPlayers.filter(
      (player) => isEligibleBatter(player) && !dismissed.has(player.id),
    );
  }, [battingPlayers, dismissedIdList]);

  const eligibleBowlers = useMemo(
    () => bowlingPlayers.filter(isEligibleBowler),
    [bowlingPlayers],
  );

  const replacementCandidates = useMemo(() => {
    const active = new Set(
      [strikerId, nonStrikerId].filter(Boolean).concat(
        innings?.striker?.id ? [innings.striker.id] : [],
        innings?.non_striker?.id ? [innings.non_striker.id] : [],
      ),
    );
    return eligibleBatters.filter((player) => !active.has(player.id));
  }, [eligibleBatters, strikerId, nonStrikerId, innings]);

  useEffect(() => {
    // New innings (or swapped batting/bowling sides) must not keep prior picks.
    setStrikerId("");
    setNonStrikerId("");
    setBowlerId("");
    setPendingBowlerId("");
    setReplacementId("");
    setDismissedId("");
    setWicketOpen(false);
    setExtraMode(null);
    setConfirmUndo(false);
    clearedBowlerForLegal.current = null;
  }, [
    innings?.id,
    innings?.batting_team.id,
    innings?.bowling_team.id,
  ]);

  useEffect(() => {
    if (!innings) return;
    if (innings.status !== "IN_PROGRESS") {
      setStrikerId("");
      setNonStrikerId("");
      setBowlerId("");
      setPendingBowlerId("");
      return;
    }
    setStrikerId(innings.striker?.id ?? "");
    setNonStrikerId(innings.non_striker?.id ?? "");
  }, [innings?.id, innings?.status, innings?.striker?.id, innings?.non_striker?.id]);

  useEffect(() => {
    if (innings?.replacement_required) {
      setWicketOpen(false);
      setExtraMode(null);
    }
  }, [innings?.replacement_required]);

  const atOverBoundary = Boolean(
    innings && isBowlerChangeRequired(innings) && !innings.replacement_required,
  );

  useEffect(() => {
    if (!innings || !atOverBoundary) return;
    const legal = innings.legal_delivery_count ?? 0;
    if (clearedBowlerForLegal.current === legal) return;
    clearedBowlerForLegal.current = legal;
    setBowlerId("");
    setPendingBowlerId("");
  }, [atOverBoundary, innings]);

  useEffect(() => {
    if (!confirmUndo) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setConfirmUndo(false);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [confirmUndo]);

  const mutationPending =
    submitDelivery.isPending ||
    submitReplacement.isPending ||
    undoDelivery.isPending;

  const freeHit = Boolean(innings?.free_hit_pending);
  const replacementRequired = Boolean(innings?.replacement_required);
  const bowlerChangeRequired = atOverBoundary && !bowlerId;
  const scoringEnabled =
    match?.status === "IN_PROGRESS" &&
    innings?.status === "IN_PROGRESS" &&
    !replacementRequired &&
    !bowlerChangeRequired;
  /** Opening pair/bowler only — later changes use Replacement required banners. */
  const canEditActivePlayers =
    scoringEnabled && (innings?.delivery_count ?? 0) === 0;

  const mutationError =
    submitDelivery.error ??
    submitReplacement.error ??
    undoDelivery.error ??
    startNext.error ??
    null;

  async function runDelivery(payload: DeliveryCreatePayload) {
    try {
      await submitDelivery.mutateAsync(payload);
      setExtraMode(null);
      setWicketOpen(false);
      setConfirmUndo(false);
    } catch {
      // surfaced via mutation.error
    }
  }

  function pairReady(): boolean {
    return Boolean(strikerId && nonStrikerId && bowlerId && strikerId !== nonStrikerId);
  }

  function basePayload(): Omit<DeliveryCreatePayload, "delivery_type"> | null {
    if (!pairReady()) return null;
    return {
      striker_id: strikerId,
      non_striker_id: nonStrikerId,
      bowler_id: bowlerId,
    };
  }

  async function scoreNormal(runs: number) {
    const base = basePayload();
    if (!base || !scoringEnabled || mutationPending) return;
    await runDelivery({
      ...base,
      delivery_type: "NORMAL",
      bat_runs: runs,
    });
  }

  async function scoreExtra(type: Exclude<ExtraMode, null>) {
    const base = basePayload();
    if (!base || !scoringEnabled || mutationPending) return;
    if (type === "NO_BALL") {
      const bat = Number.parseInt(noBallBatRuns, 10);
      if (![0, 1, 2, 3, 4, 6].includes(bat)) return;
      await runDelivery({
        ...base,
        delivery_type: "NO_BALL",
        bat_runs: bat,
      });
      return;
    }
    const extra = Number.parseInt(extraRuns, 10);
    if (!Number.isFinite(extra) || extra < 1) return;
    await runDelivery({
      ...base,
      delivery_type: type as DeliveryType,
      bat_runs: 0,
      extra_runs: extra,
    });
  }

  async function scoreWicket() {
    const base = basePayload();
    if (!base || !scoringEnabled || mutationPending || freeHit) return;
    if (!dismissedId) return;
    const bat = NO_BAT_RUNS_DISMISSALS.has(dismissalType)
      ? 0
      : Number.parseInt(wicketBatRuns, 10);
    if (![0, 1, 2, 3, 4, 6].includes(bat)) return;
    await runDelivery({
      ...base,
      delivery_type: "NORMAL",
      bat_runs: bat,
      wicket: {
        dismissed_player_id: dismissedId,
        dismissal_type: dismissalType,
      },
    });
  }

  async function replaceBatter() {
    if (!replacementId || !replacementRequired || mutationPending) return;
    try {
      await submitReplacement.mutateAsync(replacementId);
      setReplacementId("");
    } catch {
      // surfaced via mutation.error
    }
  }

  async function confirmUndoAction() {
    if (mutationPending) return;
    try {
      await undoDelivery.mutateAsync();
      setConfirmUndo(false);
    } catch {
      // surfaced via mutation.error
    }
  }

  if (matchQuery.isLoading) {
    return <LoadingBlock label="Loading scoring workspace…" lines={4} />;
  }

  if (matchQuery.isError || !match) {
    const notFound =
      matchQuery.error instanceof ApiError && matchQuery.error.status === 404;
    return (
      <div className="space-y-4">
        <Alert tone="error" title={notFound ? "Match not found" : "Unable to load match"}>
          <p>{errorMessage(matchQuery.error)}</p>
        </Alert>
        <Link
          to="/matches"
          className="text-sm font-medium text-[var(--color-accent)] hover:underline"
        >
          Back to matches
        </Link>
      </div>
    );
  }

  if (!innings) {
    return (
      <div className="space-y-4">
        <Alert title="No innings available">
          Start the match from the match detail page before scoring.
        </Alert>
        <Link
          to={`/matches/${match.id}`}
          className="text-sm font-medium text-[var(--color-accent)] hover:underline"
        >
          Back to match
        </Link>
      </div>
    );
  }

  const total = innings.innings_total_runs ?? 0;
  const wickets = innings.wickets ?? 0;
  const overs = formatOversDisplay(innings.legal_delivery_count ?? 0);
  const chase = computeChaseSummary({
    inningsNumber: innings.innings_number,
    target: innings.target,
    runs: total,
    legalDeliveryCount: innings.legal_delivery_count ?? 0,
    matchOvers: match.overs,
  });
  const deliveries = [...(deliveriesQuery.data ?? [])].reverse().slice(0, 12);
  const activeDismissOptions = [
    innings.striker,
    innings.non_striker,
  ].filter((player): player is NonNullable<typeof player> => Boolean(player));
  // Prefer local selection when opening pair not yet persisted.
  const dismissChoices =
    activeDismissOptions.length > 0
      ? activeDismissOptions
      : ([
          battingPlayers.find((p) => p.id === strikerId),
          battingPlayers.find((p) => p.id === nonStrikerId),
        ].filter(Boolean) as Player[]);

  const loadingLabel = submitDelivery.isPending
    ? wicketOpen
      ? "Recording wicket…"
      : "Scoring…"
    : submitReplacement.isPending
      ? "Replacing batter…"
      : undoDelivery.isPending
        ? "Undoing…"
        : null;

  if (match.status === "COMPLETED") {
    return (
      <section className="space-y-5" aria-label="Match result">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-xl font-semibold tracking-tight text-[var(--color-pitch-deep)] sm:text-2xl">
              {match.team_1.name} vs {match.team_2.name}
            </h2>
            <p className="mt-1 text-sm text-[var(--color-muted)]">
              {formatLabel(match.format)} · {match.overs} overs
            </p>
          </div>
          <StatusChip label={statusLabel(match.status)} tone="success" />
        </div>

        <MatchResultSummary match={match} />

        <div className="space-y-4">
          {[...(match.innings ?? [])]
            .sort((a, b) => a.innings_number - b.innings_number)
            .map((item) => (
              <InningsScorecard key={item.id} innings={item} />
            ))}
        </div>
      </section>
    );
  }

  return (
    <section className="space-y-5" aria-label="Scoring workspace" aria-busy={mutationPending}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-xl font-semibold tracking-tight text-[var(--color-pitch-deep)] sm:text-2xl">
            {match.team_1.name} vs {match.team_2.name}
          </h2>
          <p className="mt-1 text-sm text-[var(--color-muted)]">
            {formatLabel(match.format)} · Innings {innings.innings_number}
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            <StatusChip
              label={statusLabel(match.status)}
              tone={
                match.status === "IN_PROGRESS"
                  ? "live"
                  : match.status === "INNINGS_BREAK"
                    ? "warn"
                    : "neutral"
              }
            />
            <StatusChip
              label={`Inn ${innings.innings_number}: ${statusLabel(innings.status)}`}
            />
          </div>
        </div>
        {match.status === "IN_PROGRESS" ? (
          <LiveStatusBadge status={live.status} />
        ) : null}
      </div>

      {live.lastError ? (
        <Alert tone="error" title="Live updates paused">
          <p>{live.lastError}</p>
          <p className="mt-1 text-sm">
            You can still score via REST. Refresh match state if totals look stale.
          </p>
        </Alert>
      ) : null}

      <div className="rounded-xl border border-[var(--color-line)] bg-white/95 p-4 shadow-sm sm:p-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-wide text-[var(--color-muted)]">
              {innings.batting_team.name} batting
            </p>
            <p
              className="mt-1 text-5xl font-semibold tabular-nums leading-none text-[var(--color-pitch-deep)] sm:text-6xl"
              aria-live="polite"
              aria-label={`Score ${total} for ${wickets}, ${overs} overs`}
            >
              {total}/{wickets}
            </p>
            <p className="mt-2 text-sm text-[var(--color-muted)]">
              {overs} overs · bowling {innings.bowling_team.name}
            </p>
          </div>
          <div className="flex flex-wrap items-start gap-3">
            {chase ? <ChaseSummaryPanel chase={chase} /> : null}
            {freeHit ? (
              <p
                role="status"
                aria-label="Free Hit pending"
                className="max-w-[12rem] rounded-md border-2 border-[var(--color-accent)] bg-[var(--color-cream)] px-3 py-2 text-sm font-semibold text-[var(--color-accent)]"
              >
                <span aria-hidden="true" className="mr-1">
                  ▲
                </span>
                FREE HIT
                <span className="mt-0.5 block text-xs font-medium normal-case tracking-normal text-[var(--color-ink)]">
                  Next legal ball protected
                </span>
              </p>
            ) : null}
          </div>
        </div>
      </div>

      {match.status === "INNINGS_BREAK" ? (
        <Alert title="Innings break">
          <div className="space-y-3">
            <p>Scoring is paused until the next innings starts.</p>
            <Button
              type="button"
              disabled={startNext.isPending}
              onClick={() => void startNext.mutateAsync(match.id).catch(() => undefined)}
            >
              {startNext.isPending ? "Starting next innings…" : "Start Next Innings"}
            </Button>
          </div>
        </Alert>
      ) : null}

      {innings.status === "COMPLETED" ? (
        <Alert title="Innings completed">
          Delivery controls are disabled. Use match lifecycle actions as needed.
        </Alert>
      ) : null}

      {replacementRequired ? (
        <div
          className="rounded-xl border-2 border-[var(--color-accent)] bg-[var(--color-cream)] p-4 shadow-sm sm:p-5"
          role="region"
          aria-label="Replacement required"
        >
          <div className="flex flex-wrap items-center gap-2">
            <StatusChip label="Action required" tone="warn" />
            <h3 className="text-base font-semibold text-[var(--color-pitch-deep)]">
              Replacement required
            </h3>
          </div>
          <p className="mt-2 text-sm text-[var(--color-ink)]">
            Select an eligible batting-team playing-XI member before the next
            delivery. Scoring controls stay locked until you confirm.
          </p>
          <div className="mt-4 space-y-2">
            <Label htmlFor={replacementSelectId}>Replacement batter</Label>
            <Select
              value={replacementId || undefined}
              disabled={mutationPending}
              onValueChange={setReplacementId}
            >
              <SelectTrigger id={replacementSelectId}>
                <SelectValue placeholder="Select player" />
              </SelectTrigger>
              <SelectContent>
                {replacementCandidates.map((player) => (
                  <SelectItem key={player.id} value={player.id}>
                    {player.batting_order}. {player.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button
            className="mt-4"
            type="button"
            disabled={!replacementId || mutationPending}
            onClick={() => void replaceBatter()}
          >
            {submitReplacement.isPending ? "Replacing batter…" : "Confirm Replacement"}
          </Button>
        </div>
      ) : null}

      {bowlerChangeRequired ? (
        <div
          className="rounded-xl border-2 border-[var(--color-accent)] bg-[var(--color-cream)] p-4 shadow-sm sm:p-5"
          role="region"
          aria-label="Bowler change required"
        >
          <div className="flex flex-wrap items-center gap-2">
            <StatusChip label="Action required" tone="warn" />
            <h3 className="text-base font-semibold text-[var(--color-pitch-deep)]">
              Replacement required
            </h3>
          </div>
          <p className="mt-2 text-sm text-[var(--color-ink)]">
            Over complete. Select the next bowler from {innings?.bowling_team.name}{" "}
            before the next delivery. Scoring stays locked until you confirm.
          </p>
          <div className="mt-4 space-y-2">
            <Label htmlFor={`${bowlerSelectId}-change`}>Next bowler</Label>
            <Select
              value={pendingBowlerId || undefined}
              disabled={mutationPending}
              onValueChange={setPendingBowlerId}
            >
              <SelectTrigger id={`${bowlerSelectId}-change`}>
                <SelectValue placeholder="Select bowler" />
              </SelectTrigger>
              <SelectContent>
                {eligibleBowlers.map((player) => (
                  <SelectItem key={player.id} value={player.id}>
                    {player.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button
            className="mt-4"
            type="button"
            disabled={!pendingBowlerId || mutationPending}
            onClick={() => {
              setBowlerId(pendingBowlerId);
              setPendingBowlerId("");
            }}
          >
            Confirm Bowler
          </Button>
        </div>
      ) : null}

      <div className="rounded-xl border border-[var(--color-line)] bg-white/95 p-4 shadow-sm sm:p-5">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-muted)]">
          Active players
        </h3>
        <p className="mt-1 text-sm text-[var(--color-muted)]">
          {canEditActivePlayers
            ? "Select the opening pair and first bowler before the first delivery."
            : "Locked after scoring starts. Use Replacement required for batter or bowler changes."}
        </p>
        <div className="mt-4 grid gap-4 sm:grid-cols-3">
          <div className="space-y-2">
            <Label htmlFor={strikerSelectId}>Striker</Label>
            <Select
              value={strikerId || undefined}
              disabled={!canEditActivePlayers || mutationPending}
              onValueChange={setStrikerId}
            >
              <SelectTrigger id={strikerSelectId}>
                <SelectValue placeholder="Select striker" />
              </SelectTrigger>
              <SelectContent>
                {eligibleBatters
                  .filter((player) => player.id !== nonStrikerId)
                  .map((player) => (
                    <SelectItem key={player.id} value={player.id}>
                      {player.batting_order}. {player.name}
                    </SelectItem>
                  ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor={nonStrikerSelectId}>Non-striker</Label>
            <Select
              value={nonStrikerId || undefined}
              disabled={!canEditActivePlayers || mutationPending}
              onValueChange={setNonStrikerId}
            >
              <SelectTrigger id={nonStrikerSelectId}>
                <SelectValue placeholder="Select non-striker" />
              </SelectTrigger>
              <SelectContent>
                {eligibleBatters
                  .filter((player) => player.id !== strikerId)
                  .map((player) => (
                    <SelectItem key={player.id} value={player.id}>
                      {player.batting_order}. {player.name}
                    </SelectItem>
                  ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor={bowlerSelectId}>Bowler</Label>
            <Select
              value={bowlerId || undefined}
              disabled={!canEditActivePlayers || mutationPending}
              onValueChange={setBowlerId}
            >
              <SelectTrigger id={bowlerSelectId}>
                <SelectValue placeholder="Select bowler" />
              </SelectTrigger>
              <SelectContent>
                {eligibleBowlers.map((player) => (
                  <SelectItem key={player.id} value={player.id}>
                    {player.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        {strikerId && nonStrikerId && strikerId === nonStrikerId ? (
          <p className="mt-3 text-sm text-[var(--color-danger)]" role="alert">
            Striker and non-striker must be different players.
          </p>
        ) : null}
      </div>

      <div className="rounded-xl border border-[var(--color-line)] bg-white/95 p-4 shadow-sm sm:p-5">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-muted)]">
          Delivery controls
        </h3>
        <p className="mt-1 text-sm text-[var(--color-muted)]">
          Server remains authoritative for totals, legality, and Free Hit.
        </p>

        <div
          className="mt-4 grid grid-cols-3 gap-2 sm:grid-cols-6"
          role="group"
          aria-label="Normal runs"
        >
          {NORMAL_RUNS.map((runs) => (
            <button
              key={runs}
              type="button"
              aria-label={`Score ${runs} run${runs === 1 ? "" : "s"}`}
              disabled={!scoringEnabled || mutationPending || !pairReady()}
              onClick={() => void scoreNormal(runs)}
              className="inline-flex min-h-14 items-center justify-center rounded-md border border-[var(--color-line)] bg-[var(--color-cream)] text-xl font-semibold text-[var(--color-pitch-deep)] transition hover:border-[var(--color-accent)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {runs}
            </button>
          ))}
        </div>

        <div className="mt-4 grid grid-cols-2 gap-2 sm:flex sm:flex-wrap" role="group" aria-label="Extras">
          {(
            [
              ["WIDE", "Wide"],
              ["NO_BALL", "No Ball"],
              ["BYE", "Bye"],
              ["LEG_BYE", "Leg Bye"],
            ] as const
          ).map(([value, label]) => (
            <Button
              key={value}
              type="button"
              variant={extraMode === value ? "primary" : "secondary"}
              disabled={!scoringEnabled || mutationPending || !pairReady()}
              aria-pressed={extraMode === value}
              onClick={() =>
                setExtraMode((current) => (current === value ? null : value))
              }
              className="min-h-12 min-w-[6.5rem] sm:w-auto"
            >
              {label}
            </Button>
          ))}
        </div>

        {extraMode ? (
          <div className="mt-4 space-y-3 rounded-md border border-[var(--color-line)] bg-[var(--color-cream)] p-3">
            {extraMode === "NO_BALL" ? (
              <>
                <p className="text-sm text-[var(--color-muted)]">
                  No-ball adds 1 penalty run. Optional bat runs: 0, 1, 2, 3, 4, or 6.
                  Does not consume a legal ball; next delivery is a Free Hit.
                </p>
                <div className="space-y-2">
                  <Label htmlFor={noBallRunsId}>Bat runs with no-ball</Label>
                  <Select
                    value={noBallBatRuns}
                    onValueChange={setNoBallBatRuns}
                    disabled={mutationPending}
                  >
                    <SelectTrigger id={noBallRunsId}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {NORMAL_RUNS.map((runs) => (
                        <SelectItem key={runs} value={String(runs)}>
                          {runs}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </>
            ) : (
              <>
                <p className="text-sm text-[var(--color-muted)]">
                  {extraMode === "WIDE"
                    ? "Wide does not consume a legal ball."
                    : `${extraMode === "BYE" ? "Bye" : "Leg bye"} runs are extras only (bat runs stay 0).`}
                </p>
                <div className="space-y-2">
                  <Label htmlFor={extraRunsId}>Extra runs</Label>
                  <Select
                    value={extraRuns}
                    onValueChange={setExtraRuns}
                    disabled={mutationPending}
                  >
                    <SelectTrigger id={extraRunsId}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {[1, 2, 3, 4, 5].map((runs) => (
                        <SelectItem key={runs} value={String(runs)}>
                          {runs}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </>
            )}
            <Button
              type="button"
              disabled={mutationPending || !pairReady()}
              onClick={() => void scoreExtra(extraMode)}
            >
              {submitDelivery.isPending ? "Scoring…" : `Submit ${extraMode.replaceAll("_", " ")}`}
            </Button>
          </div>
        ) : null}

        <div className="mt-4">
          <Button
            type="button"
            variant="secondary"
            disabled={
              !scoringEnabled || mutationPending || !pairReady() || freeHit
            }
            aria-disabled={freeHit || undefined}
            onClick={() => {
              setWicketOpen((open) => !open);
              setDismissedId(strikerId || innings.striker?.id || "");
            }}
          >
            {wicketOpen ? "Cancel Wicket" : "Wicket"}
          </Button>
          {freeHit ? (
            <p className="mt-2 text-sm text-[var(--color-muted)]" role="status">
              Wicket is disabled while Free Hit is pending.
            </p>
          ) : null}
        </div>

        {wicketOpen && !freeHit ? (
          <div
            className="mt-4 space-y-3 rounded-md border border-[var(--color-line)] bg-[var(--color-cream)] p-3"
            role="region"
            aria-label="Wicket controls"
          >
            <div className="space-y-2">
              <Label htmlFor={dismissedSelectId}>Dismissed player</Label>
              <Select
                value={dismissedId || undefined}
                onValueChange={setDismissedId}
                disabled={mutationPending}
              >
                <SelectTrigger id={dismissedSelectId}>
                  <SelectValue placeholder="Select dismissed batter" />
                </SelectTrigger>
                <SelectContent>
                  {dismissChoices.map((player) => (
                    <SelectItem key={player.id} value={player.id}>
                      {player.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor={dismissalSelectId}>Dismissal type</Label>
              <Select
                value={dismissalType}
                onValueChange={(value) => {
                  const next = value as DismissalType;
                  setDismissalType(next);
                  if (NO_BAT_RUNS_DISMISSALS.has(next)) {
                    setWicketBatRuns("0");
                  }
                }}
                disabled={mutationPending}
              >
                <SelectTrigger id={dismissalSelectId}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {DISMISSAL_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {!NO_BAT_RUNS_DISMISSALS.has(dismissalType) ? (
              <div className="space-y-2">
                <Label htmlFor={wicketRunsId}>Bat runs on this delivery</Label>
                <Select
                  value={wicketBatRuns}
                  onValueChange={setWicketBatRuns}
                  disabled={mutationPending}
                >
                  <SelectTrigger id={wicketRunsId}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {NORMAL_RUNS.map((runs) => (
                      <SelectItem key={runs} value={String(runs)}>
                        {runs}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            ) : null}
            <Button
              type="button"
              disabled={mutationPending || !dismissedId || !pairReady()}
              onClick={() => void scoreWicket()}
            >
              {submitDelivery.isPending ? "Recording wicket…" : "Record Wicket"}
            </Button>
          </div>
        ) : null}
      </div>

      <div className="rounded-xl border border-[var(--color-line)] bg-white/95 p-4 shadow-sm sm:p-5">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-muted)]">
          Undo
        </h3>
        {!confirmUndo ? (
          <Button
            className="mt-3"
            type="button"
            variant="secondary"
            disabled={
              mutationPending ||
              (innings.delivery_count ?? 0) < 1 ||
              innings.status === "NOT_STARTED"
            }
            onClick={() => setConfirmUndo(true)}
          >
            Undo Last Delivery
          </Button>
        ) : (
          <div
            className="mt-3 space-y-3 rounded-md border border-[var(--color-line)] bg-[var(--color-cream)] p-3"
            role="alertdialog"
            aria-labelledby="undo-confirm-title"
            aria-describedby="undo-confirm-desc"
          >
            <p id="undo-confirm-title" className="font-semibold">
              Undo the last delivery?
            </p>
            <p id="undo-confirm-desc" className="text-sm text-[var(--color-muted)]">
              This will remove the most recent scoring event.
            </p>
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="secondary"
                disabled={mutationPending}
                onClick={() => setConfirmUndo(false)}
              >
                Cancel
              </Button>
              <Button
                type="button"
                disabled={mutationPending}
                onClick={() => void confirmUndoAction()}
              >
                {undoDelivery.isPending ? "Undoing…" : "Undo"}
              </Button>
            </div>
          </div>
        )}
      </div>

      <InningsScorecard innings={innings} />

      <div className="rounded-xl border border-[var(--color-line)] bg-white/95 p-4 shadow-sm sm:p-5">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-muted)]">
          Recent deliveries
        </h3>
        {deliveriesQuery.isLoading ? (
          <LoadingBlock label="Loading deliveries…" lines={2} />
        ) : null}
        {deliveries.length === 0 && deliveriesQuery.isSuccess ? (
          <p className="mt-3 text-sm text-[var(--color-muted)]">
            No deliveries yet. Use the run buttons above to score the first ball.
          </p>
        ) : null}
        {deliveries.length > 0 ? (
          <ul
            className="-mx-1 mt-3 flex gap-2 overflow-x-auto px-1 pb-1 sm:grid sm:grid-cols-2 sm:overflow-visible lg:grid-cols-3"
            aria-label="Recent deliveries"
          >
            {deliveries.map((delivery) => {
              const isWicket = Boolean(delivery.wicket);
              return (
                <li
                  key={delivery.id}
                  className={
                    isWicket
                      ? "min-w-[9.5rem] shrink-0 rounded-md border border-[var(--color-danger)]/30 bg-[var(--color-danger)]/5 px-3 py-2 text-sm sm:min-w-0"
                      : "min-w-[9.5rem] shrink-0 rounded-md border border-[var(--color-line)] bg-[var(--color-cream)] px-3 py-2 text-sm sm:min-w-0"
                  }
                >
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="font-semibold tabular-nums">
                      {delivery.over_number}.{delivery.ball_in_over}
                    </span>
                    <span
                      className={
                        isWicket
                          ? "font-semibold text-[var(--color-danger)]"
                          : "font-semibold"
                      }
                    >
                      {isWicket
                        ? "W"
                        : delivery.delivery_type === "WIDE"
                          ? `Wd ${delivery.total_runs}`
                          : delivery.delivery_type === "NO_BALL"
                            ? `Nb ${delivery.total_runs}`
                            : delivery.delivery_type === "BYE"
                              ? `B ${delivery.total_runs}`
                              : delivery.delivery_type === "LEG_BYE"
                                ? `LB ${delivery.total_runs}`
                                : String(delivery.total_runs)}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-[var(--color-muted)]">
                    {String(delivery.delivery_type).replaceAll("_", " ")}
                    {delivery.is_free_hit ? " · FH" : ""}
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

      {loadingLabel ? (
        <p
          role="status"
          aria-live="polite"
          className="rounded-md border border-[var(--color-line)] bg-white px-3 py-2 text-sm font-medium text-[var(--color-muted)]"
        >
          {loadingLabel}
        </p>
      ) : null}

      {mutationError ? (
        <Alert tone="error" title="Scoring action failed">
          <p>{errorMessage(mutationError)}</p>
          {errorCode(mutationError) ? (
            <p className="mt-1 font-mono text-xs opacity-80">
              {errorCode(mutationError)}
            </p>
          ) : null}
          <Button
            className="mt-3"
            type="button"
            variant="secondary"
            onClick={() => {
              void matchQuery.refetch();
              void deliveriesQuery.refetch();
              submitDelivery.reset();
              submitReplacement.reset();
              undoDelivery.reset();
              startNext.reset();
            }}
          >
            Refresh match state
          </Button>
        </Alert>
      ) : null}
    </section>
  );
}
