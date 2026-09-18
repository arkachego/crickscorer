import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { UserEvent } from "@testing-library/user-event";
import type { ReactElement, ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";

export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

export function renderWithProviders(
  ui: ReactElement,
  {
    route = "/matches/new",
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

/** Choose an option from a Radix/shadcn Select (combobox + listbox). */
export async function chooseSelectOption(
  user: UserEvent,
  fieldName: RegExp | string,
  optionName: RegExp | string,
) {
  await user.click(screen.getByRole("combobox", { name: fieldName }));
  await user.click(await screen.findByRole("option", { name: optionName }));
}

export async function openSelect(
  user: UserEvent,
  fieldName: RegExp | string,
) {
  await user.click(screen.getByRole("combobox", { name: fieldName }));
}

export const mockTeams = [
  {
    id: "11111111-1111-7111-8111-111111111111",
    name: "India",
    short_code: "IND",
    flag_url: "https://example.test/ind.svg",
  },
  {
    id: "22222222-2222-7222-8222-222222222222",
    name: "Pakistan",
    short_code: "PAK",
    flag_url: "https://example.test/pak.svg",
  },
  {
    id: "33333333-3333-7333-8333-333333333333",
    name: "Australia",
    short_code: "AUS",
    flag_url: "https://example.test/aus.svg",
  },
];
