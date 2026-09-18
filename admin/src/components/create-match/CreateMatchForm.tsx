import {
  useEffect,
  useId,
  useMemo,
  useState,
  type FormEvent,
} from "react";
import { MatchSuccess } from "@/components/create-match/MatchSuccess";
import {
  TeamOptionContent,
  teamOptionTextValue,
} from "@/components/create-match/TeamOptionContent";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useCreateMatch } from "@/hooks/use-create-match";
import { useTeams } from "@/hooks/use-teams";
import {
  ApiError,
  CREATABLE_FORMATS,
  FIXED_FORMAT_OVERS,
  oversForFormat,
  type Match,
  type MatchFormat,
} from "@/lib/api/types";
import { cn } from "@/lib/utils";

type FormErrors = {
  team_1_id?: string;
  team_2_id?: string;
  format?: string;
  batting_first_team_id?: string;
  overs?: string;
  form?: string;
};

const INITIAL_FORMAT: MatchFormat = "T20";

export function CreateMatchForm() {
  const formId = useId();
  const teamsQuery = useTeams();
  const createMatch = useCreateMatch();

  const [team1Id, setTeam1Id] = useState("");
  const [team2Id, setTeam2Id] = useState("");
  const [format, setFormat] = useState<MatchFormat>(INITIAL_FORMAT);
  const [battingFirstId, setBattingFirstId] = useState("");
  const [customOvers, setCustomOvers] = useState("");
  const [errors, setErrors] = useState<FormErrors>({});
  const [createdMatch, setCreatedMatch] = useState<Match | null>(null);

  const teams = teamsQuery.data ?? [];

  const team1Options = useMemo(
    () => teams.filter((team) => team.id !== team2Id),
    [teams, team2Id],
  );
  const team2Options = useMemo(
    () => teams.filter((team) => team.id !== team1Id),
    [teams, team1Id],
  );
  const battingFirstOptions = useMemo(
    () => teams.filter((team) => team.id === team1Id || team.id === team2Id),
    [teams, team1Id, team2Id],
  );

  useEffect(() => {
    if (
      battingFirstId &&
      !battingFirstOptions.some((team) => team.id === battingFirstId)
    ) {
      setBattingFirstId("");
    }
  }, [battingFirstId, battingFirstOptions]);

  const fixedOvers = format === "CUSTOM" ? null : FIXED_FORMAT_OVERS[format];

  function validate(): FormErrors {
    const next: FormErrors = {};

    if (!team1Id) next.team_1_id = "Team 1 is required.";
    if (!team2Id) next.team_2_id = "Team 2 is required.";
    if (team1Id && team2Id && team1Id === team2Id) {
      next.team_2_id = "Team 1 and Team 2 must be different.";
    }
    if (!format) next.format = "Format is required.";
    if (!battingFirstId) {
      next.batting_first_team_id = "Batting first team is required.";
    } else if (battingFirstId !== team1Id && battingFirstId !== team2Id) {
      next.batting_first_team_id =
        "Batting first must be one of the selected teams.";
    }

    if (format === "CUSTOM") {
      const trimmed = customOvers.trim();
      if (!trimmed) {
        next.overs = "Custom format requires an overs value.";
      } else if (!/^\d+$/.test(trimmed)) {
        next.overs = "Overs must be a whole number.";
      } else if (Number.parseInt(trimmed, 10) < 1) {
        next.overs = "Overs must be a positive integer.";
      }
    }

    return next;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (createMatch.isPending) return;

    const nextErrors = validate();
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) return;

    const overs = oversForFormat(format, customOvers);
    if (overs === null || overs < 1) {
      setErrors({ overs: "Overs must be a positive integer." });
      return;
    }

    try {
      const match = await createMatch.mutateAsync({
        team_1_id: team1Id,
        team_2_id: team2Id,
        format,
        batting_first_team_id: battingFirstId,
        overs,
      });
      setCreatedMatch(match);
      setErrors({});
    } catch (error) {
      const message =
        error instanceof ApiError
          ? error.message
          : "Unable to create the match. Please try again.";
      setErrors({ form: message });
      if (import.meta.env.DEV && !import.meta.env.MODE.includes("test")) {
        console.error("Match creation failed", error);
      }
    }
  }

  function resetForAnother() {
    setCreatedMatch(null);
    setTeam1Id("");
    setTeam2Id("");
    setFormat(INITIAL_FORMAT);
    setBattingFirstId("");
    setCustomOvers("");
    setErrors({});
    createMatch.reset();
  }

  if (createdMatch) {
    return (
      <section className="space-y-6" aria-label="Create Match">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight text-[var(--color-pitch-deep)]">
            Create Match
          </h2>
          <p className="mt-1 text-sm text-[var(--color-muted)]">
            Choose two teams, a limited-overs format, and who bats first.
          </p>
        </div>
        <MatchSuccess match={createdMatch} onCreateAnother={resetForAnother} />
      </section>
    );
  }

  return (
    <section className="space-y-6" aria-label="Create Match">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight text-[var(--color-pitch-deep)]">
          Create Match
        </h2>
        <p className="mt-1 text-sm text-[var(--color-muted)]">
          Choose two teams, a limited-overs format, and who bats first.
        </p>
      </div>

      <div className="rounded-xl border border-[var(--color-line)] bg-white/90 p-5 shadow-sm sm:p-7">
      {teamsQuery.isLoading ? (
        <p role="status" className="text-sm text-[var(--color-muted)]">
          Loading teams…
        </p>
      ) : null}

      {teamsQuery.isError ? (
        <Alert tone="error" title="Unable to load teams">
          {(teamsQuery.error instanceof ApiError
            ? teamsQuery.error.message
            : null) || "Please refresh and try again."}
        </Alert>
      ) : null}

      {teamsQuery.isSuccess ? (
        <form
          noValidate
          onSubmit={handleSubmit}
          className="space-y-5"
          aria-busy={createMatch.isPending}
        >
          <fieldset disabled={createMatch.isPending} className="space-y-5">
            <legend className="sr-only">Match details</legend>

            <div>
              <Label htmlFor={`${formId}-team1`}>Team 1</Label>
              <Select
                value={team1Id || undefined}
                disabled={createMatch.isPending}
                onValueChange={(value) => {
                  setTeam1Id(value);
                  setErrors((prev) => ({
                    ...prev,
                    team_1_id: undefined,
                    form: undefined,
                  }));
                }}
              >
                <SelectTrigger
                  id={`${formId}-team1`}
                  aria-invalid={Boolean(errors.team_1_id)}
                  aria-describedby={
                    errors.team_1_id ? `${formId}-team1-error` : undefined
                  }
                >
                  <SelectValue placeholder="Select team" />
                </SelectTrigger>
                <SelectContent>
                  {team1Options.map((team) => (
                    <SelectItem
                      key={team.id}
                      value={team.id}
                      textValue={teamOptionTextValue(team)}
                    >
                      <TeamOptionContent team={team} />
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {errors.team_1_id ? (
                <p
                  id={`${formId}-team1-error`}
                  className="mt-1 text-sm text-[var(--color-danger)]"
                >
                  {errors.team_1_id}
                </p>
              ) : null}
            </div>

            <div>
              <Label htmlFor={`${formId}-team2`}>Team 2</Label>
              <Select
                value={team2Id || undefined}
                disabled={createMatch.isPending}
                onValueChange={(value) => {
                  setTeam2Id(value);
                  setErrors((prev) => ({
                    ...prev,
                    team_2_id: undefined,
                    form: undefined,
                  }));
                }}
              >
                <SelectTrigger
                  id={`${formId}-team2`}
                  aria-invalid={Boolean(errors.team_2_id)}
                  aria-describedby={
                    errors.team_2_id ? `${formId}-team2-error` : undefined
                  }
                >
                  <SelectValue placeholder="Select team" />
                </SelectTrigger>
                <SelectContent>
                  {team2Options.map((team) => (
                    <SelectItem
                      key={team.id}
                      value={team.id}
                      textValue={teamOptionTextValue(team)}
                    >
                      <TeamOptionContent team={team} />
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {errors.team_2_id ? (
                <p
                  id={`${formId}-team2-error`}
                  className="mt-1 text-sm text-[var(--color-danger)]"
                >
                  {errors.team_2_id}
                </p>
              ) : null}
            </div>

            <div>
              <Label htmlFor={`${formId}-format`}>Format</Label>
              <Select
                value={format}
                disabled={createMatch.isPending}
                onValueChange={(value) => {
                  const next = value as MatchFormat;
                  setFormat(next);
                  if (next === "CUSTOM") {
                    setCustomOvers("5");
                  }
                  setErrors((prev) => ({
                    ...prev,
                    format: undefined,
                    overs: undefined,
                    form: undefined,
                  }));
                }}
              >
                <SelectTrigger
                  id={`${formId}-format`}
                  aria-invalid={Boolean(errors.format)}
                >
                  <SelectValue placeholder="Select format" />
                </SelectTrigger>
                <SelectContent>
                  {CREATABLE_FORMATS.map((item) => (
                    <SelectItem key={item.value} value={item.value}>
                      {item.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {errors.format ? (
                <p className="mt-1 text-sm text-[var(--color-danger)]">
                  {errors.format}
                </p>
              ) : null}
            </div>

            <div>
              <Label htmlFor={`${formId}-overs`}>Overs</Label>
              {format === "CUSTOM" ? (
                <Input
                  id={`${formId}-overs`}
                  name="overs"
                  type="number"
                  min={1}
                  step={1}
                  value={customOvers}
                  aria-invalid={Boolean(errors.overs)}
                  aria-describedby={
                    errors.overs
                      ? `${formId}-overs-error ${formId}-overs-hint`
                      : `${formId}-overs-hint`
                  }
                  onChange={(event) => {
                    setCustomOvers(event.target.value);
                    setErrors((prev) => ({
                      ...prev,
                      overs: undefined,
                      form: undefined,
                    }));
                  }}
                />
              ) : (
                <Input
                  id={`${formId}-overs`}
                  name="overs"
                  value={String(fixedOvers)}
                  readOnly
                  aria-readonly="true"
                  aria-describedby={`${formId}-overs-fixed`}
                />
              )}
              {format === "CUSTOM" ? (
                <p
                  id={`${formId}-overs-hint`}
                  className="mt-1 text-sm text-[var(--color-muted)]"
                >
                  Custom format needs a positive whole number of overs.
                </p>
              ) : (
                <p
                  id={`${formId}-overs-fixed`}
                  className="mt-1 text-sm text-[var(--color-muted)]"
                >
                  Overs are fixed for {format === "ONE_DAY" ? "One Day" : format}.
                </p>
              )}
              {errors.overs ? (
                <p
                  id={`${formId}-overs-error`}
                  className="mt-1 text-sm text-[var(--color-danger)]"
                >
                  {errors.overs}
                </p>
              ) : null}
            </div>

            <div>
              <Label htmlFor={`${formId}-batting`}>Batting first</Label>
              <Select
                value={battingFirstId || undefined}
                disabled={
                  createMatch.isPending || !team1Id || !team2Id
                }
                onValueChange={(value) => {
                  setBattingFirstId(value);
                  setErrors((prev) => ({
                    ...prev,
                    batting_first_team_id: undefined,
                    form: undefined,
                  }));
                }}
              >
                <SelectTrigger
                  id={`${formId}-batting`}
                  aria-invalid={Boolean(errors.batting_first_team_id)}
                  aria-describedby={
                    errors.batting_first_team_id
                      ? `${formId}-batting-error`
                      : undefined
                  }
                >
                  <SelectValue
                    placeholder={
                      !team1Id || !team2Id
                        ? "Select both teams first"
                        : "Select batting first team"
                    }
                  />
                </SelectTrigger>
                <SelectContent>
                  {battingFirstOptions.map((team) => (
                    <SelectItem
                      key={team.id}
                      value={team.id}
                      textValue={teamOptionTextValue(team)}
                    >
                      <TeamOptionContent team={team} />
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {errors.batting_first_team_id ? (
                <p
                  id={`${formId}-batting-error`}
                  className="mt-1 text-sm text-[var(--color-danger)]"
                >
                  {errors.batting_first_team_id}
                </p>
              ) : null}
            </div>
          </fieldset>

          {errors.form ? (
            <Alert tone="error" title="Could not create match">
              {errors.form}
            </Alert>
          ) : null}

          <div className="pt-1">
            <Button
              type="submit"
              disabled={createMatch.isPending || teams.length < 2}
              className={cn(createMatch.isPending && "cursor-wait")}
              aria-live="polite"
            >
              {createMatch.isPending ? "Creating match…" : "Create Match"}
            </Button>
          </div>
        </form>
      ) : null}
      </div>
    </section>
  );
}
