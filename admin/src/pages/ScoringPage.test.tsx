import { screen, waitFor } from "@testing-library/react";
import { chooseSelectOption, openSelect } from "@/test/test-utils";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ScoringPage } from "@/pages/ScoringPage";
import type {
  DeliveryHistoryItem,
  InningsScorecardData,
  Match,
  Player,
} from "@/lib/api/types";

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
const bowlerOnly: Player = {
  id: "b3333333-3333-7333-8333-333333333333",
  team_id: india.id,
  name: "Jasprit Bumrah",
  batting_order: 10,
  roles: ["Bowler"],
};
const coach: Player = {
  id: "b4444444-4444-7444-8444-444444444444",
  team_id: india.id,
  name: "Gautam Gambhir",
  batting_order: null,
  roles: ["Coach"],
};
const pakBowler: Player = {
  id: "b5555555-5555-7555-8555-555555555555",
  team_id: pakistan.id,
  name: "Shaheen Afridi",
  batting_order: 9,
  roles: ["Bowler"],
};
const replacement: Player = {
  id: "b6666666-6666-7666-8666-666666666666",
  team_id: india.id,
  name: "Suryakumar Yadav",
  batting_order: 3,
  roles: ["Batsman"],
};

function baseMatch(overrides: Partial<Match> = {}): Match {
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
        striker: null,
        non_striker: null,
        replacement_required: false,
        innings_total_runs: 0,
        legal_delivery_count: 0,
        delivery_count: 0,
        next_over_number: 0,
        next_ball_in_over: 1,
        free_hit_pending: false,
        wickets: 0,
        dismissed_player_ids: [],
        scorecard: emptyScorecard(),
      },
    ],
    ...overrides,
  };
}

function renderScoring(route = `/matches/${matchId}/scoring`) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  }
  return render(
    <Routes>
      <Route path="/matches/:matchId/scoring" element={<ScoringPage />} />
    </Routes>,
    { wrapper: Wrapper },
  );
}

function json(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function stubApis(options: {
  match?: Match;
  deliveries?: DeliveryHistoryItem[];
  onDelivery?: (body: unknown) => Response | Promise<Response>;
  onReplacement?: (body: unknown) => Response | Promise<Response>;
  onUndo?: () => Response | Promise<Response>;
}) {
  const match = options.match ?? baseMatch();
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith(`/api/v1/matches/${matchId}`)) return json(match);
    if (url.endsWith(`/api/v1/teams/${india.id}/players`)) {
      return json([striker, nonStriker, bowlerOnly, coach, replacement]);
    }
    if (url.endsWith(`/api/v1/teams/${pakistan.id}/players`)) {
      return json([pakBowler]);
    }
    if (url.endsWith(`/api/v1/innings/${inningsId}/deliveries`)) {
      if (init?.method === "POST") {
        const body = JSON.parse(String(init.body));
        if (options.onDelivery) return options.onDelivery(body);
        return json({
          id: "dddddddd-dddd-7ddd-8ddd-dddddddddddd",
          innings_id: inningsId,
          sequence_no: 1,
          over_number: 0,
          ball_in_over: 1,
          striker: { id: striker.id, name: striker.name },
          non_striker: { id: nonStriker.id, name: nonStriker.name },
          bowler: { id: pakBowler.id, name: pakBowler.name },
          delivery_type: body.delivery_type,
          bat_runs: body.bat_runs ?? 0,
          wide_runs: 0,
          no_ball_runs: 0,
          bye_runs: 0,
          leg_bye_runs: 0,
          total_runs: body.bat_runs ?? body.extra_runs ?? 0,
          is_legal: body.delivery_type === "NORMAL",
          is_free_hit: false,
          wicket: null,
          innings_status: "IN_PROGRESS",
          match_status: "IN_PROGRESS",
          innings_total_runs: body.bat_runs ?? 0,
          replacement_required: false,
        });
      }
      return json(options.deliveries ?? []);
    }
    if (url.endsWith(`/api/v1/innings/${inningsId}/replacement`)) {
      const body = JSON.parse(String(init?.body));
      if (options.onReplacement) return options.onReplacement(body);
      return json(match);
    }
    if (url.endsWith(`/api/v1/innings/${inningsId}/undo`)) {
      if (options.onUndo) return options.onUndo();
      return json({
        match,
        innings_id: inningsId,
        delivery_count: 0,
        legal_delivery_count: 0,
        innings_total_runs: 0,
        next_over_number: 0,
        next_ball_in_over: 1,
        free_hit_pending: false,
        replacement_required: false,
        innings_status: "IN_PROGRESS",
        match_status: "IN_PROGRESS",
        striker: null,
        non_striker: null,
      });
    }
    throw new Error(url);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function selectPlayers(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByLabelText(/^striker$/i);
  await chooseSelectOption(user, /^striker$/i, /abhishek sharma/i);
  await chooseSelectOption(user, /^non-striker$/i, /shubman gill/i);
  await chooseSelectOption(user, /^bowler$/i, /shaheen afridi/i);
}

describe("Admin scoring UI", () => {
  it("renders match/innings state and filters player selectors before scoring", async () => {
    stubApis({});
    renderScoring();

    const user = userEvent.setup();
    expect(
      await screen.findByRole("heading", { name: /india vs pakistan/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/select the opening pair and first bowler/i),
    ).toBeInTheDocument();

    await openSelect(user, /^striker$/i);
    const options = screen.getAllByRole("option").map((o) => o.textContent);
    expect(options.some((text) => text?.includes("Gautam Gambhir"))).toBe(false);
    expect(options.some((text) => text?.includes("Jasprit Bumrah"))).toBe(true);

    await user.keyboard("{Escape}");
    await openSelect(user, /^bowler$/i);
    const bowlerOptions = screen.getAllByRole("option").map((o) => o.textContent);
    expect(bowlerOptions.some((text) => text?.includes("Shaheen Afridi"))).toBe(true);
  });

  it("locks active players after scoring has started", async () => {
    stubApis({
      match: baseMatch({
        innings: [
          {
            ...baseMatch().innings![0],
            striker: { id: striker.id, name: striker.name },
            non_striker: { id: nonStriker.id, name: nonStriker.name },
            innings_total_runs: 42,
            wickets: 3,
            legal_delivery_count: 44,
            delivery_count: 48,
            free_hit_pending: false,
            scorecard: emptyScorecard({
              total_runs: 42,
              wickets: 3,
              overs_display: "7.2",
              run_rate: 5.72,
              batters: [
                {
                  player: { id: striker.id, name: striker.name },
                  dismissal_text: "b Shaheen Afridi",
                  is_not_out: false,
                  runs: 20,
                  balls: 15,
                  fours: 2,
                  sixes: 1,
                  strike_rate: 133.33,
                },
                {
                  player: { id: nonStriker.id, name: nonStriker.name },
                  dismissal_text: "not out",
                  is_not_out: true,
                  runs: 18,
                  balls: 20,
                  fours: 1,
                  sixes: 0,
                  strike_rate: 90,
                },
              ],
              bowlers: [
                {
                  player: { id: pakBowler.id, name: pakBowler.name },
                  overs: "3.2",
                  maidens: 0,
                  runs: 28,
                  wickets: 1,
                  noballs: 0,
                  wides: 2,
                  economy: 8.4,
                },
              ],
              extras: { byes: 1, leg_byes: 0, wides: 2, noballs: 0, total: 3 },
            }),
          },
        ],
      }),
    });
    renderScoring();

    expect(
      await screen.findByRole("heading", { name: /india vs pakistan/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("42/3")).toBeInTheDocument();
    expect(
      screen.getByText(/locked after scoring starts/i),
    ).toBeInTheDocument();

    expect(screen.getByLabelText(/^striker$/i)).toBeDisabled();
    expect(screen.getByLabelText(/^non-striker$/i)).toBeDisabled();
    expect(screen.getByLabelText(/^bowler$/i)).toBeDisabled();

    expect(screen.getAllByText(/42-3 \(7\.2 Ov\)/i).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("columnheader", { name: /^r$/i }).length).toBe(2);
    expect(screen.getByText(pakBowler.name)).toBeInTheDocument();
    expect(screen.getByText(/b shaheen afridi/i)).toBeInTheDocument();
  });

  it("submits normal runs with the correct payload", async () => {
    const user = userEvent.setup();
    let captured: unknown;
    stubApis({
      onDelivery: (body) => {
        captured = body;
        return json({
          id: "dddddddd-dddd-7ddd-8ddd-dddddddddddd",
          innings_id: inningsId,
          sequence_no: 1,
          over_number: 0,
          ball_in_over: 1,
          striker: { id: striker.id, name: striker.name },
          non_striker: { id: nonStriker.id, name: nonStriker.name },
          bowler: { id: pakBowler.id, name: pakBowler.name },
          delivery_type: "NORMAL",
          bat_runs: 4,
          wide_runs: 0,
          no_ball_runs: 0,
          bye_runs: 0,
          leg_bye_runs: 0,
          total_runs: 4,
          is_legal: true,
          is_free_hit: false,
          wicket: null,
          innings_status: "IN_PROGRESS",
          match_status: "IN_PROGRESS",
          innings_total_runs: 4,
          replacement_required: false,
        });
      },
    });
    renderScoring();
    await selectPlayers(user);
    await user.click(screen.getByRole("button", { name: /score 4 runs/i }));

    await waitFor(() => {
      expect(captured).toEqual({
        striker_id: striker.id,
        non_striker_id: nonStriker.id,
        bowler_id: pakBowler.id,
        delivery_type: "NORMAL",
        bat_runs: 4,
      });
    });
  });

  it("submits wide extras with delivery_type WIDE", async () => {
    const user = userEvent.setup();
    let captured: unknown;
    stubApis({
      onDelivery: (body) => {
        captured = body;
        return json({
          id: "dddddddd-dddd-7ddd-8ddd-dddddddddddd",
          innings_id: inningsId,
          sequence_no: 1,
          over_number: 0,
          ball_in_over: 1,
          striker: { id: striker.id, name: striker.name },
          non_striker: { id: nonStriker.id, name: nonStriker.name },
          bowler: { id: pakBowler.id, name: pakBowler.name },
          delivery_type: "WIDE",
          bat_runs: 0,
          wide_runs: 1,
          no_ball_runs: 0,
          bye_runs: 0,
          leg_bye_runs: 0,
          total_runs: 1,
          is_legal: false,
          is_free_hit: false,
          wicket: null,
          innings_status: "IN_PROGRESS",
          match_status: "IN_PROGRESS",
          innings_total_runs: 1,
          replacement_required: false,
        });
      },
    });
    renderScoring();
    await selectPlayers(user);
    await user.click(screen.getByRole("button", { name: /^wide$/i }));
    await user.click(screen.getByRole("button", { name: /submit wide/i }));
    await waitFor(() => {
      expect(captured).toMatchObject({
        delivery_type: "WIDE",
        bat_runs: 0,
        extra_runs: 1,
      });
    });
  });

  it("opens wicket controls with only active batters and supported dismissals", async () => {
    const user = userEvent.setup();
    stubApis({
      match: baseMatch({
        innings: [
          {
            ...baseMatch().innings![0],
            striker: { id: striker.id, name: striker.name },
            non_striker: { id: nonStriker.id, name: nonStriker.name },
          },
        ],
      }),
    });
    renderScoring();
    await selectPlayers(user);
    await user.click(screen.getByRole("button", { name: /^wicket$/i }));

    await openSelect(user, /dismissed player/i);
    const names = screen
      .getAllByRole("option")
      .map((o) => o.textContent)
      .filter(Boolean);
    expect(names.some((n) => n?.includes("Abhishek"))).toBe(true);
    expect(names.some((n) => n?.includes("Shubman"))).toBe(true);
    expect(names.some((n) => n?.includes("Gautam"))).toBe(false);
    expect(names.some((n) => n?.includes("Suryakumar"))).toBe(false);

    await user.keyboard("{Escape}");
    await openSelect(user, /dismissal type/i);
    const types = screen.getAllByRole("option").map((o) => o.textContent);
    expect(types).toEqual(["Bowled", "LBW", "Stumped", "Caught", "Run Out"]);
    await user.keyboard("{Escape}");
    expect(
      screen.queryByLabelText(/bat runs on this delivery/i),
    ).not.toBeInTheDocument();
  });

  it("disables wicket action on Free Hit", async () => {
    stubApis({
      match: baseMatch({
        innings: [
          {
            ...baseMatch().innings![0],
            free_hit_pending: true,
            striker: { id: striker.id, name: striker.name },
            non_striker: { id: nonStriker.id, name: nonStriker.name },
          },
        ],
      }),
    });
    renderScoring();
    expect(await screen.findByRole("status", { name: /free hit/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^wicket$/i })).toBeDisabled();
  });

  it("shows replacement panel and submits selected player", async () => {
    const user = userEvent.setup();
    let captured: unknown;
    stubApis({
      match: baseMatch({
        innings: [
          {
            ...baseMatch().innings![0],
            striker: null,
            non_striker: { id: nonStriker.id, name: nonStriker.name },
            replacement_required: true,
            wickets: 1,
            dismissed_player_ids: [striker.id],
          },
        ],
      }),
      onReplacement: (body) => {
        captured = body;
        return json(
          baseMatch({
            innings: [
              {
                ...baseMatch().innings![0],
                striker: { id: replacement.id, name: replacement.name },
                non_striker: { id: nonStriker.id, name: nonStriker.name },
                replacement_required: false,
                wickets: 1,
                dismissed_player_ids: [striker.id],
              },
            ],
          }),
        );
      },
    });
    renderScoring();
    expect(
      await screen.findByRole("region", { name: /replacement required/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /score 4 runs/i })).toBeDisabled();

    await chooseSelectOption(user, /replacement batter/i, /suryakumar yadav/i);
    await user.click(screen.getByRole("button", { name: /confirm replacement/i }));
    await waitFor(() => {
      expect(captured).toEqual({ player_id: replacement.id });
    });
  });

  it("requires undo confirmation and posts undo", async () => {
    const user = userEvent.setup();
    let undoCalled = false;
    stubApis({
      match: baseMatch({
        innings: [
          {
            ...baseMatch().innings![0],
            delivery_count: 1,
            legal_delivery_count: 1,
            innings_total_runs: 1,
          },
        ],
      }),
      onUndo: () => {
        undoCalled = true;
        return json({
          match: baseMatch(),
          innings_id: inningsId,
          delivery_count: 0,
          legal_delivery_count: 0,
          innings_total_runs: 0,
          next_over_number: 0,
          next_ball_in_over: 1,
          free_hit_pending: false,
          replacement_required: false,
          innings_status: "IN_PROGRESS",
          match_status: "IN_PROGRESS",
          striker: null,
          non_striker: null,
        });
      },
    });
    renderScoring();
    await user.click(await screen.findByRole("button", { name: /undo last delivery/i }));
    expect(screen.getByText(/undo the last delivery/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^undo$/i }));
    await waitFor(() => expect(undoCalled).toBe(true));
  });

  it("shows structured backend errors", async () => {
    const user = userEvent.setup();
    stubApis({
      onDelivery: () =>
        json(
          {
            detail: {
              code: "WICKET_NOT_ALLOWED_ON_FREE_HIT",
              message: "Wickets are not allowed on a Free Hit.",
            },
          },
          409,
        ),
    });
    renderScoring();
    await selectPlayers(user);
    await user.click(screen.getByRole("button", { name: /score 0 runs/i }));
    expect(
      await screen.findByText(/wickets are not allowed on a free hit/i),
    ).toBeInTheDocument();
    expect(screen.getByText("WICKET_NOT_ALLOWED_ON_FREE_HIT")).toBeInTheDocument();
  });

  it("disables scoring controls when innings is completed", async () => {
    stubApis({
      match: baseMatch({
        status: "INNINGS_BREAK",
        innings: [
          {
            ...baseMatch().innings![0],
            status: "COMPLETED",
            striker: { id: striker.id, name: striker.name },
            non_striker: { id: nonStriker.id, name: nonStriker.name },
            innings_total_runs: 120,
            wickets: 10,
            legal_delivery_count: 60,
            delivery_count: 65,
          },
        ],
      }),
    });
    renderScoring();
    expect(
      await screen.findByText(/delivery controls are disabled/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /score 4 runs/i })).toBeDisabled();
    expect(
      screen.getByRole("button", { name: /start next innings/i }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/^striker$/i)).toHaveTextContent(/select striker/i);
    expect(screen.getByLabelText(/^non-striker$/i)).toHaveTextContent(
      /select non-striker/i,
    );
    expect(screen.getByLabelText(/^bowler$/i)).toHaveTextContent(/select bowler/i);
  });

  it("clears active players when the next innings starts", async () => {
    const user = userEvent.setup();
    const innings2Id = "dddddddd-dddd-7ddd-8ddd-dddddddddddd";
    const pakBatter: Player = {
      id: "b7777777-7777-7777-8777-777777777777",
      team_id: pakistan.id,
      name: "Fakhar Zaman",
      batting_order: 2,
      roles: ["Batsman"],
    };
    const indiaBowler: Player = {
      id: "b8888888-8888-7888-8888-888888888888",
      team_id: india.id,
      name: "Jasprit Bumrah",
      batting_order: 10,
      roles: ["Bowler"],
    };

    const breakMatch = baseMatch({
      status: "INNINGS_BREAK",
      innings: [
        {
          ...baseMatch().innings![0],
          status: "COMPLETED",
          striker: { id: striker.id, name: striker.name },
          non_striker: { id: nonStriker.id, name: nonStriker.name },
          innings_total_runs: 104,
          wickets: 3,
          legal_delivery_count: 30,
          delivery_count: 32,
        },
      ],
    });
    const nextMatch = baseMatch({
      status: "IN_PROGRESS",
      innings: [
        {
          ...breakMatch.innings![0],
          status: "COMPLETED",
        },
        {
          id: innings2Id,
          innings_number: 2,
          batting_team: pakistan,
          bowling_team: india,
          status: "IN_PROGRESS",
          created_at: "2026-09-18T13:00:00Z",
          striker: null,
          non_striker: null,
          replacement_required: false,
          innings_total_runs: 0,
          legal_delivery_count: 0,
          delivery_count: 0,
          next_over_number: 0,
          next_ball_in_over: 1,
          free_hit_pending: false,
          wickets: 0,
          dismissed_player_ids: [],
          scorecard: emptyScorecard(),
        },
      ],
    });

    let current = breakMatch;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (
        url.endsWith(`/api/v1/matches/${matchId}/innings/start`) &&
        init?.method === "POST"
      ) {
        current = nextMatch;
        return json(current);
      }
      if (url.endsWith(`/api/v1/matches/${matchId}`)) return json(current);
      if (url.endsWith(`/api/v1/teams/${india.id}/players`)) {
        return json([striker, nonStriker, bowlerOnly, coach, replacement, indiaBowler]);
      }
      if (url.endsWith(`/api/v1/teams/${pakistan.id}/players`)) {
        return json([pakBowler, pakBatter]);
      }
      if (url.includes("/deliveries")) return json([]);
      throw new Error(url);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderScoring();
    expect(
      await screen.findByRole("button", { name: /start next innings/i }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/^striker$/i)).toHaveTextContent(/select striker/i);

    await user.click(screen.getByRole("button", { name: /start next innings/i }));

    expect(
      await screen.findByText(/pakistan batting/i),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/^striker$/i)).toHaveTextContent(/select striker/i);
    expect(screen.getByLabelText(/^non-striker$/i)).toHaveTextContent(
      /select non-striker/i,
    );
    expect(screen.getByLabelText(/^bowler$/i)).toHaveTextContent(/select bowler/i);
    expect(screen.getByLabelText(/^striker$/i)).not.toHaveTextContent(
      /abhishek sharma/i,
    );
    expect(screen.getByLabelText(/^bowler$/i)).not.toHaveTextContent(
      /mustafizur|shaheen/i,
    );
  });

  it("shows match result summary when the match is completed", async () => {
    stubApis({
      match: baseMatch({
        status: "COMPLETED",
        overs: 2,
        innings: [
          {
            ...baseMatch().innings![0],
            status: "COMPLETED",
            innings_number: 1,
            innings_total_runs: 39,
            wickets: 2,
            legal_delivery_count: 12,
            delivery_count: 12,
            scorecard: emptyScorecard({
              total_runs: 39,
              wickets: 2,
              overs_display: "2.0",
              run_rate: 19.5,
            }),
          },
          {
            ...baseMatch().innings![0],
            id: "dddddddd-dddd-7ddd-8ddd-dddddddddddd",
            status: "COMPLETED",
            innings_number: 2,
            batting_team: pakistan,
            bowling_team: india,
            innings_total_runs: 8,
            wickets: 1,
            legal_delivery_count: 12,
            delivery_count: 12,
            target: 40,
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
    renderScoring();

    expect(
      await screen.findByRole("region", { name: /match result summary/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/won by 31 runs/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /score 4 runs/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/^active players$/i)).not.toBeInTheDocument();
  });

  it("prevents duplicate submissions while scoring is pending", async () => {
    const user = userEvent.setup();
    let resolveDelivery: ((value: Response) => void) | undefined;
    stubApis({
      onDelivery: () =>
        new Promise<Response>((resolve) => {
          resolveDelivery = resolve;
        }),
    });
    renderScoring();
    await selectPlayers(user);
    const four = screen.getByRole("button", { name: /score 4 runs/i });
    await user.click(four);
    expect(await screen.findByText(/scoring…/i)).toBeInTheDocument();
    expect(four).toBeDisabled();
    resolveDelivery?.(
      json({
        id: "dddddddd-dddd-7ddd-8ddd-dddddddddddd",
        innings_id: inningsId,
        sequence_no: 1,
        over_number: 0,
        ball_in_over: 1,
        striker: { id: striker.id, name: striker.name },
        non_striker: { id: nonStriker.id, name: nonStriker.name },
        bowler: { id: pakBowler.id, name: pakBowler.name },
        delivery_type: "NORMAL",
        bat_runs: 4,
        wide_runs: 0,
        no_ball_runs: 0,
        bye_runs: 0,
        leg_bye_runs: 0,
        total_runs: 4,
        is_legal: true,
        is_free_hit: false,
        wicket: null,
        innings_status: "IN_PROGRESS",
        match_status: "IN_PROGRESS",
        innings_total_runs: 4,
        replacement_required: false,
      }),
    );
    await waitFor(() => expect(screen.queryByText(/^scoring…$/i)).not.toBeInTheDocument());
  });
});
