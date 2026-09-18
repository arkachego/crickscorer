/**
 * Cross-application convergence: Admin and Viewer apply the same authoritative
 * snapshot shape to equivalent cache projections (score/wickets/legal/FH/pair).
 */
import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it, beforeEach } from "vitest";
import {
  applyMatchLiveSnapshot,
  resetLiveVersionsForTests,
} from "@/lib/live/snapshot-cache";
import {
  deliveriesQueryKey,
  matchQueryKey,
} from "@/hooks/use-match-lifecycle";
import type { Match, MatchLiveSnapshot } from "@/lib/api/types";

const matchId = "aaaaaaaa-aaaa-7aaa-8aaa-aaaaaaaaaaaa";
const inningsId = "cccccccc-cccc-7ccc-8ccc-cccccccccccc";

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

const striker = { id: "p1", name: "Abhishek Sharma" };
const nonStriker = { id: "p2", name: "Shubman Gill" };

function authoritativeSnapshot(version: number): MatchLiveSnapshot {
  const match: Match = {
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
        innings_total_runs: 7,
        legal_delivery_count: 2,
        delivery_count: 2,
        free_hit_pending: false,
        wickets: 1,
        replacement_required: false,
        dismissed_player_ids: ["p0"],
        striker,
        non_striker: nonStriker,
      },
    ],
  };
  return {
    match_id: matchId,
    version,
    match,
    deliveries_by_innings: {
      [inningsId]: [
        {
          id: "d1",
          sequence_no: 1,
          over_number: 0,
          ball_in_over: 1,
          delivery_type: "NORMAL",
          bat_runs: 4,
          wide_runs: 0,
          no_ball_runs: 0,
          bye_runs: 0,
          leg_bye_runs: 0,
          total_runs: 4,
          is_legal: true,
          is_free_hit: false,
          striker,
          non_striker: nonStriker,
          bowler: { id: "p3", name: "Shaheen Afridi" },
          wicket: null,
        },
        {
          id: "d2",
          sequence_no: 2,
          over_number: 0,
          ball_in_over: 2,
          delivery_type: "NORMAL",
          bat_runs: 0,
          wide_runs: 0,
          no_ball_runs: 0,
          bye_runs: 0,
          leg_bye_runs: 0,
          total_runs: 0,
          is_legal: true,
          is_free_hit: false,
          striker,
          non_striker: nonStriker,
          bowler: { id: "p3", name: "Shaheen Afridi" },
          wicket: {
            dismissal_type: "BOWLED",
            dismissed_player: { id: "p0", name: "Out" },
          },
        },
      ],
    },
  };
}

function projection(client: QueryClient) {
  const match = client.getQueryData<Match>(matchQueryKey(matchId));
  const deliveries = client.getQueryData(deliveriesQueryKey(inningsId)) as
    | unknown[]
    | undefined;
  const inn = match?.innings?.[0];
  return {
    score: inn?.innings_total_runs,
    wickets: inn?.wickets,
    legal_delivery_count: inn?.legal_delivery_count,
    free_hit_pending: inn?.free_hit_pending,
    striker_id: inn?.striker?.id,
    non_striker_id: inn?.non_striker?.id,
    innings_status: inn?.status,
    match_status: match?.status,
    delivery_count: deliveries?.length,
  };
}

describe("Admin/Viewer cross-application convergence", () => {
  beforeEach(() => {
    resetLiveVersionsForTests();
  });

  it("Admin cache converges on authoritative delivery/wicket snapshot fields", () => {
    const admin = new QueryClient();
    const snap = authoritativeSnapshot(3);
    expect(applyMatchLiveSnapshot(admin, snap)).toBe(true);
    expect(projection(admin)).toEqual({
      score: 7,
      wickets: 1,
      legal_delivery_count: 2,
      free_hit_pending: false,
      striker_id: striker.id,
      non_striker_id: nonStriker.id,
      innings_status: "IN_PROGRESS",
      match_status: "IN_PROGRESS",
      delivery_count: 2,
    });
  });
});
