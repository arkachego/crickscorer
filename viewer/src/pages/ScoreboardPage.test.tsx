import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type {
  DeliveryHistoryItem,
  InningsScorecardData,
  Match,
} from "@/lib/api/types";
import { mockMatches, renderApp } from "@/test/test-utils";

const india = mockMatches[0].team_1;
const pakistan = mockMatches[0].team_2;
const matchId = mockMatches[0].id;
const inningsId = "cccccccc-cccc-7ccc-8ccc-cccccccccccc";

function emptyScorecard(
  overrides: Partial<InningsScorecardData> = {},
): InningsScorecardData {
  return {
    batters: [],
    extras: { byes: 0, leg_byes: 0, wides: 0, noballs: 0, total: 0 },
    did_not_bat: [],
    bowlers: [],
    total_runs: 0,
    wickets: 0,
    overs_display: "0.0",
    run_rate: 0,
    ...overrides,
  };
}

function jsonResponse(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function activeMatch(overrides: Partial<Match> = {}): Match {
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
        innings_total_runs: 42,
        legal_delivery_count: 44,
        delivery_count: 46,
        next_over_number: 7,
        next_ball_in_over: 3,
        free_hit_pending: false,
        wickets: 3,
        dismissed_player_ids: [],
        scorecard: emptyScorecard({
          total_runs: 42,
          wickets: 3,
          overs_display: "7.2",
          run_rate: 5.72,
          batters: [
            {
              player: { id: "p1", name: "Abhishek Sharma" },
              dismissal_text: "b Shaheen Afridi",
              is_not_out: false,
              runs: 24,
              balls: 18,
              fours: 3,
              sixes: 1,
              strike_rate: 133.33,
            },
            {
              player: { id: "p2", name: "Shubman Gill" },
              dismissal_text: "not out",
              is_not_out: true,
              runs: 15,
              balls: 20,
              fours: 1,
              sixes: 0,
              strike_rate: 75,
            },
          ],
          bowlers: [
            {
              player: { id: "b1", name: "Shaheen Afridi" },
              overs: "3.2",
              maidens: 0,
              runs: 22,
              wickets: 1,
              noballs: 0,
              wides: 1,
              economy: 6.6,
            },
          ],
          extras: { byes: 0, leg_byes: 1, wides: 1, noballs: 0, total: 2 },
        }),
      },
    ],
    ...overrides,
  };
}

const sampleDeliveries: DeliveryHistoryItem[] = [
  {
    id: "d1",
    sequence_no: 1,
    over_number: 7,
    ball_in_over: 1,
    delivery_type: "NORMAL",
    bat_runs: 1,
    wide_runs: 0,
    no_ball_runs: 0,
    bye_runs: 0,
    leg_bye_runs: 0,
    total_runs: 1,
    is_legal: true,
    is_free_hit: false,
    striker: { id: "p1", name: "Abhishek Sharma" },
    non_striker: { id: "p2", name: "Shubman Gill" },
    bowler: { id: "b1", name: "Shaheen Afridi" },
    wicket: null,
  },
  {
    id: "d2",
    sequence_no: 2,
    over_number: 7,
    ball_in_over: 1,
    delivery_type: "WIDE",
    bat_runs: 0,
    wide_runs: 1,
    no_ball_runs: 0,
    bye_runs: 0,
    leg_bye_runs: 0,
    total_runs: 1,
    is_legal: false,
    is_free_hit: false,
    striker: { id: "p1", name: "Abhishek Sharma" },
    non_striker: { id: "p2", name: "Shubman Gill" },
    bowler: { id: "b1", name: "Shaheen Afridi" },
    wicket: null,
  },
  {
    id: "d3",
    sequence_no: 3,
    over_number: 7,
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
    striker: { id: "p1", name: "Abhishek Sharma" },
    non_striker: { id: "p2", name: "Shubman Gill" },
    bowler: { id: "b1", name: "Shaheen Afridi" },
    wicket: {
      dismissed_player: { id: "p1", name: "Abhishek Sharma" },
      dismissal_type: "BOWLED",
    },
  },
];

function stubScoreboard(options: {
  match?: Match;
  deliveries?: DeliveryHistoryItem[];
}) {
  const match = options.match ?? activeMatch();
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (init?.method && init.method !== "GET") {
      throw new Error(`Unexpected mutation: ${init.method} ${url}`);
    }
    if (url.endsWith(`/api/v1/matches/${match.id}`)) {
      return jsonResponse(match);
    }
    if (url.includes("/deliveries")) {
      return jsonResponse(options.deliveries ?? sampleDeliveries);
    }
    throw new Error(`Unexpected fetch: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("Viewer scoreboard", () => {
  it("renders authoritative score, overs, scorecard, and Free Hit", async () => {
    stubScoreboard({
      match: activeMatch({
        innings: [
          {
            ...activeMatch().innings![0],
            free_hit_pending: true,
          },
        ],
      }),
    });
    renderApp(`/matches/${matchId}/scoreboard`);

    expect(
      await screen.findByRole("heading", { name: /india vs pakistan/i }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/score 42 for 3/i)).toHaveTextContent("42/3");
    expect(screen.getByText(/7\.2 overs/i)).toBeInTheDocument();
    expect(screen.getByText(/abhishek sharma/i)).toBeInTheDocument();
    expect(screen.getByText(/shubman gill/i)).toBeInTheDocument();
    expect(screen.getByRole("status", { name: /free hit/i })).toBeInTheDocument();
    expect(screen.getAllByRole("columnheader", { name: /^r$/i }).length).toBe(2);
    expect(screen.getByRole("columnheader", { name: /^eco$/i })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /^batters$/i })).not.toBeInTheDocument();
    expect(screen.getAllByText(/shaheen afridi/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/^b shaheen afridi$/i)).toBeInTheDocument();
  });

  it("formats recent deliveries including wides and wickets", async () => {
    stubScoreboard({});
    renderApp(`/matches/${matchId}/scoreboard`);

    const list = await screen.findByRole("list", { name: /recent deliveries/i });
    const items = within(list).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent(/W/);
    expect(items[0]).toHaveTextContent(/Abhishek Sharma/);
    expect(items[1]).toHaveTextContent(/Wd/);
    expect(items[2]).toHaveTextContent(/1/);
  });

  it("shows created match pre-start state without deliveries fetch", async () => {
    const fetchMock = stubScoreboard({ match: mockMatches[0] });
    renderApp(`/matches/${matchId}/scoreboard`);
    expect(await screen.findByText(/match not started/i)).toBeInTheDocument();
    expect(fetchMock.mock.calls.every((call) => !String(call[0]).includes("/deliveries"))).toBe(
      true,
    );
  });

  it("shows innings break and completed states", async () => {
    stubScoreboard({
      match: activeMatch({
        status: "INNINGS_BREAK",
        innings: [
          {
            ...activeMatch().innings![0],
            status: "COMPLETED",
            free_hit_pending: false,
          },
        ],
      }),
    });
    const breakView = renderApp(`/matches/${matchId}/scoreboard`);
    expect(
      await screen.findByRole("status", { name: /innings break/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/end of innings/i)).toBeInTheDocument();
    breakView.unmount();

    stubScoreboard({
      match: activeMatch({
        status: "COMPLETED",
        overs: 2,
        innings: [
          {
            id: "cccccccc-cccc-7ccc-8ccc-cccccccccc01",
            innings_number: 1,
            batting_team: india,
            bowling_team: pakistan,
            status: "COMPLETED",
            created_at: "2026-09-18T12:05:00Z",
            striker: null,
            non_striker: null,
            replacement_required: false,
            innings_total_runs: 39,
            legal_delivery_count: 12,
            delivery_count: 12,
            free_hit_pending: false,
            wickets: 2,
            dismissed_player_ids: [],
            target: null,
            scorecard: emptyScorecard({
              total_runs: 39,
              wickets: 2,
              overs_display: "2.0",
              run_rate: 19.5,
            }),
          },
          {
            ...activeMatch().innings![0],
            status: "COMPLETED",
            innings_number: 2,
            batting_team: pakistan,
            bowling_team: india,
            innings_total_runs: 8,
            legal_delivery_count: 12,
            delivery_count: 12,
            wickets: 1,
            target: 40,
            free_hit_pending: false,
            scorecard: emptyScorecard({
              total_runs: 8,
              wickets: 1,
              overs_display: "2.0",
              run_rate: 4,
            }),
          },
        ],
      }),
    });
    renderApp(`/matches/${matchId}/scoreboard`);
    expect(
      await screen.findByRole("region", { name: /match result summary/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/won by 31 runs/i)).toBeInTheDocument();
    expect(screen.queryByText(/winner calculation/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/need 32 from 0 balls/i)).not.toBeInTheDocument();
  });

  it("is reachable from match detail and remains read-only", async () => {
    const user = userEvent.setup();
    const match = activeMatch();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (init?.method && init.method !== "GET") {
        throw new Error(`Mutation not allowed: ${init.method}`);
      }
      if (url.endsWith(`/api/v1/matches/${match.id}`)) return jsonResponse(match);
      if (url.includes("/deliveries")) return jsonResponse(sampleDeliveries);
      throw new Error(url);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderApp(`/matches/${matchId}`);
    const link = await screen.findByRole("link", { name: /view scoreboard/i });
    expect(link).toHaveAttribute("href", `/matches/${matchId}/scoreboard`);
    await user.click(link);
    expect(await screen.findByLabelText(/score 42 for 3/i)).toBeInTheDocument();

    expect(
      fetchMock.mock.calls.every((call) => {
        const init = call[1] as RequestInit | undefined;
        return !init?.method || init.method === "GET";
      }),
    ).toBe(true);
  });

  it("handles scoreboard 404 and does not poll", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(
        { detail: { code: "MATCH_NOT_FOUND", message: "Match was not found." } },
        404,
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    renderApp(`/matches/${matchId}/scoreboard`);
    expect(await screen.findByText(/match not found/i)).toBeInTheDocument();
    const callsAfterLoad = fetchMock.mock.calls.length;
    await new Promise((resolve) => setTimeout(resolve, 150));
    expect(fetchMock.mock.calls.length).toBe(callsAfterLoad);
  });

  it("deep-links directly to the scoreboard route", async () => {
    stubScoreboard({});
    renderApp(`/matches/${matchId}/scoreboard`);
    await waitFor(() => {
      expect(screen.getByRole("region", { name: /match scoreboard/i })).toBeInTheDocument();
    });
  });

  it("shows chase target and required rate in the second innings", async () => {
    stubScoreboard({
      match: activeMatch({
        overs: 2,
        innings: [
          {
            id: "cccccccc-cccc-7ccc-8ccc-cccccccccc01",
            innings_number: 1,
            batting_team: india,
            bowling_team: pakistan,
            status: "COMPLETED",
            created_at: "2026-09-18T12:05:00Z",
            striker: null,
            non_striker: null,
            replacement_required: false,
            innings_total_runs: 15,
            legal_delivery_count: 12,
            delivery_count: 12,
            free_hit_pending: false,
            wickets: 2,
            dismissed_player_ids: [],
            target: null,
          },
          {
            ...activeMatch().innings![0],
            innings_number: 2,
            batting_team: pakistan,
            bowling_team: india,
            innings_total_runs: 2,
            legal_delivery_count: 5,
            delivery_count: 5,
            wickets: 0,
            target: 16,
            free_hit_pending: false,
            scorecard: emptyScorecard({
              total_runs: 2,
              wickets: 0,
              overs_display: "0.5",
            }),
          },
        ],
      }),
    });
    renderApp(`/matches/${matchId}/scoreboard`);

    expect(
      await screen.findByRole("status", {
        name: /target 16, need 14 runs from 7 balls/i,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText(/^target$/i)).toBeInTheDocument();
    expect(screen.getByText("16")).toBeInTheDocument();
    expect(screen.getByText(/need/i)).toHaveTextContent(/14/);
    expect(screen.getByText(/from/i).closest("p")).toHaveTextContent(/7/);
    expect(screen.getByText(/rrr/i).closest("p")).toHaveTextContent(/12\.00/);
  });
});
