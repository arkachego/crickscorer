import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { MatchDetailPage } from "@/pages/MatchDetailPage";
import { MatchListPage } from "@/pages/MatchListPage";
import type { Match } from "@/lib/api/types";

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

function baseMatch(overrides: Partial<Match> = {}): Match {
  return {
    id: "aaaaaaaa-aaaa-7aaa-8aaa-aaaaaaaaaaaa",
    team_1: india,
    team_2: pakistan,
    batting_first_team: india,
    format: "T20",
    overs: 20,
    status: "CREATED",
    created_at: "2026-09-18T12:00:00Z",
    innings: [],
    ...overrides,
  };
}

function renderAdmin(route: string) {
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
      <Route path="/matches" element={<MatchListPage />} />
      <Route path="/matches/:matchId" element={<MatchDetailPage />} />
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

describe("Admin match lifecycle", () => {
  it("lists matches and shows Start Match for CREATED", async () => {
    const match = baseMatch();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/api/v1/matches")) return json([match]);
        if (url.endsWith(`/api/v1/matches/${match.id}`)) return json(match);
        throw new Error(url);
      }),
    );

    renderAdmin("/matches");
    expect(await screen.findByRole("heading", { name: /^matches$/i })).toBeInTheDocument();
    const link = await screen.findByRole("link", { name: /india vs pakistan/i });
    expect(link).toHaveAttribute("href", `/matches/${match.id}`);

    renderAdmin(`/matches/${match.id}`);
    expect(
      await screen.findByRole("button", { name: /start match/i }),
    ).toBeInTheDocument();
  });

  it("starts a match and refreshes authoritative state", async () => {
    const user = userEvent.setup();
    const created = baseMatch();
    const started = baseMatch({
      status: "IN_PROGRESS",
      innings: [
        {
          id: "cccccccc-cccc-7ccc-8ccc-cccccccccccc",
          innings_number: 1,
          batting_team: india,
          bowling_team: pakistan,
          status: "IN_PROGRESS",
          created_at: "2026-09-18T12:01:00Z",
        },
      ],
    });
    let current = created;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith(`/api/v1/matches/${created.id}/start`) && init?.method === "POST") {
        current = started;
        return json(started);
      }
      if (url.endsWith(`/api/v1/matches/${created.id}`)) return json(current);
      throw new Error(url);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderAdmin(`/matches/${created.id}`);
    await user.click(await screen.findByRole("button", { name: /start match/i }));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        `/api/v1/matches/${created.id}/start`,
        expect.objectContaining({ method: "POST" }),
      );
    });
    expect(await screen.findByText(/innings 1/i)).toBeInTheDocument();
    expect(screen.getByText(/india batting/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /complete innings/i }),
    ).toBeInTheDocument();
  });

  it("completes innings and starts next innings through to COMPLETED", async () => {
    const user = userEvent.setup();
    const innings1 = {
      id: "cccccccc-cccc-7ccc-8ccc-cccccccccccc",
      innings_number: 1,
      batting_team: india,
      bowling_team: pakistan,
      status: "IN_PROGRESS" as const,
      created_at: "2026-09-18T12:01:00Z",
    };
    let current = baseMatch({
      status: "IN_PROGRESS",
      innings: [innings1],
    });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith(`/api/v1/innings/${innings1.id}/complete`) && init?.method === "POST") {
        current = baseMatch({
          status: "INNINGS_BREAK",
          innings: [{ ...innings1, status: "COMPLETED" }],
        });
        return json(current);
      }
      if (url.endsWith(`/api/v1/matches/${current.id}/innings/start`) && init?.method === "POST") {
        current = baseMatch({
          status: "IN_PROGRESS",
          innings: [
            { ...innings1, status: "COMPLETED" },
            {
              id: "dddddddd-dddd-7ddd-8ddd-dddddddddddd",
              innings_number: 2,
              batting_team: pakistan,
              bowling_team: india,
              status: "IN_PROGRESS",
              created_at: "2026-09-18T12:02:00Z",
            },
          ],
        });
        return json(current);
      }
      if (
        url.endsWith("/api/v1/innings/dddddddd-dddd-7ddd-8ddd-dddddddddddd/complete") &&
        init?.method === "POST"
      ) {
        current = baseMatch({
          status: "COMPLETED",
          innings: [
            { ...innings1, status: "COMPLETED" },
            {
              id: "dddddddd-dddd-7ddd-8ddd-dddddddddddd",
              innings_number: 2,
              batting_team: pakistan,
              bowling_team: india,
              status: "COMPLETED",
              created_at: "2026-09-18T12:02:00Z",
            },
          ],
        });
        return json(current);
      }
      if (url.endsWith(`/api/v1/matches/${current.id}`)) return json(current);
      throw new Error(`${init?.method} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderAdmin(`/matches/${current.id}`);
    await user.click(await screen.findByRole("button", { name: /complete innings/i }));
    expect(
      await screen.findByRole("button", { name: /start next innings/i }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /start next innings/i }));
    expect(await screen.findByText(/innings 2/i)).toBeInTheDocument();
    expect(screen.getByText(/pakistan batting/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /complete innings/i }));
    expect(
      await screen.findByText(/match completed\. no further lifecycle actions/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /start match/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /complete innings/i })).not.toBeInTheDocument();
  });

  it("renders lifecycle conflict and network errors", async () => {
    const user = userEvent.setup();
    const match = baseMatch();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith(`/api/v1/matches/${match.id}`) && !init?.method) {
          return json(match);
        }
        if (url.endsWith(`/api/v1/matches/${match.id}/start`)) {
          return json(
            {
              detail: {
                code: "INVALID_MATCH_TRANSITION",
                message: "Match in status IN_PROGRESS cannot be started.",
              },
            },
            409,
          );
        }
        throw new Error(url);
      }),
    );
    renderAdmin(`/matches/${match.id}`);
    await user.click(await screen.findByRole("button", { name: /start match/i }));
    expect(
      await screen.findByText(/match in status in_progress cannot be started/i),
    ).toBeInTheDocument();
  });

  it("disables lifecycle action while pending", async () => {
    const user = userEvent.setup();
    const match = baseMatch();
    let current = match;
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    let calls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith(`/api/v1/matches/${match.id}/start`) && init?.method === "POST") {
          calls += 1;
          await gate;
          current = baseMatch({
            status: "IN_PROGRESS",
            innings: [
              {
                id: "cccccccc-cccc-7ccc-8ccc-cccccccccccc",
                innings_number: 1,
                batting_team: india,
                bowling_team: pakistan,
                status: "IN_PROGRESS",
                created_at: "2026-09-18T12:01:00Z",
              },
            ],
          });
          return json(current);
        }
        if (url.endsWith(`/api/v1/matches/${match.id}`)) {
          return json(current);
        }
        throw new Error(url);
      }),
    );

    renderAdmin(`/matches/${match.id}`);
    const button = await screen.findByRole("button", { name: /start match/i });
    await user.click(button);
    await user.click(button);
    expect(await screen.findByRole("button", { name: /starting match/i })).toBeDisabled();
    expect(calls).toBe(1);
    release();
    await screen.findByText(/innings 1/i);
  });
});
