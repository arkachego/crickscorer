import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchInningsDeliveries,
  fetchMatch,
  fetchMatches,
} from "@/lib/api/matches";
import {
  resolveDeliveriesAgainstLiveCache,
  resolveMatchAgainstLiveCache,
} from "@/lib/live/snapshot-cache";
import {
  deliveriesQueryKey,
  matchQueryKey,
  matchesQueryKey,
} from "@/lib/query-keys";

export { deliveriesQueryKey, matchQueryKey, matchesQueryKey };

export function useMatches() {
  return useQuery({
    queryKey: matchesQueryKey,
    queryFn: fetchMatches,
  });
}

export function useMatch(matchId: string | undefined) {
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: matchQueryKey(matchId ?? ""),
    queryFn: async () => {
      const match = await fetchMatch(matchId!);
      return resolveMatchAgainstLiveCache(queryClient, matchId!, match);
    },
    enabled: Boolean(matchId),
  });
}

export function useInningsDeliveries(
  inningsId: string | undefined,
  matchId?: string,
) {
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: deliveriesQueryKey(inningsId ?? ""),
    queryFn: async () => {
      const deliveries = await fetchInningsDeliveries(inningsId!);
      if (!matchId) return deliveries;
      return resolveDeliveriesAgainstLiveCache(
        queryClient,
        matchId,
        inningsId!,
        deliveries,
      );
    },
    enabled: Boolean(inningsId),
  });
}
