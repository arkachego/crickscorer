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

  it("LoadingBlock announces status", () => {
    render(<LoadingBlock label="Loading scoreboard…" />);
    expect(
      screen.getByRole("status", { name: /loading scoreboard/i }),
    ).toBeInTheDocument();
  });

  it("StatusChip pairs symbol with text", () => {
    render(<StatusChip label="Live" tone="live" />);
    expect(screen.getByText(/^live$/i)).toBeInTheDocument();
    expect(screen.getByText("●")).toBeInTheDocument();
  });
});
