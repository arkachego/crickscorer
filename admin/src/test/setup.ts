import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// Radix Select expects pointer-capture APIs that jsdom does not implement.
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
}
if (!Element.prototype.setPointerCapture) {
  Element.prototype.setPointerCapture = () => undefined;
}
if (!Element.prototype.releasePointerCapture) {
  Element.prototype.releasePointerCapture = () => undefined;
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => undefined;
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

vi.mock("socket.io-client", () => {
  return {
    io: vi.fn(() => {
      const handlers = new Map<string, Set<(...args: unknown[]) => void>>();
      const socket = {
        on(event: string, handler: (...args: unknown[]) => void) {
          if (!handlers.has(event)) handlers.set(event, new Set());
          handlers.get(event)!.add(handler);
          return socket;
        },
        emit: vi.fn(),
        removeAllListeners: vi.fn(() => handlers.clear()),
        disconnect: vi.fn(),
        io: {
          on: vi.fn(),
          removeAllListeners: vi.fn(),
          opts: { reconnection: true },
        },
      };
      queueMicrotask(() => {
        for (const handler of handlers.get("connect") ?? []) {
          handler();
        }
      });
      return socket;
    }),
  };
});
