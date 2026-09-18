import type { Team } from "@/lib/api/types";

type TeamOptionContentProps = {
  team: Team;
};

/** Flag left, name centre, short code flush right — used in selects + trigger. */
export function TeamOptionContent({ team }: TeamOptionContentProps) {
  return (
    <span className="flex w-full min-w-0 items-center gap-2.5">
      <img
        src={team.flag_url}
        alt=""
        width={24}
        height={16}
        className="h-4 w-6 shrink-0 rounded-[2px] object-cover ring-1 ring-[var(--color-line)]"
      />
      <span className="min-w-0 flex-1 truncate text-left">{team.name}</span>
      <span className="shrink-0 text-xs font-semibold tracking-wide text-[var(--color-muted)]">
        {team.short_code}
      </span>
    </span>
  );
}

export function teamOptionTextValue(team: Team): string {
  return `${team.name} (${team.short_code})`;
}
