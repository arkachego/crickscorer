import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { CreateMatchForm } from "@/components/create-match/CreateMatchForm";
import {
  chooseSelectOption,
  mockTeams,
  openSelect,
  renderWithProviders,
} from "@/test/test-utils";

function mockFetchSequence(
  handlers: Array<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response> | Response>,
) {
  let call = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const handler = handlers[Math.min(call, handlers.length - 1)];
      call += 1;
      return handler(input, init);
    }),
  );
}

function teamsResponse() {
  return new Response(JSON.stringify(mockTeams), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

async function renderReadyForm() {
  mockFetchSequence([() => teamsResponse()]);
  renderWithProviders(<CreateMatchForm />);
  expect(await screen.findByLabelText(/^team 1$/i)).toBeInTheDocument();
  return userEvent.setup();
}

const indiaOption = /india \(ind\)/i;
const pakistanOption = /pakistan \(pak\)/i;

describe("CreateMatchForm", () => {
  it("renders required fields and creatable formats without TEST", async () => {
    const user = await renderReadyForm();

    expect(screen.getByLabelText(/^team 1$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^team 2$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^format$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^overs$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^batting first$/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /create match/i }),
    ).toBeInTheDocument();

    await openSelect(user, /^format$/i);
    const options = screen.getAllByRole("option").map((option) => option.textContent);
    expect(options).toEqual(["T10", "T20", "One Day", "Custom"]);
    expect(options).not.toContain("TEST");
  });

  it("excludes selected Team 1 from Team 2 and drives batting-first options", async () => {
    const user = await renderReadyForm();

    await chooseSelectOption(user, /^team 1$/i, indiaOption);
    await openSelect(user, /^team 2$/i);
    expect(screen.queryByRole("option", { name: indiaOption })).not.toBeInTheDocument();
    expect(screen.getByRole("option", { name: pakistanOption })).toBeInTheDocument();

    await user.click(screen.getByRole("option", { name: pakistanOption }));
    await openSelect(user, /^batting first$/i);
    const battingLabels = screen
      .getAllByRole("option")
      .map((option) => option.getAttribute("aria-label"));
    expect(battingLabels).toEqual(
      expect.arrayContaining([
        expect.stringMatching(indiaOption),
        expect.stringMatching(pakistanOption),
      ]),
    );
    expect(battingLabels).toHaveLength(2);
  });

  it("uses fixed overs for T10/T20/ONE_DAY and shows editable overs for CUSTOM", async () => {
    const user = await renderReadyForm();
    const overs = () => screen.getByLabelText(/^overs$/i) as HTMLInputElement;

    await chooseSelectOption(user, /^format$/i, /^t10$/i);
    expect(overs()).toHaveValue("10");
    expect(overs()).toHaveAttribute("readonly");

    await chooseSelectOption(user, /^format$/i, /^t20$/i);
    expect(overs()).toHaveValue("20");

    await chooseSelectOption(user, /^format$/i, /^one day$/i);
    expect(overs()).toHaveValue("50");

    await chooseSelectOption(user, /^format$/i, /^custom$/i);
    expect(overs()).not.toHaveAttribute("readonly");
    expect(overs()).toHaveAttribute("type", "number");
    expect(overs()).toHaveAttribute("min", "1");
    expect(overs()).toHaveValue(5);
    expect(
      screen.getByText(/custom format needs a positive whole number of overs\.$/i),
    ).toBeInTheDocument();
  });

  it("validates required fields and CUSTOM overs", async () => {
    const user = await renderReadyForm();

    await user.click(screen.getByRole("button", { name: /create match/i }));
    expect(screen.getByText(/team 1 is required/i)).toBeInTheDocument();
    expect(screen.getByText(/team 2 is required/i)).toBeInTheDocument();
    expect(
      screen.getByText(/batting first team is required/i),
    ).toBeInTheDocument();

    await chooseSelectOption(user, /^team 1$/i, indiaOption);
    await chooseSelectOption(user, /^team 2$/i, pakistanOption);
    await chooseSelectOption(user, /^batting first$/i, indiaOption);
    await chooseSelectOption(user, /^format$/i, /^custom$/i);

    await user.clear(screen.getByLabelText(/^overs$/i));
    await user.click(screen.getByRole("button", { name: /create match/i }));
    expect(
      screen.getByText(/custom format requires an overs value/i),
    ).toBeInTheDocument();

    await user.clear(screen.getByLabelText(/^overs$/i));
    await user.type(screen.getByLabelText(/^overs$/i), "0");
    await user.click(screen.getByRole("button", { name: /create match/i }));
    expect(
      screen.getByText(/overs must be a positive integer/i),
    ).toBeInTheDocument();

    await user.clear(screen.getByLabelText(/^overs$/i));
    await user.type(screen.getByLabelText(/^overs$/i), "-3");
    await user.click(screen.getByRole("button", { name: /create match/i }));
    expect(screen.getByText(/overs must be a whole number/i)).toBeInTheDocument();

    await user.clear(screen.getByLabelText(/^overs$/i));
    await user.type(screen.getByLabelText(/^overs$/i), "12.5");
    await user.click(screen.getByRole("button", { name: /create match/i }));
    expect(screen.getByText(/overs must be a whole number/i)).toBeInTheDocument();
  });

  it("submits a valid T20 payload and shows success", async () => {
    const user = userEvent.setup();
    let createBody: unknown = null;
    let createCalls = 0;

    mockFetchSequence([
      () => teamsResponse(),
      async (_input, init) => {
        createCalls += 1;
        createBody = JSON.parse(String(init?.body));
        await new Promise((resolve) => setTimeout(resolve, 40));
        return new Response(
          JSON.stringify({
            id: "aaaaaaaa-aaaa-7aaa-8aaa-aaaaaaaaaaaa",
            team_1: mockTeams[0],
            team_2: mockTeams[1],
            batting_first_team: mockTeams[0],
            format: "T20",
            overs: 20,
            status: "CREATED",
            created_at: "2026-09-18T12:00:00Z",
          }),
          { status: 201, headers: { "Content-Type": "application/json" } },
        );
      },
    ]);

    renderWithProviders(<CreateMatchForm />);
    await screen.findByLabelText(/^team 1$/i);

    await chooseSelectOption(user, /^team 1$/i, indiaOption);
    await chooseSelectOption(user, /^team 2$/i, pakistanOption);
    await chooseSelectOption(user, /^format$/i, /^t20$/i);
    await chooseSelectOption(user, /^batting first$/i, indiaOption);

    const submit = screen.getByRole("button", { name: /create match/i });
    await user.click(submit);
    expect(await screen.findByRole("button", { name: /creating match/i })).toBeDisabled();

    expect(
      await screen.findByRole("status", { name: /match created/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/india vs pakistan/i)).toBeInTheDocument();
    expect(screen.getByText(/^t20$/i)).toBeInTheDocument();
    expect(screen.getByText(/^20$/)).toBeInTheDocument();
    expect(screen.queryByText(/match id/i)).not.toBeInTheDocument();
    expect(
      screen.queryByText("aaaaaaaa-aaaa-7aaa-8aaa-aaaaaaaaaaaa"),
    ).not.toBeInTheDocument();
    expect(createCalls).toBe(1);
    expect(createBody).toEqual({
      team_1_id: mockTeams[0].id,
      team_2_id: mockTeams[1].id,
      format: "T20",
      batting_first_team_id: mockTeams[0].id,
      overs: 20,
    });
  });

  it("displays API domain, not-found, validation, and network errors", async () => {
    const user = userEvent.setup();

    async function fillValid(userApi: typeof user) {
      await chooseSelectOption(userApi, /^team 1$/i, indiaOption);
      await chooseSelectOption(userApi, /^team 2$/i, pakistanOption);
      await chooseSelectOption(userApi, /^batting first$/i, indiaOption);
    }

    mockFetchSequence([
      () => teamsResponse(),
      () =>
        new Response(
          JSON.stringify({
            detail: {
              code: "TEAMS_MUST_BE_DISTINCT",
              message: "team_1_id and team_2_id must refer to different teams.",
            },
          }),
          { status: 400, headers: { "Content-Type": "application/json" } },
        ),
    ]);
    const { unmount } = renderWithProviders(<CreateMatchForm />);
    await screen.findByLabelText(/^team 1$/i);
    await fillValid(user);
    await user.click(screen.getByRole("button", { name: /create match/i }));
    expect(
      await screen.findByText(
        /team_1_id and team_2_id must refer to different teams/i,
      ),
    ).toBeInTheDocument();
    unmount();

    mockFetchSequence([
      () => teamsResponse(),
      () =>
        new Response(
          JSON.stringify({
            detail: {
              code: "TEAM_NOT_FOUND",
              message: "Team referenced by team_1_id was not found.",
            },
          }),
          { status: 404, headers: { "Content-Type": "application/json" } },
        ),
    ]);
    const second = renderWithProviders(<CreateMatchForm />);
    await screen.findByLabelText(/^team 1$/i);
    await fillValid(user);
    await user.click(screen.getByRole("button", { name: /create match/i }));
    expect(
      await screen.findByText(/team referenced by team_1_id was not found/i),
    ).toBeInTheDocument();
    second.unmount();

    mockFetchSequence([
      () => teamsResponse(),
      () =>
        new Response(
          JSON.stringify({
            detail: [{ msg: "Input should be a valid UUID", loc: ["body", "team_1_id"] }],
          }),
          { status: 422, headers: { "Content-Type": "application/json" } },
        ),
    ]);
    const third = renderWithProviders(<CreateMatchForm />);
    await screen.findByLabelText(/^team 1$/i);
    await fillValid(user);
    await user.click(screen.getByRole("button", { name: /create match/i }));
    expect(
      await screen.findByText(/input should be a valid uuid/i),
    ).toBeInTheDocument();
    third.unmount();

    mockFetchSequence([
      () => teamsResponse(),
      () => Promise.reject(new TypeError("Failed to fetch")),
    ]);
    renderWithProviders(<CreateMatchForm />);
    await screen.findByLabelText(/^team 1$/i);
    await fillValid(user);
    await user.click(screen.getByRole("button", { name: /create match/i }));
    expect(
      await screen.findByText(/unable to complete the request\. please try again/i),
    ).toBeInTheDocument();
  });

  it("prevents duplicate submission while pending", async () => {
    const user = userEvent.setup();
    let createCalls = 0;
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });

    mockFetchSequence([
      () => teamsResponse(),
      async (_input, init) => {
        createCalls += 1;
        expect(init?.method).toBe("POST");
        await gate;
        return new Response(
          JSON.stringify({
            id: "bbbbbbbb-bbbb-7bbb-8bbb-bbbbbbbbbbbb",
            team_1: mockTeams[0],
            team_2: mockTeams[1],
            batting_first_team: mockTeams[0],
            format: "T20",
            overs: 20,
            status: "CREATED",
            created_at: "2026-09-18T12:00:00Z",
          }),
          { status: 201, headers: { "Content-Type": "application/json" } },
        );
      },
    ]);

    renderWithProviders(<CreateMatchForm />);
    await screen.findByLabelText(/^team 1$/i);
    await chooseSelectOption(user, /^team 1$/i, indiaOption);
    await chooseSelectOption(user, /^team 2$/i, pakistanOption);
    await chooseSelectOption(user, /^batting first$/i, indiaOption);

    const button = screen.getByRole("button", { name: /create match/i });
    await user.click(button);
    await user.click(button);
    expect(await screen.findByRole("button", { name: /creating match/i })).toBeDisabled();
    expect(createCalls).toBe(1);
    release();
    await waitFor(() => {
      expect(screen.getByText(/match created/i)).toBeInTheDocument();
    });
  });
});
