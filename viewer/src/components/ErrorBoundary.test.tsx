import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ErrorBoundary } from "@/components/ErrorBoundary";

function Boom(): null {
  throw new Error("render boom");
}

describe("Viewer ErrorBoundary", () => {
  it("shows recovery UI instead of crashing the tree", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(
      <ErrorBoundary title="Viewer UI error">
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByText(/viewer ui error/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /refresh/i })).toBeInTheDocument();
    spy.mockRestore();
  });
});
