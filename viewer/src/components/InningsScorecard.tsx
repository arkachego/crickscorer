import type {
  Innings,
  InningsScorecardData,
  PlayerBrief,
} from "@/lib/api/types";
import { cn } from "@/lib/utils";

const EMPTY_SCORECARD: InningsScorecardData = {
  batters: [],
  extras: { byes: 0, leg_byes: 0, wides: 0, noballs: 0, total: 0 },
  did_not_bat: [],
  bowlers: [],
  total_runs: 0,
  wickets: 0,
  overs_display: "0.0",
  run_rate: 0,
};

function formatSr(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

function formatEco(value: number): string {
  return value.toFixed(2);
}

function didNotBatLabel(players: PlayerBrief[]): string {
  return players.map((player) => player.name).join(", ");
}

export function InningsScorecard({
  innings,
  className,
}: {
  innings: Innings;
  className?: string;
}) {
  const scorecard = innings.scorecard ?? EMPTY_SCORECARD;
  const totalRuns = scorecard.total_runs || innings.innings_total_runs || 0;
  const wickets = scorecard.wickets || innings.wickets || 0;
  const overs = scorecard.overs_display;
  const strikerId = innings.striker?.id;
  const showStrikerMark = innings.status === "IN_PROGRESS";

  return (
    <div
      className={cn(
        "overflow-hidden rounded-xl border border-[var(--color-line)] bg-white/95 shadow-sm",
        className,
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2 bg-[var(--color-skyline)] px-4 py-3 text-white sm:px-5">
        <p className="text-sm font-semibold tracking-tight sm:text-base">
          {innings.batting_team.name}
        </p>
        <p className="text-sm font-semibold tabular-nums sm:text-base">
          {totalRuns}-{wickets} ({overs} Ov)
        </p>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[28rem] border-collapse text-sm">
          <thead>
            <tr className="border-b border-[var(--color-line)] bg-[var(--color-sand)] text-left text-xs uppercase tracking-wide text-[var(--color-muted)]">
              <th className="px-4 py-2 font-medium sm:px-5">Batter</th>
              <th className="px-2 py-2 text-right font-medium">R</th>
              <th className="px-2 py-2 text-right font-medium">B</th>
              <th className="px-2 py-2 text-right font-medium">4s</th>
              <th className="px-2 py-2 text-right font-medium">6s</th>
              <th className="px-4 py-2 text-right font-medium sm:px-5">SR</th>
            </tr>
          </thead>
          <tbody>
            {scorecard.batters.length === 0 ? (
              <tr>
                <td
                  colSpan={6}
                  className="px-4 py-4 text-[var(--color-muted)] sm:px-5"
                >
                  No batters yet.
                </td>
              </tr>
            ) : (
              scorecard.batters.map((row) => {
                const isStriker =
                  showStrikerMark && strikerId === row.player.id;
                return (
                  <tr
                    key={row.player.id}
                    className="border-b border-[var(--color-line)]"
                  >
                    <td className="px-4 py-2.5 sm:px-5">
                      <p
                        className={cn(
                          "font-medium text-[var(--color-skyline-deep)]",
                          isStriker && "font-semibold",
                        )}
                      >
                        {isStriker ? (
                          <span aria-hidden="true">★ </span>
                        ) : null}
                        {row.player.name}
                      </p>
                      <p className="text-xs text-[var(--color-muted)]">
                        {row.dismissal_text}
                      </p>
                    </td>
                    <td className="px-2 py-2.5 text-right font-semibold tabular-nums text-[var(--color-ink)]">
                      {row.runs}
                    </td>
                    <td className="px-2 py-2.5 text-right tabular-nums text-[var(--color-ink)]">
                      {row.balls}
                    </td>
                    <td className="px-2 py-2.5 text-right tabular-nums text-[var(--color-ink)]">
                      {row.fours}
                    </td>
                    <td className="px-2 py-2.5 text-right tabular-nums text-[var(--color-ink)]">
                      {row.sixes}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums text-[var(--color-ink)] sm:px-5">
                      {formatSr(row.strike_rate)}
                    </td>
                  </tr>
                );
              })
            )}
            <tr className="border-b border-[var(--color-line)]">
              <td
                className="px-4 py-2.5 text-[var(--color-ink)] sm:px-5"
                colSpan={1}
              >
                <span className="font-medium">Extras</span>
                <span className="ml-2 text-xs text-[var(--color-muted)]">
                  (b {scorecard.extras.byes}, lb {scorecard.extras.leg_byes}, w{" "}
                  {scorecard.extras.wides}, nb {scorecard.extras.noballs})
                </span>
              </td>
              <td
                className="px-2 py-2.5 text-right font-semibold tabular-nums"
                colSpan={5}
              >
                {scorecard.extras.total}
              </td>
            </tr>
            <tr className="border-b border-[var(--color-line)] bg-[var(--color-sand)]/60">
              <td className="px-4 py-2.5 font-semibold sm:px-5" colSpan={1}>
                Total
                <span className="ml-2 text-xs font-normal text-[var(--color-muted)]">
                  RR: {formatEco(scorecard.run_rate)}
                </span>
              </td>
              <td
                className="px-4 py-2.5 text-right font-semibold tabular-nums sm:px-5"
                colSpan={5}
              >
                {totalRuns}-{wickets} ({overs} Ov)
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      {scorecard.did_not_bat.length > 0 ? (
        <p className="border-b border-[var(--color-line)] px-4 py-3 text-sm text-[var(--color-muted)] sm:px-5">
          <span className="font-medium text-[var(--color-ink)]">Did not bat:</span>{" "}
          {didNotBatLabel(scorecard.did_not_bat)}
        </p>
      ) : null}

      <div className="overflow-x-auto">
        <table className="w-full min-w-[32rem] border-collapse text-sm">
          <thead>
            <tr className="border-b border-[var(--color-line)] bg-[var(--color-sand)] text-left text-xs uppercase tracking-wide text-[var(--color-muted)]">
              <th className="px-4 py-2 font-medium sm:px-5">Bowler</th>
              <th className="px-2 py-2 text-right font-medium">O</th>
              <th className="px-2 py-2 text-right font-medium">M</th>
              <th className="px-2 py-2 text-right font-medium">R</th>
              <th className="px-2 py-2 text-right font-medium">W</th>
              <th className="px-2 py-2 text-right font-medium">NB</th>
              <th className="px-2 py-2 text-right font-medium">WD</th>
              <th className="px-4 py-2 text-right font-medium sm:px-5">ECO</th>
            </tr>
          </thead>
          <tbody>
            {scorecard.bowlers.length === 0 ? (
              <tr>
                <td
                  colSpan={8}
                  className="px-4 py-4 text-[var(--color-muted)] sm:px-5"
                >
                  No bowlers yet.
                </td>
              </tr>
            ) : (
              scorecard.bowlers.map((row) => (
                <tr
                  key={row.player.id}
                  className="border-b border-[var(--color-line)] last:border-b-0"
                >
                  <td className="px-4 py-2.5 font-medium text-[var(--color-skyline-deep)] sm:px-5">
                    {row.player.name}
                  </td>
                  <td className="px-2 py-2.5 text-right tabular-nums">
                    {row.overs}
                  </td>
                  <td className="px-2 py-2.5 text-right tabular-nums">
                    {row.maidens}
                  </td>
                  <td className="px-2 py-2.5 text-right tabular-nums">
                    {row.runs}
                  </td>
                  <td className="px-2 py-2.5 text-right font-semibold tabular-nums">
                    {row.wickets}
                  </td>
                  <td className="px-2 py-2.5 text-right tabular-nums">
                    {row.noballs}
                  </td>
                  <td className="px-2 py-2.5 text-right tabular-nums">
                    {row.wides}
                  </td>
                  <td className="px-4 py-2.5 text-right tabular-nums sm:px-5">
                    {formatEco(row.economy)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
