import { useQuery } from "@tanstack/react-query";
import { fetchTeams } from "@/lib/api/matches";

export const teamsQueryKey = ["teams"] as const;

export function useTeams() {
  return useQuery({
    queryKey: teamsQueryKey,
    queryFn: fetchTeams,
  });
}
