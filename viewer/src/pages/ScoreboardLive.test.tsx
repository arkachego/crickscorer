import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ScoreboardPage } from "@/pages/ScoreboardPage";
import {
  applyMatchLiveSnapshot,
  getAppliedLiveVersion,
  resetLiveVersionsForTests,
  resolveMatchAgainstLiveCache,
} from "@/lib/live/snapshot-cache";
import { deliveriesQueryKey, matchQueryKey } from "@/lib/query-keys";
import type { Match, MatchLiveSnapshot } from "@/lib/api/types";
import { mockMatches } from "@/test/test-utils";
import { io } from "socket.io-client";

const matchId = mockMatches[0].id;
const inningsId = "cccccccc-cccc-7ccc-8ccc-cccccccccccc";
const india = mockMatches[0].team_1;
const pakistan = mockMatches[0].team_2;

function activeMatch(runs = 10): Match {
  return {
    ...mockMatches[0],
    status: "IN_PROGRESS",
    innings: [
      {
        id: inningsId,
        innings_number: 1,
        batting_team: india,
        bowling_team: pakistan,
        status: "IN_PROGRESS",
        created_at: "2026-09-18T12:05:00Z",
        striker: { id: "p1", name: "Abhishek Sharma" },
        non_striker: { id: "p2", name: "Shubman Gill" },
        replacement_required: false,
        innings_total_runs: runs,
        legal_delivery_count: 6,
        delivery_count: 6,
        free_hit_pending: false,
        wickets: 0,
        dismissed_player_ids: [],
      },
    ],
  };
}

function snapshot(version: number, runs: number): MatchLiveSnapshot {
  const match = activeMatch(runs);
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
          bat_runs: runs,
          wide_runs: 0,
          no_ball_runs: 0,
          bye_runs: 0,
          leg_bye_runs: 0,
          total_runs: runs,
          is_legal: true,
          is_free_hit: false,
          striker: { id: "p1", name: "Abhishek Sharma" },
          non_striker: { id: "p2", name: "Shubman Gill" },
          bowler: { id: "b1", name: "Shaheen Afridi" },
          wicket: null,
        },
      ],
    },
  };
}

function jsonResponse(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderScoreboard() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[`/matches/${matchId}/scoreboard`]}>
          {children}
        </MemoryRouter>
      </QueryClientProvider>
    );
  }
  return {
    queryClient,
    ...render(
      <Routes>
        <Route path="/matches/:matchId/scoreboard" element={<ScoreboardPage />} />
      </Routes>,
      { wrapper: Wrapper },
    ),
  };
}

describe("Viewer live Socket.IO sync", () => {
  beforeEach(() => {
    resetLiveVersionsForTests();
    vi.mocked(io).mockClear();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith(`/api/v1/matches/${matchId}`)) {
          return jsonResponse(activeMatch());
        }
        if (url.includes("/deliveries")) {
          return jsonResponse([]);
        }
        throw new Error(url);
      }),
    );
  });

  it("applies match:update snapshot to score and deliveries cache", async () => {
    const { queryClient } = renderScoreboard();
    expect(await screen.findByLabelText(/score 10 for 0/i)).toBeInTheDocument();

    applyMatchLiveSnapshot(queryClient, snapshot(1, 42));
    await waitFor(() => {
      expect(screen.getByLabelText(/score 42 for 0/i)).toBeInTheDocument();
    });
    expect(getAppliedLiveVersion(matchId)).toBe(1);
    expect(queryClient.getQueryData(deliveriesQueryKey(inningsId))).toHaveLength(1);
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

  it("ignores wrong match_id snapshots for the active board", () => {
    const queryClient = new QueryClient();
    applyMatchLiveSnapshot(queryClient, snapshot(1, 10));
    const other: MatchLiveSnapshot = {
      ...snapshot(2, 99),
      match_id: "bbbbbbbb-bbbb-7bbb-8bbb-bbbbbbbbbbbb",
      match: { ...activeMatch(99), id: "bbbbbbbb-bbbb-7bbb-8bbb-bbbbbbbbbbbb" },
    };
    expect(applyMatchLiveSnapshot(queryClient, other)).toBe(true);
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
      activeMatch(0),
    );
    expect(resolved.innings?.[0].innings_total_runs).toBe(42);
  });

  it("disconnects and cleans up on unmount", async () => {
    const { unmount } = renderScoreboard();
    await screen.findByRole("heading", { name: /india vs pakistan/i });
    const socket = vi.mocked(io).mock.results[0]?.value as {
      disconnect: ReturnType<typeof vi.fn>;
      removeAllListeners: ReturnType<typeof vi.fn>;
    };
    unmount();
    expect(socket.removeAllListeners).toHaveBeenCalled();
    expect(socket.disconnect).toHaveBeenCalled();
  });

  it("connects Socket.IO and emits match:join", async () => {
    renderScoreboard();
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

  it("does not create polling timers for live sync", async () => {
    const setIntervalSpy = vi.spyOn(window, "setInterval");
    renderScoreboard();
    await screen.findByRole("heading", { name: /india vs pakistan/i });
    const pollingCalls = setIntervalSpy.mock.calls.filter(
      (call) => typeof call[1] === "number" && (call[1] as number) >= 1000,
    );
    expect(pollingCalls).toHaveLength(0);
    setIntervalSpy.mockRestore();
  });
});
