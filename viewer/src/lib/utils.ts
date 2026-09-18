import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatLabel(format: string): string {
  if (format === "ONE_DAY") return "One Day";
  if (format === "CUSTOM") return "Custom";
  return format;
}

export function statusLabel(status: string): string {
  return status.replaceAll("_", " ");
}

/** Format legal balls as cricket overs display (e.g. 44 → "7.2"). */
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
  const runsNeeded = Math.max(0, input.target - input.runs - 1);
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
    const byRuns = first.runs - second.runs;
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

export function formatDeliveryOutcome(delivery: {
  delivery_type: string;
  bat_runs: number;
  wide_runs: number;
  no_ball_runs: number;
  bye_runs: number;
  leg_bye_runs: number;
  total_runs: number;
  wicket: { dismissed_player: { name: string } } | null;
}): string {
  if (delivery.wicket) {
    return "W";
  }
  switch (delivery.delivery_type) {
    case "WIDE":
      return delivery.wide_runs <= 1 ? "Wd" : `Wd ${delivery.wide_runs}`;
    case "NO_BALL":
      return delivery.bat_runs > 0 ? `Nb ${delivery.bat_runs}` : "Nb";
    case "BYE":
      return `B ${delivery.bye_runs}`;
    case "LEG_BYE":
      return `LB ${delivery.leg_bye_runs}`;
    default:
      return String(delivery.total_runs);
  }
}
