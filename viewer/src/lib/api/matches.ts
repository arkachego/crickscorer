import { apiRequest } from "@/lib/api/client";
import type { DeliveryHistoryItem, Match } from "@/lib/api/types";

export function fetchMatches(): Promise<Match[]> {
  return apiRequest<Match[]>("/api/v1/matches");
}

export function fetchMatch(matchId: string): Promise<Match> {
  return apiRequest<Match>(`/api/v1/matches/${matchId}`);
}

export function fetchInningsDeliveries(
  inningsId: string,
): Promise<DeliveryHistoryItem[]> {
  return apiRequest<DeliveryHistoryItem[]>(
    `/api/v1/innings/${inningsId}/deliveries`,
  );
}
