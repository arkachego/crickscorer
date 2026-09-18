import { Link } from "react-router-dom";
import type { Match } from "@/lib/api/types";
import { formatLabel, statusLabel } from "@/lib/utils";
import { StatusChip } from "@/components/StatusChip";

type MatchCardProps = {
  match: Match;
};

function statusTone(
  status: string,
): "neutral" | "live" | "warn" | "success" {
  if (status === "IN_PROGRESS") return "live";
  if (status === "INNINGS_BREAK") return "warn";
  if (status === "COMPLETED") return "success";
  return "neutral";
}

export function MatchCard({ match }: MatchCardProps) {
  const title = `${match.team_1.name} vs ${match.team_2.name}`;
  const summary = `${formatLabel(match.format)} · ${match.overs} overs · ${statusLabel(match.status)}`;

  return (
    <Link
      to={`/matches/${match.id}`}
      aria-label={`${title}. ${summary}.`}
      className="block rounded-xl border border-[var(--color-line)] bg-white/95 p-4 shadow-sm transition hover:border-[var(--color-accent)] hover:shadow-md focus-visible:border-[var(--color-accent)]"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate text-lg font-semibold text-[var(--color-skyline-deep)]">
            {title}
          </h3>
          <p className="mt-1 text-sm text-[var(--color-muted)]">
            {formatLabel(match.format)} · {match.overs} overs
          </p>
        </div>
        <StatusChip
          label={statusLabel(match.status)}
          tone={statusTone(match.status)}
          className="shrink-0"
        />
      </div>
    </Link>
  );
}
