import type { Match } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/alert";

type MatchSuccessProps = {
  match: Match;
  onCreateAnother: () => void;
};

function formatLabel(format: string): string {
  if (format === "ONE_DAY") return "One Day";
  if (format === "CUSTOM") return "Custom";
  return format;
}

export function MatchSuccess({ match, onCreateAnother }: MatchSuccessProps) {
  return (
    <Alert tone="success" role="status" title="Match created">
      <div className="space-y-3">
        <p className="text-base font-semibold text-[var(--color-ink)]">
          {match.team_1.name} vs {match.team_2.name}
        </p>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-[var(--color-ink)]">
          <div>
            <dt className="text-xs uppercase tracking-wide text-[var(--color-muted)]">
              Format
            </dt>
            <dd>{formatLabel(match.format)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-[var(--color-muted)]">
              Overs
            </dt>
            <dd>{match.overs}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-[var(--color-muted)]">
              Status
            </dt>
            <dd>{match.status}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-[var(--color-muted)]">
              Batting first
            </dt>
            <dd>{match.batting_first_team.name}</dd>
          </div>
        </dl>
        <Button type="button" variant="secondary" onClick={onCreateAnother}>
          Create another match
        </Button>
      </div>
    </Alert>
  );
}
