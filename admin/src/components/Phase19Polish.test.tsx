import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { App } from "@/App";
import { LoadingBlock } from "@/components/LoadingBlock";
import { StatusChip } from "@/components/StatusChip";

describe("Phase 19 polish primitives", () => {
  it("exposes a skip link to main content", () => {
    render(<App />);
    expect(
      screen.getByRole("link", { name: /skip to main content/i }),
    ).toHaveAttribute("href", "#main-content");
  });

  it("LoadingBlock announces status without relying on colour alone", () => {
    render(<LoadingBlock label="Loading matches…" />);
    expect(screen.getByRole("status", { name: /loading matches/i })).toBeInTheDocument();
  });

  it("StatusChip pairs symbol with text", () => {
    render(<StatusChip label="In Progress" tone="live" />);
    expect(screen.getByText(/in progress/i)).toBeInTheDocument();
    expect(screen.getByText("●")).toBeInTheDocument();
  });
});
