export type MatchFormat = "T10" | "T20" | "ONE_DAY" | "CUSTOM" | "TEST";

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
  | "STUMPED"
  | "HIT_WICKET";

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

export interface DeliveryHistoryItem {
  id: string;
  sequence_no: number;
  over_number: number;
  ball_in_over: number;
  delivery_type: DeliveryType | string;
  bat_runs: number;
  wide_runs: number;
  no_ball_runs: number;
  bye_runs: number;
  leg_bye_runs: number;
  total_runs: number;
  is_legal: boolean;
  is_free_hit: boolean;
  striker: PlayerBrief;
  non_striker: PlayerBrief;
  bowler: PlayerBrief;
  wicket: {
    dismissed_player: PlayerBrief;
    dismissal_type: DismissalType | string;
  } | null;
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

/** Authoritative Socket.IO live snapshot (match:joined / match:update). */
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

