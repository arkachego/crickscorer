import { useMutation } from "@tanstack/react-query";
import { createMatch } from "@/lib/api/matches";
import type { MatchCreatePayload } from "@/lib/api/types";

export function useCreateMatch() {
  return useMutation({
    mutationFn: (payload: MatchCreatePayload) => createMatch(payload),
  });
}
