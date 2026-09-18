import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { io, type Socket } from "socket.io-client";
import { applyMatchLiveSnapshot } from "@/lib/live/snapshot-cache";
import type { LiveConnectionStatus, MatchLiveSnapshot } from "@/lib/api/types";

function socketBaseUrl(): string {
  return (import.meta.env.VITE_SOCKET_URL as string | undefined) ?? "";
}

function isValidSnapshot(
  matchId: string,
  payload: unknown,
): payload is MatchLiveSnapshot {
  if (!payload || typeof payload !== "object") return false;
  const snap = payload as MatchLiveSnapshot;
  return (
    snap.match_id === matchId &&
    typeof snap.version === "number" &&
    Number.isFinite(snap.version) &&
    snap.match != null &&
    typeof snap.match === "object" &&
    snap.deliveries_by_innings != null &&
    typeof snap.deliveries_by_innings === "object"
  );
}

/**
 * Connect to Socket.IO for a match scoreboard: join room, apply snapshots.
 * Connection is owned by the scoreboard page and torn down on unmount.
 */
export function useMatchLiveSocket(matchId: string | undefined): {
  status: LiveConnectionStatus;
  lastError: string | null;
} {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<LiveConnectionStatus>("connecting");
  const [lastError, setLastError] = useState<string | null>(null);
  const socketRef = useRef<Socket | null>(null);
  const joinBlockedRef = useRef(false);

  useEffect(() => {
    if (!matchId) {
      return;
    }

    const activeMatchId = matchId;
    let cancelled = false;
    joinBlockedRef.current = false;
    setStatus("connecting");
    setLastError(null);

    const socket = io(socketBaseUrl(), {
      path: "/socket.io",
      transports: ["websocket", "polling"],
      autoConnect: true,
      reconnection: true,
      reconnectionAttempts: Infinity,
      reconnectionDelay: 500,
      reconnectionDelayMax: 5000,
    });
    socketRef.current = socket;

    function joinRoom() {
      if (joinBlockedRef.current) return;
      socket.emit("match:join", { match_id: activeMatchId });
    }

    function onSnapshot(event: string, payload: unknown) {
      if (cancelled) return;
      if (!isValidSnapshot(activeMatchId, payload)) {
        setLastError("Received an invalid live update and ignored it.");
        return;
      }
      applyMatchLiveSnapshot(queryClient, payload, {
        force: event === "match:joined",
      });
      if (event === "match:joined" || event === "match:update") {
        setStatus("live");
        setLastError(null);
      }
    }

    socket.on("connect", () => {
      if (cancelled) return;
      setStatus("live");
      joinRoom();
    });

    socket.on("disconnect", () => {
      if (cancelled) return;
      setStatus("disconnected");
    });

    socket.io.on("reconnect_attempt", () => {
      if (cancelled) return;
      setStatus("reconnecting");
    });

    socket.io.on("reconnect", () => {
      if (cancelled) return;
      setStatus("live");
      joinRoom();
    });

    socket.on("connect_error", () => {
      if (cancelled) return;
      setStatus("error");
      setLastError(
        "Unable to connect for live updates. Showing last known REST state.",
      );
    });

    socket.on("match:joined", (payload) => onSnapshot("match:joined", payload));
    socket.on("match:update", (payload) => onSnapshot("match:update", payload));
    socket.on("match:error", (payload: { message?: string; code?: string }) => {
      if (cancelled) return;
      setLastError(payload?.message ?? "Live update error.");
      if (
        payload?.code === "MATCH_NOT_FOUND" ||
        payload?.code === "INVALID_MATCH_ID"
      ) {
        joinBlockedRef.current = true;
        setStatus("error");
        socket.io.opts.reconnection = false;
      }
    });

    return () => {
      cancelled = true;
      socket.removeAllListeners();
      socket.io.removeAllListeners();
      socket.disconnect();
      socketRef.current = null;
    };
  }, [matchId, queryClient]);

  return { status, lastError };
}
