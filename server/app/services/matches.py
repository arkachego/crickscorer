"""Match creation, read, and lifecycle domain service."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.enums import InningsStatus, MatchFormat, MatchStatus
from app.db.models import Innings, Match, Team
from app.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.schemas.match import (
    InningsResponse,
    MatchCreateRequest,
    MatchResponse,
    TeamSummary,
)
from app.schemas.delivery import PlayerBrief

FIXED_FORMAT_OVERS: dict[MatchFormat, int] = {
    MatchFormat.T10: 10,
    MatchFormat.T20: 20,
    MatchFormat.ONE_DAY: 50,
}

CREATABLE_FORMATS = frozenset(
    {MatchFormat.T10, MatchFormat.T20, MatchFormat.ONE_DAY, MatchFormat.CUSTOM}
)

# Limited-overs CrickScorer matches have exactly two innings.
LIMITED_OVERS_INNINGS_COUNT = 2

_MATCH_LOAD_OPTIONS = (
    selectinload(Match.team_1),
    selectinload(Match.team_2),
    selectinload(Match.batting_first_team),
    selectinload(Match.innings).selectinload(Innings.batting_team),
    selectinload(Match.innings).selectinload(Innings.striker),
    selectinload(Match.innings).selectinload(Innings.non_striker),
)


def _resolve_overs(fmt: MatchFormat, overs: int | None) -> int:
    if fmt is MatchFormat.TEST:
        raise ValidationAppError(
            "TEST_FORMAT_NOT_SUPPORTED",
            "Test match creation is not supported.",
        )

    if fmt is MatchFormat.CUSTOM:
        if overs is None:
            raise ValidationAppError(
                "CUSTOM_OVERS_REQUIRED",
                "CUSTOM format requires an explicit overs value.",
            )
        if overs < 1:
            raise ValidationAppError(
                "INVALID_OVERS",
                "overs must be a positive integer.",
            )
        return overs

    expected = FIXED_FORMAT_OVERS[fmt]
    if overs is None:
        return expected
    if overs != expected:
        raise ValidationAppError(
            "INVALID_FIXED_FORMAT_OVERS",
            f"{fmt.value} matches must use exactly {expected} overs.",
        )
    return expected


def _get_team(session: Session, team_id: uuid.UUID, *, field: str) -> Team:
    team = session.scalar(select(Team).where(Team.id == team_id))
    if team is None:
        raise NotFoundError(
            "TEAM_NOT_FOUND",
            f"Team referenced by {field} was not found.",
        )
    return team


def _match_query(*, for_update: bool = False):
    stmt = select(Match).options(*_MATCH_LOAD_OPTIONS)
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return stmt


def _bowling_team(match: Match, batting_team_id: uuid.UUID) -> Team:
    if match.team_1_id == batting_team_id:
        return match.team_2
    if match.team_2_id == batting_team_id:
        return match.team_1
    raise ConflictError(
        "INVALID_INNINGS_TEAM",
        "Innings batting team is not one of the match teams.",
    )


def serialize_match(match: Match, session: Session) -> MatchResponse:
    """Build MatchResponse including derived bowling teams and scoring snapshot."""
    # Lazy import avoids circular dependency with reconstruction.
    from app.services.reconstruction import reconstruct_innings_state
    from app.services.scorecard import build_innings_scorecard

    ordered = sorted(match.innings, key=lambda item: item.innings_number)
    states = {
        innings.id: reconstruct_innings_state(session, innings, match)
        for innings in ordered
    }
    first_innings_total: int | None = None
    for innings in ordered:
        if innings.innings_number == 1:
            first_innings_total = states[innings.id].innings_total_runs
            break

    innings_payload: list[InningsResponse] = []
    for innings in ordered:
        state = states[innings.id]
        scorecard = build_innings_scorecard(session, innings)
        target = innings.target
        if target is None and innings.innings_number >= 2 and first_innings_total is not None:
            target = int(first_innings_total) + 1
        innings_payload.append(
            InningsResponse(
                id=innings.id,
                innings_number=innings.innings_number,
                batting_team=TeamSummary.model_validate(innings.batting_team),
                bowling_team=TeamSummary.model_validate(
                    _bowling_team(match, innings.batting_team_id)
                ),
                status=innings.status,
                created_at=innings.created_at,
                striker=(
                    PlayerBrief.model_validate(innings.striker)
                    if innings.striker is not None
                    else None
                ),
                non_striker=(
                    PlayerBrief.model_validate(innings.non_striker)
                    if innings.non_striker is not None
                    else None
                ),
                replacement_required=bool(innings.replacement_required),
                target=target,
                innings_total_runs=state.innings_total_runs,
                legal_delivery_count=state.legal_delivery_count,
                delivery_count=state.delivery_count,
                next_over_number=state.next_over_number,
                next_ball_in_over=state.next_ball_in_over,
                free_hit_pending=state.free_hit_pending,
                wickets=len(state.dismissed_player_ids),
                dismissed_player_ids=list(state.dismissed_player_ids),
                scorecard=scorecard,
            )
        )
    return MatchResponse(
        id=match.id,
        team_1=TeamSummary.model_validate(match.team_1),
        team_2=TeamSummary.model_validate(match.team_2),
        batting_first_team=TeamSummary.model_validate(match.batting_first_team),
        format=match.format,
        overs=match.overs if match.overs is not None else 0,
        status=match.status,
        created_at=match.created_at,
        innings=innings_payload,
    )


def list_matches(session: Session) -> list[Match]:
    """Return matches newest-first for discovery."""
    rows = session.scalars(
        _match_query().order_by(Match.created_at.desc(), Match.id.desc())
    )
    return list(rows)


def get_match(session: Session, match_id: uuid.UUID) -> Match:
    """Return a single match by id, or raise NotFoundError."""
    match = session.scalar(_match_query().where(Match.id == match_id))
    if match is None:
        raise NotFoundError(
            "MATCH_NOT_FOUND",
            "Match was not found.",
        )
    return match


def _locked_match(session: Session, match_id: uuid.UUID) -> Match:
    """Lock the match row for lifecycle mutations.

    Scoring/undo/replacement paths lock innings then match. Lifecycle start
    paths lock the match only because no innings row is being mutated yet.
    Concurrent delivery vs start races are serialised on the match row once
    the delivery path requests the match lock.
    """
    match = session.scalar(_match_query(for_update=True).where(Match.id == match_id))
    if match is None:
        raise NotFoundError(
            "MATCH_NOT_FOUND",
            "Match was not found.",
        )
    return match


def _active_innings(match: Match) -> Innings | None:
    active = [i for i in match.innings if i.status is InningsStatus.IN_PROGRESS]
    if len(active) > 1:
        raise ConflictError(
            "MULTIPLE_ACTIVE_INNINGS",
            "Match has more than one innings in progress.",
        )
    return active[0] if active else None


def _create_innings(
    session: Session,
    match: Match,
    *,
    innings_number: int,
    batting_team_id: uuid.UUID,
    target: int | None = None,
) -> Innings:
    if batting_team_id not in {match.team_1_id, match.team_2_id}:
        raise ConflictError(
            "INVALID_INNINGS_TEAM",
            "Innings batting team must be one of the match teams.",
        )
    # Ensure bowling side is resolvable.
    _bowling_team(match, batting_team_id)

    innings = Innings(
        match_id=match.id,
        batting_team_id=batting_team_id,
        innings_number=innings_number,
        status=InningsStatus.IN_PROGRESS,
        target=target,
    )
    session.add(innings)
    session.flush()
    return innings


def start_match(session: Session, match_id: uuid.UUID) -> Match:
    """CREATED → IN_PROGRESS with innings 1 started."""
    match = _locked_match(session, match_id)

    if match.status is not MatchStatus.CREATED:
        raise ConflictError(
            "INVALID_MATCH_TRANSITION",
            f"Match in status {match.status.value} cannot be started.",
        )
    if match.batting_first_team_id is None:
        raise ConflictError(
            "BATTING_FIRST_REQUIRED",
            "Match cannot start without a batting-first team.",
        )
    if match.innings:
        raise ConflictError(
            "INNINGS_ALREADY_EXIST",
            "Match already has innings and cannot be started again.",
        )

    _create_innings(
        session,
        match,
        innings_number=1,
        batting_team_id=match.batting_first_team_id,
    )
    match.status = MatchStatus.IN_PROGRESS

    try:
        session.commit()
    except Exception:
        session.rollback()
        raise

    from app.realtime import publish_match_update

    publish_match_update(match_id)

    session.expire_all()
    return get_match(session, match_id)


def start_next_innings(session: Session, match_id: uuid.UUID) -> Match:
    """INNINGS_BREAK → IN_PROGRESS with the next innings created and started."""
    match = _locked_match(session, match_id)

    if match.status is not MatchStatus.INNINGS_BREAK:
        raise ConflictError(
            "INVALID_MATCH_TRANSITION",
            f"Match in status {match.status.value} cannot start the next innings.",
        )
    if _active_innings(match) is not None:
        raise ConflictError(
            "ACTIVE_INNINGS_EXISTS",
            "Cannot start the next innings while another innings is in progress.",
        )

    completed = sorted(
        (i for i in match.innings if i.status is InningsStatus.COMPLETED),
        key=lambda item: item.innings_number,
    )
    if len(completed) != 1:
        raise ConflictError(
            "INVALID_INNINGS_SEQUENCE",
            "Next innings can only be started after exactly one completed innings.",
        )
    if len(match.innings) >= LIMITED_OVERS_INNINGS_COUNT:
        raise ConflictError(
            "MAX_INNINGS_REACHED",
            "Limited-overs matches support exactly two innings.",
        )

    first = completed[0]
    next_batting_id = (
        match.team_2_id if first.batting_team_id == match.team_1_id else match.team_1_id
    )
    from app.services.reconstruction import reconstruct_innings_state

    first_state = reconstruct_innings_state(session, first, match)
    chase_target = int(first_state.innings_total_runs) + 1
    _create_innings(
        session,
        match,
        innings_number=2,
        batting_team_id=next_batting_id,
        target=chase_target,
    )
    match.status = MatchStatus.IN_PROGRESS

    try:
        session.commit()
    except Exception:
        session.rollback()
        raise

    from app.realtime import publish_match_update

    publish_match_update(match_id)

    session.expire_all()
    return get_match(session, match_id)


def apply_innings_completion(innings: Innings, match: Match) -> None:
    """Mutate innings + match for completion. Caller owns the transaction."""
    innings.status = InningsStatus.COMPLETED
    if innings.innings_number >= LIMITED_OVERS_INNINGS_COUNT:
        match.status = MatchStatus.COMPLETED
    else:
        match.status = MatchStatus.INNINGS_BREAK


def complete_innings(session: Session, innings_id: uuid.UUID) -> Match:
    """Complete an active innings; match → INNINGS_BREAK or COMPLETED."""
    innings = session.scalar(
        select(Innings)
        .where(Innings.id == innings_id)
        .options(selectinload(Innings.match))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if innings is None:
        raise NotFoundError(
            "INNINGS_NOT_FOUND",
            "Innings was not found.",
        )

    match = _locked_match(session, innings.match_id)

    if innings.status is not InningsStatus.IN_PROGRESS:
        raise ConflictError(
            "INVALID_INNINGS_TRANSITION",
            f"Innings in status {innings.status.value} cannot be completed.",
        )
    if match.status is not MatchStatus.IN_PROGRESS:
        raise ConflictError(
            "INVALID_MATCH_TRANSITION",
            f"Match in status {match.status.value} cannot complete an innings.",
        )

    active = _active_innings(match)
    if active is None or active.id != innings.id:
        raise ConflictError(
            "INNINGS_NOT_ACTIVE",
            "Only the active innings can be completed.",
        )

    apply_innings_completion(innings, match)

    try:
        session.commit()
    except Exception:
        session.rollback()
        raise

    from app.realtime import publish_match_update

    publish_match_update(match.id)

    session.expire_all()
    return get_match(session, match.id)


def create_match(session: Session, payload: MatchCreateRequest) -> Match:
    """Validate and persist a new match with status CREATED."""
    if payload.format is MatchFormat.TEST:
        raise ValidationAppError(
            "TEST_FORMAT_NOT_SUPPORTED",
            "Test match creation is not supported in the current CrickScorer domain.",
        )

    if payload.format not in CREATABLE_FORMATS:
        raise ValidationAppError(
            "UNSUPPORTED_FORMAT",
            f"Format {payload.format.value} cannot be used to create a match.",
        )

    if payload.team_1_id == payload.team_2_id:
        raise ValidationAppError(
            "TEAMS_MUST_BE_DISTINCT",
            "team_1_id and team_2_id must refer to different teams.",
        )

    team_1 = _get_team(session, payload.team_1_id, field="team_1_id")
    team_2 = _get_team(session, payload.team_2_id, field="team_2_id")

    participating = {team_1.id, team_2.id}
    if payload.batting_first_team_id not in participating:
        batting_first = session.scalar(
            select(Team).where(Team.id == payload.batting_first_team_id)
        )
        if batting_first is None:
            raise NotFoundError(
                "TEAM_NOT_FOUND",
                "Team referenced by batting_first_team_id was not found.",
            )
        raise ValidationAppError(
            "BATTING_FIRST_NOT_IN_MATCH",
            "batting_first_team_id must be either team_1_id or team_2_id.",
        )

    overs = _resolve_overs(payload.format, payload.overs)

    match = Match(
        team_1_id=team_1.id,
        team_2_id=team_2.id,
        batting_first_team_id=payload.batting_first_team_id,
        format=payload.format,
        overs=overs,
        status=MatchStatus.CREATED,
    )
    session.add(match)
    try:
        session.flush()
        match_id = match.id
        session.commit()
    except Exception:
        session.rollback()
        raise

    session.expire_all()
    created = get_match(session, match_id)
    if created.batting_first_team is None:
        raise RuntimeError("Created match could not be reloaded")
    return created
