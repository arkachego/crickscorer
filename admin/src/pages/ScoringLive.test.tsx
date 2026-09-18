import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ScoringPage } from "@/pages/ScoringPage";
import {
  applyMatchLiveSnapshot,
  getAppliedLiveVersion,
  resetLiveVersionsForTests,
  resolveMatchAgainstLiveCache,
} from "@/lib/live/snapshot-cache";
import {
  deliveriesQueryKey,
  matchQueryKey,
} from "@/hooks/use-match-lifecycle";
import type { Match, MatchLiveSnapshot, Player } from "@/lib/api/types";
import { io } from "socket.io-client";

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

const inningsId = "cccccccc-cccc-7ccc-8ccc-cccccccccccc";
const matchId = "aaaaaaaa-aaaa-7aaa-8aaa-aaaaaaaaaaaa";
const otherMatchId = "bbbbbbbb-bbbb-7bbb-8bbb-bbbbbbbbbbbb";

const striker: Player = {
  id: "b1111111-1111-7111-8111-111111111111",
  team_id: india.id,
  name: "Abhishek Sharma",
  batting_order: 1,
  roles: ["Batsman"],
};
const nonStriker: Player = {
  id: "b2222222-2222-7222-8222-222222222222",
  team_id: india.id,
  name: "Shubman Gill",
  batting_order: 2,
  roles: ["Batsman"],
};
const pakBowler: Player = {
  id: "b5555555-5555-7555-8555-555555555555",
  team_id: pakistan.id,
  name: "Shaheen Afridi",
  batting_order: 9,
  roles: ["Bowler"],
};

function baseMatch(runs = 0): Match {
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
        striker: { id: striker.id, name: striker.name },
        non_striker: { id: nonStriker.id, name: nonStriker.name },
        replacement_required: false,
        innings_total_runs: runs,
        legal_delivery_count: runs > 0 ? 1 : 0,
        delivery_count: runs > 0 ? 1 : 0,
        next_over_number: 0,
        next_ball_in_over: runs > 0 ? 2 : 1,
        free_hit_pending: false,
        wickets: 0,
        dismissed_player_ids: [],
      },
    ],
  };
}

function snapshot(
  version: number,
  runs: number,
  id = matchId,
): MatchLiveSnapshot {
  const match = { ...baseMatch(runs), id };
  return {
    match_id: id,
    version,
    match,
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
                striker: { id: striker.id, name: striker.name },
                non_striker: { id: nonStriker.id, name: nonStriker.name },
                bowler: { id: pakBowler.id, name: pakBowler.name },
                wicket: null,
              },
            ]
          : [],
    },
  };
}

function jsonResponse(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderScoring() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[`/matches/${matchId}/scoring`]}>
          {children}
        </MemoryRouter>
      </QueryClientProvider>
    );
  }
  return {
    queryClient,
    ...render(
      <Routes>
        <Route path="/matches/:matchId/scoring" element={<ScoringPage />} />
      </Routes>,
      { wrapper: Wrapper },
    ),
  };
}

describe("Admin live Socket.IO sync", () => {
  beforeEach(() => {
    resetLiveVersionsForTests();
    vi.mocked(io).mockClear();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith(`/api/v1/matches/${matchId}`)) {
          return jsonResponse(baseMatch());
        }
        if (url.includes("/players")) {
          return jsonResponse([striker, nonStriker, pakBowler]);
        }
        if (url.includes("/deliveries")) {
          return jsonResponse([]);
        }
        throw new Error(url);
      }),
    );
  });

  it("connects Socket.IO and emits match:join", async () => {
    renderScoring();
    await screen.findByRole("heading", { name: /india vs pakistan/i });
    expect(io).toHaveBeenCalled();
    const socket = vi.mocked(io).mock.results[0]?.value as {
      emit: ReturnType<typeof vi.fn>;
    };
    await waitFor(() => {
      expect(socket.emit).toHaveBeenCalledWith("match:join", {
        match_id: matchId,
      });
    });
    expect(screen.getByLabelText(/connection/i)).toBeInTheDocument();
  });

  it("applies newer match:update snapshot to score and deliveries", async () => {
    const { queryClient } = renderScoring();
    await screen.findByText("0/0");

    applyMatchLiveSnapshot(queryClient, snapshot(1, 4));
    await waitFor(() => {
      expect(screen.getByText("4/0")).toBeInTheDocument();
    });
    expect(getAppliedLiveVersion(matchId)).toBe(1);
    expect(queryClient.getQueryData(deliveriesQueryKey(inningsId))).toHaveLength(
      1,
    );
  });

  it("ignores stale older versions", () => {
    const queryClient = new QueryClient();
    expect(applyMatchLiveSnapshot(queryClient, snapshot(5, 50))).toBe(true);
    expect(applyMatchLiveSnapshot(queryClient, snapshot(4, 40))).toBe(false);
    expect(
      queryClient.getQueryData<Match>(matchQueryKey(matchId))?.innings?.[0]
        .innings_total_runs,
    ).toBe(50);
  });

  it("force-applies joined snapshot after version reset (server restart)", () => {
    const queryClient = new QueryClient();
    expect(applyMatchLiveSnapshot(queryClient, snapshot(8, 80))).toBe(true);
    expect(
      applyMatchLiveSnapshot(queryClient, snapshot(0, 10), { force: true }),
    ).toBe(true);
    expect(getAppliedLiveVersion(matchId)).toBe(0);
    expect(applyMatchLiveSnapshot(queryClient, snapshot(1, 11))).toBe(true);
    expect(
      queryClient.getQueryData<Match>(matchQueryKey(matchId))?.innings?.[0]
        .innings_total_runs,
    ).toBe(11);
  });

  it("ignores wrong match_id snapshots", () => {
    const queryClient = new QueryClient();
    applyMatchLiveSnapshot(queryClient, snapshot(1, 10));
    expect(
      applyMatchLiveSnapshot(queryClient, snapshot(2, 99, otherMatchId)),
    ).toBe(true);
    expect(
      queryClient.getQueryData<Match>(matchQueryKey(matchId))?.innings?.[0]
        .innings_total_runs,
    ).toBe(10);
  });

  it("does not let late REST overwrite a newer live snapshot", () => {
    const queryClient = new QueryClient();
    applyMatchLiveSnapshot(queryClient, snapshot(3, 42));
    const resolved = resolveMatchAgainstLiveCache(
      queryClient,
      matchId,
      baseMatch(0),
    );
    expect(resolved.innings?.[0].innings_total_runs).toBe(42);
  });

  it("disconnects and cleans up on unmount", async () => {
    const { unmount } = renderScoring();
    await screen.findByRole("heading", { name: /india vs pakistan/i });
    const socket = vi.mocked(io).mock.results[0]?.value as {
      disconnect: ReturnType<typeof vi.fn>;
      removeAllListeners: ReturnType<typeof vi.fn>;
    };
    unmount();
    expect(socket.removeAllListeners).toHaveBeenCalled();
    expect(socket.disconnect).toHaveBeenCalled();
  });

  it("does not create polling timers for live sync", async () => {
    const setIntervalSpy = vi.spyOn(window, "setInterval");
    renderScoring();
    await screen.findByRole("heading", { name: /india vs pakistan/i });
    const pollingCalls = setIntervalSpy.mock.calls.filter(
      (call) => typeof call[1] === "number" && (call[1] as number) >= 1000,
    );
    expect(pollingCalls).toHaveLength(0);
    setIntervalSpy.mockRestore();
  });
});
