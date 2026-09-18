import { apiRequest } from "@/lib/api/client";
import type {
  DeliveryCreatePayload,
  DeliveryHistoryItem,
  DeliveryResponse,
  Match,
  MatchCreatePayload,
  Player,
  Team,
  UndoResponse,
} from "@/lib/api/types";

export function fetchTeams(): Promise<Team[]> {
  return apiRequest<Team[]>("/api/v1/teams");
}

export function fetchTeamPlayers(teamId: string): Promise<Player[]> {
  return apiRequest<Player[]>(`/api/v1/teams/${teamId}/players`);
}

export function fetchMatches(): Promise<Match[]> {
  return apiRequest<Match[]>("/api/v1/matches");
}

export function fetchMatch(matchId: string): Promise<Match> {
  return apiRequest<Match>(`/api/v1/matches/${matchId}`);
}

export function createMatch(payload: MatchCreatePayload): Promise<Match> {
  return apiRequest<Match>("/api/v1/matches", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function startMatch(matchId: string): Promise<Match> {
  return apiRequest<Match>(`/api/v1/matches/${matchId}/start`, {
    method: "POST",
  });
}

export function startNextInnings(matchId: string): Promise<Match> {
  return apiRequest<Match>(`/api/v1/matches/${matchId}/innings/start`, {
    method: "POST",
  });
}

export function completeInnings(inningsId: string): Promise<Match> {
  return apiRequest<Match>(`/api/v1/innings/${inningsId}/complete`, {
    method: "POST",
  });
}

export function fetchInningsDeliveries(
  inningsId: string,
): Promise<DeliveryHistoryItem[]> {
  return apiRequest<DeliveryHistoryItem[]>(
    `/api/v1/innings/${inningsId}/deliveries`,
  );
}

export function submitDelivery(
  inningsId: string,
  payload: DeliveryCreatePayload,
): Promise<DeliveryResponse> {
  return apiRequest<DeliveryResponse>(
    `/api/v1/innings/${inningsId}/deliveries`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function submitReplacement(
  inningsId: string,
  playerId: string,
): Promise<Match> {
  return apiRequest<Match>(`/api/v1/innings/${inningsId}/replacement`, {
    method: "POST",
    body: JSON.stringify({ player_id: playerId }),
  });
}

export function undoLatestDelivery(inningsId: string): Promise<UndoResponse> {
  return apiRequest<UndoResponse>(`/api/v1/innings/${inningsId}/undo`, {
    method: "POST",
  });
}
