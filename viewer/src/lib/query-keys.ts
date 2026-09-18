export const matchesQueryKey = ["matches"] as const;

export function matchQueryKey(matchId: string) {
  return ["matches", matchId] as const;
}

export function deliveriesQueryKey(inningsId: string) {
  return ["innings", inningsId, "deliveries"] as const;
}
