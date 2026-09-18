import type { QueryClient } from "@tanstack/react-query";
import {
  deliveriesQueryKey,
  matchQueryKey,
} from "@/hooks/use-match-lifecycle";
import type {
  DeliveryHistoryItem,
  Match,
  MatchLiveSnapshot,
} from "@/lib/api/types";

/** Highest applied Socket.IO snapshot version per match (module scope). */
const appliedVersions = new Map<string, number>();
const lastSnapshots = new Map<string, MatchLiveSnapshot>();

export function getAppliedLiveVersion(matchId: string): number {
  return appliedVersions.get(matchId) ?? 0;
}

export function resetLiveVersionsForTests(): void {
  appliedVersions.clear();
  lastSnapshots.clear();
}

/**
 * Apply an authoritative live snapshot if its version is newer.
 * Pass `{ force: true }` for `match:joined` so a server restart that resets
 * in-memory versions can re-baseline the client without rejecting later updates.
 * Returns true when the cache was updated.
 */
export function applyMatchLiveSnapshot(
  queryClient: QueryClient,
  snapshot: MatchLiveSnapshot,
  options?: { force?: boolean },
): boolean {
  const current = appliedVersions.get(snapshot.match_id) ?? 0;
  if (!options?.force && snapshot.version <= current) {
    return false;
  }

  appliedVersions.set(snapshot.match_id, snapshot.version);
  lastSnapshots.set(snapshot.match_id, snapshot);
  queryClient.setQueryData(matchQueryKey(snapshot.match_id), snapshot.match);

  for (const [inningsId, deliveries] of Object.entries(
    snapshot.deliveries_by_innings,
  )) {
    queryClient.setQueryData(deliveriesQueryKey(inningsId), deliveries);
  }
  return true;
}

/**
 * REST queryFn guard: if a newer socket snapshot exists, keep it instead of
 * regressing to a stale HTTP response.
 */
export function resolveMatchAgainstLiveCache(
  queryClient: QueryClient,
  matchId: string,
  match: Match,
): Match {
  const version = appliedVersions.get(matchId) ?? 0;
  if (version > 0) {
    const cached = queryClient.getQueryData<Match>(matchQueryKey(matchId));
    if (cached) {
      return cached;
    }
    const snap = lastSnapshots.get(matchId);
    if (snap) {
      return snap.match;
    }
  }
  return match;
}

export function resolveDeliveriesAgainstLiveCache(
  queryClient: QueryClient,
  matchId: string,
  inningsId: string,
  deliveries: DeliveryHistoryItem[],
): DeliveryHistoryItem[] {
  const version = appliedVersions.get(matchId) ?? 0;
  if (version > 0) {
    const cached = queryClient.getQueryData<DeliveryHistoryItem[]>(
      deliveriesQueryKey(inningsId),
    );
    if (cached) {
      return cached;
    }
    const snap = lastSnapshots.get(matchId);
    const fromSnap = snap?.deliveries_by_innings[inningsId];
    if (fromSnap) {
      return fromSnap;
    }
  }
  return deliveries;
}
