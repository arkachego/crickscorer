import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
  cleanup();
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
