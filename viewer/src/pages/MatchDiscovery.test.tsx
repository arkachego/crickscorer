import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { mockMatches, renderApp } from "@/test/test-utils";

function jsonResponse(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("Viewer match discovery", () => {
  it("renders loading then match list metadata in API order", async () => {
    let resolveList!: (value: Response) => void;
    const listGate = new Promise<Response>((resolve) => {
      resolveList = resolve;
    });

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/api/v1/matches")) {
          return listGate;
        }
        throw new Error(`Unexpected fetch: ${url}`);
      }),
    );

    renderApp("/matches");
    expect(screen.getByText(/loading matches/i)).toBeInTheDocument();
    resolveList(jsonResponse(mockMatches));

    expect(await screen.findByRole("heading", { name: /^matches$/i })).toBeInTheDocument();
    const list = await screen.findByRole("list", { name: /match list/i });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent(/india vs pakistan/i);
    expect(items[0]).toHaveTextContent(/t20 · 20 overs/i);
    expect(items[0]).not.toHaveTextContent(/batting first/i);
    expect(items[0]).toHaveTextContent(/created/i);
    expect(items[1]).toHaveTextContent(/t10 · 10 overs/i);
    expect(items[1]).not.toHaveTextContent(/batting first/i);

    const firstLink = within(items[0]).getByRole("link");
    expect(firstLink).toHaveAttribute(
      "href",
      `/matches/${mockMatches[0].id}`,
    );
    expect(firstLink).toHaveAccessibleName(/india vs pakistan/i);
  });

  it("renders empty and error states", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse([])),
    );
    const first = renderApp("/matches");
    expect(await screen.findByText(/no matches available/i)).toBeInTheDocument();
    first.unmount();

    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))),
    );
    renderApp("/matches");
    expect(await screen.findByText(/unable to load matches/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });

  it("navigates to detail and fetches the match by id", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/v1/matches")) {
        return jsonResponse(mockMatches);
      }
      if (url.endsWith(`/api/v1/matches/${mockMatches[0].id}`)) {
        return jsonResponse(mockMatches[0]);
      }
      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderApp("/matches");
    const link = await screen.findByRole("link", {
      name: /india vs pakistan\. t20 · 20 overs/i,
    });
    await user.click(link);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        `/api/v1/matches/${mockMatches[0].id}`,
        expect.any(Object),
      );
    });
    expect(
      await screen.findByRole("heading", { name: /india vs pakistan/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/^t20$/i)).toBeInTheDocument();
    expect(screen.getByText(/^20$/)).toBeInTheDocument();
    expect(screen.getByText(/^status$/i).closest("div")).toHaveTextContent(
      /created/i,
    );
    expect(screen.getByText(/batting first/i).closest("div")).toHaveTextContent(
      /india/i,
    );
    expect(
      screen.queryByRole("link", { name: /back to matches/i }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/match id/i)).not.toBeInTheDocument();
  });

  it("shows detail loading, not-found, and generic error states", async () => {
    let resolveDetail!: (value: Response) => void;
    const detailGate = new Promise<Response>((resolve) => {
      resolveDetail = resolve;
    });

    vi.stubGlobal(
      "fetch",
      vi.fn(async () => detailGate),
    );
    const loading = renderApp(`/matches/${mockMatches[0].id}`);
    expect(screen.getByText(/loading match/i)).toBeInTheDocument();
    resolveDetail(jsonResponse(mockMatches[0]));
    expect(
      await screen.findByRole("heading", { name: /india vs pakistan/i }),
    ).toBeInTheDocument();
    loading.unmount();

    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(
          { detail: { code: "MATCH_NOT_FOUND", message: "Match was not found." } },
          404,
        ),
      ),
    );
    const missing = renderApp("/matches/cccccccc-cccc-7ccc-8ccc-cccccccccccc");
    expect(await screen.findByText(/match not found/i)).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /back to matches/i }),
    ).not.toBeInTheDocument();
    missing.unmount();

    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))),
    );
    renderApp(`/matches/${mockMatches[0].id}`);
    expect(await screen.findByText(/unable to load match/i)).toBeInTheDocument();
  });

  it("supports keyboard activation of match links", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/api/v1/matches")) {
          return jsonResponse(mockMatches);
        }
        if (url.includes(mockMatches[0].id)) {
          return jsonResponse(mockMatches[0]);
        }
        throw new Error(`Unexpected fetch: ${url}`);
      }),
    );

    renderApp("/matches");
    const link = await screen.findByRole("link", {
      name: /india vs pakistan\. t20 · 20 overs/i,
    });
    link.focus();
    expect(link).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(
      await screen.findByRole("heading", { name: /india vs pakistan/i }),
    ).toBeInTheDocument();
  });
});
