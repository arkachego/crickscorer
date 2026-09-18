import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it, beforeEach } from "vitest";
import {
  applyMatchLiveSnapshot,
  resetLiveVersionsForTests,
} from "@/lib/live/snapshot-cache";
import {
  deliveriesQueryKey,
  matchQueryKey,
  matchesQueryKey,
  teamPlayersQueryKey,
} from "@/hooks/use-match-lifecycle";
import type { Match, MatchLiveSnapshot } from "@/lib/api/types";

const matchId = "aaaaaaaa-aaaa-7aaa-8aaa-aaaaaaaaaaaa";
const inningsId = "cccccccc-cccc-7ccc-8ccc-cccccccccccc";
const otherInningsId = "dddddddd-dddd-7ddd-8ddd-dddddddddddd";

const india = {
  id: "11111111-1111-7111-8111-111111111111",
  name: "India",
  short_code: "IND",
  flag_url: "https://example.test/ind.svg",
};
const pakistan = {
  id: "22222222-2222-7222-8222-222222222222",
  name: "Pakistan",
  short_code: "PAK",
  flag_url: "https://example.test/pak.svg",
};

function matchAt(runs: number): Match {
  return {
    id: matchId,
    team_1: india,
    team_2: pakistan,
    batting_first_team: india,
    format: "T20",
    overs: 20,
    status: "IN_PROGRESS",
    created_at: "2026-09-18T12:00:00Z",
    innings: [
      {
        id: inningsId,
        innings_number: 1,
        batting_team: india,
        bowling_team: pakistan,
        status: "IN_PROGRESS",
        created_at: "2026-09-18T12:00:00Z",
        innings_total_runs: runs,
        legal_delivery_count: runs > 0 ? 1 : 0,
        delivery_count: runs > 0 ? 1 : 0,
        free_hit_pending: false,
        wickets: 0,
        replacement_required: false,
        dismissed_player_ids: [],
      },
    ],
  };
}

function snap(version: number, runs: number): MatchLiveSnapshot {
  return {
    match_id: matchId,
    version,
    match: matchAt(runs),
    deliveries_by_innings: {
      [inningsId]:
        runs > 0
          ? [
              {
                id: "d1",
                sequence_no: 1,
                over_number: 0,
                ball_in_over: 1,
                delivery_type: "NORMAL",
                bat_runs: runs,
                wide_runs: 0,
                no_ball_runs: 0,
                bye_runs: 0,
                leg_bye_runs: 0,
                total_runs: runs,
                is_legal: true,
                is_free_hit: false,
                striker: { id: "p1", name: "A" },
                non_striker: { id: "p2", name: "B" },
                bowler: { id: "p3", name: "C" },
                wicket: null,
              },
            ]
          : [],
    },
  };
}

describe("Admin cross-cache live synchronisation", () => {
  beforeEach(() => {
    resetLiveVersionsForTests();
  });

  it("applies the same snapshot to two Admin query clients (Admin A/B)", () => {
    const adminA = new QueryClient();
    const adminB = new QueryClient();
    const listSeed = [{ id: "list-only" }];
    const playersSeed = [{ id: "static-player" }];
    adminA.setQueryData(matchesQueryKey, listSeed);
    adminB.setQueryData(matchesQueryKey, listSeed);
    adminA.setQueryData(teamPlayersQueryKey(india.id), playersSeed);
    adminB.setQueryData(teamPlayersQueryKey(india.id), playersSeed);
    adminA.setQueryData(deliveriesQueryKey(otherInningsId), [{ id: "other" }]);

    const update = snap(1, 4);
    // Module-scoped version map is per JS heap (per browser tab). Resetting
    // between clients simulates Admin A and Admin B as separate processes.
    expect(applyMatchLiveSnapshot(adminA, update)).toBe(true);
    resetLiveVersionsForTests();
    expect(applyMatchLiveSnapshot(adminB, update)).toBe(true);

    expect(
      adminA.getQueryData<Match>(matchQueryKey(matchId))?.innings?.[0]
        .innings_total_runs,
    ).toBe(4);
    expect(
      adminB.getQueryData<Match>(matchQueryKey(matchId))?.innings?.[0]
        .innings_total_runs,
    ).toBe(4);
    expect(adminA.getQueryData(deliveriesQueryKey(inningsId))).toHaveLength(1);
    expect(adminB.getQueryData(deliveriesQueryKey(inningsId))).toHaveLength(1);

    // Live snapshots must not mutate list or static player caches.
    expect(adminA.getQueryData(matchesQueryKey)).toEqual(listSeed);
    expect(adminB.getQueryData(matchesQueryKey)).toEqual(listSeed);
    expect(adminA.getQueryData(teamPlayersQueryKey(india.id))).toEqual(playersSeed);
    expect(adminA.getQueryData(deliveriesQueryKey(otherInningsId))).toEqual([
      { id: "other" },
    ]);
  });

  it("undo-shaped snapshot replaces delivery history rather than appending", () => {
    const client = new QueryClient();
    applyMatchLiveSnapshot(client, snap(1, 4));
    applyMatchLiveSnapshot(client, {
      match_id: matchId,
      version: 2,
      match: matchAt(0),
      deliveries_by_innings: { [inningsId]: [] },
    });
    expect(client.getQueryData(deliveriesQueryKey(inningsId))).toEqual([]);
    expect(
      client.getQueryData<Match>(matchQueryKey(matchId))?.innings?.[0]
        .innings_total_runs,
    ).toBe(0);
  });
});
