export type MatchFormat = "T10" | "T20" | "ONE_DAY" | "CUSTOM";

export type MatchStatus =
  | "CREATED"
  | "IN_PROGRESS"
  | "INNINGS_BREAK"
  | "COMPLETED";

export type InningsStatus = "NOT_STARTED" | "IN_PROGRESS" | "COMPLETED";

export type DeliveryType = "NORMAL" | "WIDE" | "NO_BALL" | "BYE" | "LEG_BYE";

export type DismissalType =
  | "BOWLED"
  | "CAUGHT"
  | "LBW"
  | "RUN_OUT"
  | "STUMPED";

export interface Team {
  id: string;
  name: string;
  short_code: string;
  flag_url: string;
}

export interface PlayerBrief {
  id: string;
  name: string;
}

export interface BatterScorecardRow {
  player: PlayerBrief;
  dismissal_text: string;
  is_not_out: boolean;
  runs: number;
  balls: number;
  fours: number;
  sixes: number;
  strike_rate: number;
}

export interface BowlerScorecardRow {
  player: PlayerBrief;
  overs: string;
  maidens: number;
  runs: number;
  wickets: number;
  noballs: number;
  wides: number;
  economy: number;
}

export interface ExtrasBreakdown {
  byes: number;
  leg_byes: number;
  wides: number;
  noballs: number;
  total: number;
}

export interface InningsScorecardData {
  batters: BatterScorecardRow[];
  extras: ExtrasBreakdown;
  did_not_bat: PlayerBrief[];
  bowlers: BowlerScorecardRow[];
  total_runs: number;
  wickets: number;
  overs_display: string;
  run_rate: number;
}

export interface Player {
  id: string;
  team_id: string;
  name: string;
  batting_order: number | null;
  roles: string[];
}

export interface Innings {
  id: string;
  innings_number: number;
  batting_team: Team;
  bowling_team: Team;
  status: InningsStatus | string;
  created_at: string;
  striker?: PlayerBrief | null;
  non_striker?: PlayerBrief | null;
  replacement_required?: boolean;
  target?: number | null;
  innings_total_runs?: number;
  legal_delivery_count?: number;
  delivery_count?: number;
  next_over_number?: number;
  next_ball_in_over?: number;
  free_hit_pending?: boolean;
  wickets?: number;
  dismissed_player_ids?: string[];
  scorecard?: InningsScorecardData;
}

export interface Match {
  id: string;
  team_1: Team;
  team_2: Team;
  batting_first_team: Team;
  format: MatchFormat | string;
  overs: number;
  status: MatchStatus | string;
  created_at: string;
  innings?: Innings[];
}

export interface MatchCreatePayload {
  team_1_id: string;
  team_2_id: string;
  format: MatchFormat;
  batting_first_team_id: string;
  overs: number;
}

export interface WicketPayload {
  dismissed_player_id: string;
  dismissal_type: DismissalType;
}

export interface DeliveryCreatePayload {
  striker_id: string;
  non_striker_id: string;
  bowler_id: string;
  delivery_type: DeliveryType;
  bat_runs?: number;
  extra_runs?: number;
  wicket?: WicketPayload;
}

export interface DeliveryResponse {
  id: string;
  innings_id: string;
  sequence_no: number;
  over_number: number;
  ball_in_over: number;
  striker: PlayerBrief;
  non_striker: PlayerBrief;
  bowler: PlayerBrief;
  delivery_type: DeliveryType | string;
  bat_runs: number;
  wide_runs: number;
  no_ball_runs: number;
  bye_runs: number;
  leg_bye_runs: number;
  total_runs: number;
  is_legal: boolean;
  is_free_hit: boolean;
  wicket: {
    dismissed_player: PlayerBrief;
    dismissal_type: DismissalType | string;
  } | null;
  innings_status: InningsStatus | string;
  match_status: MatchStatus | string;
  innings_total_runs: number;
  replacement_required: boolean;
}

export type DeliveryHistoryItem = Omit<
  DeliveryResponse,
  "innings_id" | "innings_status" | "match_status" | "innings_total_runs" | "replacement_required"
>;

export interface MatchLiveSnapshot {
  match_id: string;
  version: number;
  match: Match;
  deliveries_by_innings: Record<string, DeliveryHistoryItem[]>;
}

export type LiveConnectionStatus =
  | "connecting"
  | "live"
  | "reconnecting"
  | "disconnected"
  | "error";

export interface UndoResponse {
  match: Match;
  innings_id: string;
  delivery_count: number;
  legal_delivery_count: number;
  innings_total_runs: number;
  next_over_number: number;
  next_ball_in_over: number;
  free_hit_pending: boolean;
  replacement_required: boolean;
  innings_status: InningsStatus | string;
  match_status: MatchStatus | string;
  striker: PlayerBrief | null;
  non_striker: PlayerBrief | null;
}

export interface ApiErrorBody {
  detail:
    | {
        code?: string;
        message?: string;
      }
    | Array<{ msg?: string; loc?: unknown }>
    | string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export const CREATABLE_FORMATS: ReadonlyArray<{
  value: MatchFormat;
  label: string;
}> = [
  { value: "T10", label: "T10" },
  { value: "T20", label: "T20" },
  { value: "ONE_DAY", label: "One Day" },
  { value: "CUSTOM", label: "Custom" },
];

export const FIXED_FORMAT_OVERS: Record<Exclude<MatchFormat, "CUSTOM">, number> =
  {
    T10: 10,
    T20: 20,
    ONE_DAY: 50,
  };

export const DISMISSAL_OPTIONS: ReadonlyArray<{
  value: DismissalType;
  label: string;
}> = [
  { value: "BOWLED", label: "Bowled" },
  { value: "LBW", label: "LBW" },
  { value: "STUMPED", label: "Stumped" },
  { value: "CAUGHT", label: "Caught" },
  { value: "RUN_OUT", label: "Run Out" },
];

/** Dismissals that cannot include bat runs on the same delivery. */
export const NO_BAT_RUNS_DISMISSALS: ReadonlySet<DismissalType> = new Set([
  "BOWLED",
  "LBW",
  "STUMPED",
]);

export const NORMAL_RUNS = [0, 1, 2, 3, 4, 6] as const;

export function oversForFormat(
  format: MatchFormat,
  customOvers: string,
): number | null {
  if (format === "CUSTOM") {
    if (!/^\d+$/.test(customOvers.trim())) {
      return null;
    }
    return Number.parseInt(customOvers, 10);
  }
  return FIXED_FORMAT_OVERS[format];
}

export function formatOversDisplay(legalDeliveryCount: number): string {
  const overs = Math.floor(legalDeliveryCount / 6);
  const balls = legalDeliveryCount % 6;
  return `${overs}.${balls}`;
}

export interface ChaseSummary {
  target: number;
  runsNeeded: number;
  ballsRemaining: number;
  requiredRunRate: number | null;
  targetAchieved: boolean;
}

/** Second-innings chase figures from target, score, and match overs. */
export function computeChaseSummary(input: {
  inningsNumber: number;
  target: number | null | undefined;
  runs: number;
  legalDeliveryCount: number;
  matchOvers: number;
}): ChaseSummary | null {
  if (input.inningsNumber < 2) return null;
  if (input.target == null || input.target < 1) return null;
  if (input.matchOvers < 1) return null;

  const maxBalls = input.matchOvers * 6;
  const ballsRemaining = Math.max(0, maxBalls - input.legalDeliveryCount);
  const runsNeeded = Math.max(0, input.target - input.runs);
  const targetAchieved = input.runs >= input.target;
  let requiredRunRate: number | null = null;
  if (!targetAchieved && ballsRemaining > 0) {
    requiredRunRate = Math.round((runsNeeded * 6 * 100) / ballsRemaining) / 100;
  } else if (!targetAchieved && ballsRemaining === 0) {
    requiredRunRate = null;
  } else {
    requiredRunRate = 0;
  }

  return {
    target: input.target,
    runsNeeded,
    ballsRemaining,
    requiredRunRate,
    targetAchieved,
  };
}

export type MatchResultInningsLine = {
  team: { id: string; name: string; short_code: string; flag_url: string };
  runs: number;
  wickets: number;
  oversDisplay: string;
  runRate: number;
  inningsNumber: number;
};

export type MatchResultSummaryData = {
  lines: MatchResultInningsLine[];
  outcome:
    | {
        kind: "win";
        winner: MatchResultInningsLine["team"];
        margin: string;
      }
    | { kind: "tie" }
    | { kind: "unavailable" };
};

function decimalOvers(legalDeliveryCount: number): number {
  return (
    Math.floor(legalDeliveryCount / 6) + (legalDeliveryCount % 6) / 6
  );
}

function inningsRunRate(runs: number, legalDeliveryCount: number): number {
  const overs = decimalOvers(legalDeliveryCount);
  if (overs <= 0) return 0;
  return Math.round((runs / overs) * 100) / 100;
}

/** Final match result from completed innings (limited-overs, two innings). */
export function computeMatchResult(match: {
  status: string;
  overs: number;
  innings?: Array<{
    innings_number: number;
    status: string;
    batting_team: MatchResultInningsLine["team"];
    innings_total_runs?: number;
    wickets?: number;
    legal_delivery_count?: number;
    target?: number | null;
    scorecard?: { run_rate?: number; overs_display?: string } | null;
  }>;
}): MatchResultSummaryData | null {
  if (match.status !== "COMPLETED") return null;

  const ordered = [...(match.innings ?? [])].sort(
    (a, b) => a.innings_number - b.innings_number,
  );
  if (ordered.length < 2) return null;

  const lines: MatchResultInningsLine[] = ordered.map((item) => {
    const runs = item.innings_total_runs ?? 0;
    const legal = item.legal_delivery_count ?? 0;
    return {
      team: item.batting_team,
      runs,
      wickets: item.wickets ?? 0,
      oversDisplay:
        item.scorecard?.overs_display ?? formatOversDisplay(legal),
      runRate: item.scorecard?.run_rate ?? inningsRunRate(runs, legal),
      inningsNumber: item.innings_number,
    };
  });

  const first = lines.find((line) => line.inningsNumber === 1);
  const second = lines.find((line) => line.inningsNumber === 2);
  if (!first || !second) {
    return { lines, outcome: { kind: "unavailable" } };
  }

  if (second.runs > first.runs) {
    const wicketsRemaining = Math.max(0, 10 - second.wickets);
    return {
      lines,
      outcome: {
        kind: "win",
        winner: second.team,
        margin:
          wicketsRemaining === 1
            ? "won by 1 wicket"
            : `won by ${wicketsRemaining} wickets`,
      },
    };
  }

  if (second.runs < first.runs) {
    const byRuns = first.runs - second.wickets;
    return {
      lines,
      outcome: {
        kind: "win",
        winner: first.team,
        margin: byRuns === 1 ? "won by 1 run" : `won by ${byRuns} runs`,
      },
    };
  }

  return { lines, outcome: { kind: "tie" } };
}

/** True between overs: legal balls complete an over and innings is still live. */
export function isBowlerChangeRequired(innings: {
  status: string;
  legal_delivery_count?: number;
}): boolean {
  if (innings.status !== "IN_PROGRESS") return false;
  const legal = innings.legal_delivery_count ?? 0;
  return legal > 0 && legal % 6 === 0;
}

export function isEligibleBatter(player: Player): boolean {
  return player.batting_order != null && !player.roles.includes("Coach");
}

export function isEligibleBowler(player: Player): boolean {
  return player.roles.includes("Bowler");
}
