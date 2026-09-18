import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  completeInnings,
  fetchInningsDeliveries,
  fetchMatch,
  fetchMatches,
  fetchTeamPlayers,
  startMatch,
  startNextInnings,
  submitDelivery,
  submitReplacement,
  undoLatestDelivery,
} from "@/lib/api/matches";
import type { DeliveryCreatePayload } from "@/lib/api/types";
import {
  resolveDeliveriesAgainstLiveCache,
  resolveMatchAgainstLiveCache,
} from "@/lib/live/snapshot-cache";

export const matchesQueryKey = ["matches"] as const;

export function matchQueryKey(matchId: string) {
  return ["matches", matchId] as const;
}

export function teamPlayersQueryKey(teamId: string) {
  return ["teams", teamId, "players"] as const;
}

export function deliveriesQueryKey(inningsId: string) {
  return ["innings", inningsId, "deliveries"] as const;
}

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

export function useTeamPlayers(teamId: string | undefined) {
  return useQuery({
    queryKey: teamPlayersQueryKey(teamId ?? ""),
    queryFn: () => fetchTeamPlayers(teamId!),
    enabled: Boolean(teamId),
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

function useLifecycleMutation(
  mutationFn: (id: string) => Promise<unknown>,
  matchId: string | undefined,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: matchesQueryKey });
      if (matchId) {
        await queryClient.invalidateQueries({ queryKey: matchQueryKey(matchId) });
      }
    },
  });
}

export function useStartMatch(matchId: string | undefined) {
  return useLifecycleMutation(startMatch, matchId);
}

export function useStartNextInnings(matchId: string | undefined) {
  return useLifecycleMutation(startNextInnings, matchId);
}

export function useCompleteInnings(matchId: string | undefined) {
  return useLifecycleMutation(completeInnings, matchId);
}

async function invalidateScoring(
  queryClient: ReturnType<typeof useQueryClient>,
  matchId: string,
  inningsId: string,
) {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: matchesQueryKey }),
    queryClient.invalidateQueries({ queryKey: matchQueryKey(matchId) }),
    queryClient.invalidateQueries({ queryKey: deliveriesQueryKey(inningsId) }),
  ]);
}

export function useSubmitDelivery(
  matchId: string | undefined,
  inningsId: string | undefined,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: DeliveryCreatePayload) =>
      submitDelivery(inningsId!, payload),
    onSuccess: async () => {
      if (matchId && inningsId) {
        await invalidateScoring(queryClient, matchId, inningsId);
      }
    },
  });
}

export function useSubmitReplacement(
  matchId: string | undefined,
  inningsId: string | undefined,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (playerId: string) => submitReplacement(inningsId!, playerId),
    onSuccess: async () => {
      if (matchId && inningsId) {
        await invalidateScoring(queryClient, matchId, inningsId);
      }
    },
  });
}

export function useUndoDelivery(
  matchId: string | undefined,
  inningsId: string | undefined,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => undoLatestDelivery(inningsId!),
    onSuccess: async () => {
      if (matchId && inningsId) {
        await invalidateScoring(queryClient, matchId, inningsId);
      }
    },
  });
}
