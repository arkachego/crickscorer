import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { MatchDetailPage } from "@/pages/MatchDetailPage";
import { MatchListPage } from "@/pages/MatchListPage";
import { ScoreboardPage } from "@/pages/ScoreboardPage";
import type { Match } from "@/lib/api/types";

export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
}

export function renderApp(route = "/matches") {
  const queryClient = createTestQueryClient();

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  }

  return {
    queryClient,
    ...render(
      <Routes>
        <Route path="/matches" element={<MatchListPage />} />
        <Route path="/matches/:matchId" element={<MatchDetailPage />} />
        <Route
          path="/matches/:matchId/scoreboard"
          element={<ScoreboardPage />}
        />
      </Routes>,
      { wrapper: Wrapper },
    ),
  };
}

export function renderPage(
  ui: ReactElement,
  {
    route = "/matches",
    queryClient = createTestQueryClient(),
  }: { route?: string; queryClient?: QueryClient } = {},
) {
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  }

  return {
    queryClient,
    ...render(ui, { wrapper: Wrapper }),
  };
}

export const mockMatches: Match[] = [
  {
    id: "aaaaaaaa-aaaa-7aaa-8aaa-aaaaaaaaaaaa",
    team_1: {
      id: "11111111-1111-7111-8111-111111111111",
      name: "India",
      short_code: "IND",
      flag_url: "https://example.test/ind.svg",
    },
    team_2: {
      id: "22222222-2222-7222-8222-222222222222",
      name: "Pakistan",
      short_code: "PAK",
      flag_url: "https://example.test/pak.svg",
    },
    batting_first_team: {
      id: "11111111-1111-7111-8111-111111111111",
      name: "India",
      short_code: "IND",
      flag_url: "https://example.test/ind.svg",
    },
    format: "T20",
    overs: 20,
    status: "CREATED",
    created_at: "2026-09-18T12:00:00Z",
  },
  {
    id: "bbbbbbbb-bbbb-7bbb-8bbb-bbbbbbbbbbbb",
    team_1: {
      id: "11111111-1111-7111-8111-111111111111",
      name: "India",
      short_code: "IND",
      flag_url: "https://example.test/ind.svg",
    },
    team_2: {
      id: "22222222-2222-7222-8222-222222222222",
      name: "Pakistan",
      short_code: "PAK",
      flag_url: "https://example.test/pak.svg",
    },
    batting_first_team: {
      id: "22222222-2222-7222-8222-222222222222",
      name: "Pakistan",
      short_code: "PAK",
      flag_url: "https://example.test/pak.svg",
    },
    format: "T10",
    overs: 10,
    status: "CREATED",
    created_at: "2026-09-18T11:00:00Z",
  },
];
