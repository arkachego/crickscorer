import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  BrowserRouter,
  NavLink,
  Navigate,
  Route,
  Routes,
} from "react-router-dom";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { CreateMatchPage } from "@/pages/CreateMatchPage";
import { MatchDetailPage } from "@/pages/MatchDetailPage";
import { MatchListPage } from "@/pages/MatchListPage";
import { ScoringPage } from "@/pages/ScoringPage";
import { cn } from "@/lib/utils";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      refetchOnWindowFocus: false,
    },
    mutations: {
      // Never auto-retry scoring/lifecycle mutations (duplicate delivery risk).
      retry: false,
    },
  },
});

function navClass({ isActive }: { isActive: boolean }) {
  return cn(
    "inline-flex min-h-11 items-center rounded-md border px-3 py-2 text-sm font-medium transition",
    isActive
      ? "border-white bg-white/15 text-white"
      : "border-white/20 text-white/90 hover:bg-white/10",
  );
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className="flex h-dvh flex-col overflow-hidden bg-[radial-gradient(circle_at_top,_#e7f0ea,_#f4f7f5_55%)]">
          <a
            href="#main-content"
            className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-white focus:px-3 focus:py-2 focus:text-sm focus:font-semibold focus:text-[var(--color-pitch-deep)]"
          >
            Skip to main content
          </a>
          <header className="shrink-0 border-b border-[var(--color-line)] bg-[var(--color-pitch)] text-white">
            <div className="mx-auto flex max-w-3xl flex-wrap items-center justify-between gap-3 px-4 py-4 sm:px-6">
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-white/70">
                  CrickScorer
                </p>
                <h1 className="text-lg font-semibold tracking-tight sm:text-xl">
                  Admin
                </h1>
              </div>
              <nav aria-label="Admin" className="flex flex-wrap items-center gap-2">
                <NavLink to="/matches" end className={navClass}>
                  Matches
                </NavLink>
                <NavLink to="/matches/new" className={navClass}>
                  Create Match
                </NavLink>
              </nav>
            </div>
          </header>
          <main
            id="main-content"
            tabIndex={-1}
            className="min-h-0 flex-1 overflow-y-auto outline-none"
          >
            <div className="mx-auto max-w-3xl px-4 py-6 sm:px-6 sm:py-8">
              <ErrorBoundary title="Admin UI error">
                <Routes>
                  <Route path="/" element={<Navigate to="/matches" replace />} />
                  <Route path="/matches" element={<MatchListPage />} />
                  <Route path="/matches/new" element={<CreateMatchPage />} />
                  <Route path="/matches/:matchId" element={<MatchDetailPage />} />
                  <Route
                    path="/matches/:matchId/scoring"
                    element={<ScoringPage />}
                  />
                  <Route path="*" element={<Navigate to="/matches" replace />} />
                </Routes>
              </ErrorBoundary>
            </div>
          </main>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
