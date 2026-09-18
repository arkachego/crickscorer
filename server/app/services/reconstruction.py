"""Innings state reconstruction and undo (Phase 12).

Persisted deliveries (+ batter_replacements) are the event history.
innings/match projection fields are rebuilt from that history.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.db.enums import InningsStatus, MatchStatus
from app.db.models import BatterReplacement, Delivery, Innings, Match, Player
from app.exceptions import ConflictError, NotFoundError
from app.schemas.match import MatchResponse, UndoResponse
from app.services.matches import (
    LIMITED_OVERS_INNINGS_COUNT,
    get_match,
    serialize_match,
)
from app.services.strike_rotation import (
    LEGAL_BALLS_PER_OVER,
    crossing_runs_for_rotation,
    max_legal_deliveries,
    next_delivery_position,
    rotate_strike_ids,
)

ROLE_COACH = "Coach"


@dataclass(slots=True)
class ReconstructedInningsState:
    striker_id: uuid.UUID | None
    non_striker_id: uuid.UUID | None
    replacement_required: bool
    innings_status: InningsStatus
    delivery_count: int
    legal_delivery_count: int
    innings_total_runs: int
    next_over_number: int
    next_ball_in_over: int
    free_hit_pending: bool
    dismissed_player_ids: list[uuid.UUID]


def _role_names(player: Player) -> set[str]:
    return {role.name for role in player.roles}


def _is_eligible_batter(
    player: Player,
    *,
    dismissed: set[uuid.UUID],
    active: set[uuid.UUID],
) -> bool:
    if player.batting_order is None:
        return False
    if ROLE_COACH in _role_names(player):
        return False
    if player.id in dismissed or player.id in active:
        return False
    return True


def _playing_xi_players(session: Session, batting_team_id: uuid.UUID) -> list[Player]:
    return list(
        session.scalars(
            select(Player)
            .where(
                Player.team_id == batting_team_id,
                Player.batting_order.is_not(None),
            )
            .options(selectinload(Player.roles))
        )
    )


def _has_eligible_replacement(
    *,
    xi: list[Player],
    dismissed: set[uuid.UUID],
    active: set[uuid.UUID],
) -> bool:
    return any(_is_eligible_batter(p, dismissed=dismissed, active=active) for p in xi)


def reconstruct_innings_state(
    session: Session,
    innings: Innings,
    match: Match,
) -> ReconstructedInningsState:
    """Rebuild innings projection from deliveries + batter_replacements."""
    deliveries = list(
        session.scalars(
            select(Delivery)
            .where(Delivery.innings_id == innings.id)
            .order_by(Delivery.sequence_no.asc(), Delivery.id.asc())
        )
    )
    replacements = {
        row.wicket_delivery_id: row
        for row in session.scalars(
            select(BatterReplacement).where(BatterReplacement.innings_id == innings.id)
        )
    }
    xi = _playing_xi_players(session, innings.batting_team_id)
    max_legal = max_legal_deliveries(match.overs or 0)

    striker_id: uuid.UUID | None = None
    non_striker_id: uuid.UUID | None = None
    replacement_required = False
    dismissed: set[uuid.UUID] = set()
    legal_count = 0
    total_runs = 0
    completed_all_out = False

    for delivery in deliveries:
        total_runs += int(delivery.total_runs)

        # Who faced this ball (explicit on the delivery row).
        if striker_id is None and non_striker_id is None:
            striker_id = delivery.striker_id
            non_striker_id = delivery.non_striker_id
        elif not replacement_required:
            striker_id = delivery.striker_id
            non_striker_id = delivery.non_striker_id

        if delivery.is_legal:
            legal_count += 1

        if delivery.dismissed_player_id is not None and not completed_all_out:
            dismissed_id = delivery.dismissed_player_id
            dismissed.add(dismissed_id)
            if striker_id == dismissed_id:
                striker_id = None
            elif non_striker_id == dismissed_id:
                non_striker_id = None

            active = {x for x in (striker_id, non_striker_id) if x is not None}
            if _has_eligible_replacement(xi=xi, dismissed=dismissed, active=active):
                replacement_required = True
                repl = replacements.get(delivery.id)
                if repl is not None:
                    if repl.fills_striker_slot:
                        striker_id = repl.player_id
                    else:
                        non_striker_id = repl.player_id
                    replacement_required = False
            else:
                replacement_required = False
                completed_all_out = True
        elif (
            striker_id is not None
            and non_striker_id is not None
            and not replacement_required
            and not (max_legal > 0 and legal_count >= max_legal)
        ):
            # Rotate for the next ball (odd crossing runs + end of over).
            ended_over = bool(delivery.is_legal) and (
                legal_count % LEGAL_BALLS_PER_OVER == 0
            )
            striker_id, non_striker_id = rotate_strike_ids(
                striker_id,
                non_striker_id,
                crossing_runs=crossing_runs_for_rotation(
                    bat_runs=delivery.bat_runs,
                    wide_runs=delivery.wide_runs,
                    bye_runs=delivery.bye_runs,
                    leg_bye_runs=delivery.leg_bye_runs,
                ),
                ended_over=ended_over,
            )

        if max_legal > 0 and legal_count >= max_legal:
            replacement_required = False
            # Overs complete — do not leave vacancy open.
            break

        if completed_all_out:
            break

    delivery_count = len(deliveries)
    free_hit_pending = bool(deliveries) and int(deliveries[-1].no_ball_runs) > 0

    if delivery_count == 0:
        # Preserve Phase 8 post-start: started innings stay IN_PROGRESS.
        status = (
            InningsStatus.IN_PROGRESS
            if innings.status is not InningsStatus.NOT_STARTED
            else InningsStatus.NOT_STARTED
        )
        return ReconstructedInningsState(
            striker_id=None,
            non_striker_id=None,
            replacement_required=False,
            innings_status=status,
            delivery_count=0,
            legal_delivery_count=0,
            innings_total_runs=0,
            next_over_number=0,
            next_ball_in_over=1,
            free_hit_pending=False,
            dismissed_player_ids=[],
        )

    overs_complete = max_legal > 0 and legal_count >= max_legal
    if completed_all_out or overs_complete:
        status = InningsStatus.COMPLETED
        if overs_complete:
            replacement_required = False
    else:
        status = InningsStatus.IN_PROGRESS

    _, next_over, next_ball = next_delivery_position(
        delivery_count=delivery_count,
        legal_count=min(legal_count, max_legal) if max_legal else legal_count,
    )
    # When overs complete, next position is past the last legal ball.
    if overs_complete:
        next_over = legal_count // LEGAL_BALLS_PER_OVER
        next_ball = LEGAL_BALLS_PER_OVER

    return ReconstructedInningsState(
        striker_id=striker_id,
        non_striker_id=non_striker_id,
        replacement_required=replacement_required,
        innings_status=status,
        delivery_count=delivery_count,
        legal_delivery_count=legal_count,
        innings_total_runs=total_runs,
        next_over_number=next_over,
        next_ball_in_over=next_ball,
        free_hit_pending=free_hit_pending and status is InningsStatus.IN_PROGRESS,
        dismissed_player_ids=sorted(dismissed, key=str),
    )


def derive_match_status(innings_list: list[Innings]) -> MatchStatus:
    if any(i.status is InningsStatus.IN_PROGRESS for i in innings_list):
        return MatchStatus.IN_PROGRESS
    completed = [i for i in innings_list if i.status is InningsStatus.COMPLETED]
    if len(completed) >= LIMITED_OVERS_INNINGS_COUNT:
        return MatchStatus.COMPLETED
    if len(completed) == 1:
        return MatchStatus.INNINGS_BREAK
    return MatchStatus.CREATED


def apply_reconstructed_state(
    innings: Innings, state: ReconstructedInningsState
) -> None:
    innings.striker_id = state.striker_id
    innings.non_striker_id = state.non_striker_id
    innings.replacement_required = state.replacement_required
    innings.status = state.innings_status


def undo_latest_delivery(session: Session, innings_id: uuid.UUID) -> UndoResponse:
    """Delete the latest delivery and rebuild innings/match projections."""
    innings = session.scalar(
        select(Innings)
        .where(Innings.id == innings_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if innings is None:
        raise NotFoundError("INNINGS_NOT_FOUND", "Innings was not found.")

    match = session.scalar(
        select(Match)
        .where(Match.id == innings.match_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if match is None:
        raise NotFoundError("MATCH_NOT_FOUND", "Match was not found.")

    if innings.status is InningsStatus.NOT_STARTED:
        raise ConflictError(
            "INVALID_INNINGS_STATE",
            "Cannot undo a NOT_STARTED innings.",
        )

    # Do not undo innings 1 after innings 2 exists.
    sibling_innings = list(
        session.scalars(select(Innings).where(Innings.match_id == match.id))
    )
    if innings.innings_number == 1 and any(i.innings_number > 1 for i in sibling_innings):
        raise ConflictError(
            "INVALID_UNDO_STATE",
            "Cannot undo innings 1 after a later innings has started.",
        )

    latest = session.scalar(
        select(Delivery)
        .where(Delivery.innings_id == innings.id)
        .order_by(Delivery.sequence_no.desc(), Delivery.id.desc())
        .limit(1)
    )
    if latest is None:
        raise ConflictError(
            "NO_DELIVERY_TO_UNDO",
            "There is no delivery to undo for this innings.",
        )

    # CASCADE removes batter_replacements tied to this wicket delivery.
    session.execute(delete(Delivery).where(Delivery.id == latest.id))
    session.flush()

    state = reconstruct_innings_state(session, innings, match)
    apply_reconstructed_state(innings, state)
    session.flush()

    all_innings = list(
        session.scalars(
            select(Innings)
            .where(Innings.match_id == match.id)
            .execution_options(populate_existing=True)
        )
    )
    match.status = derive_match_status(all_innings)

    try:
        session.commit()
    except Exception:
        session.rollback()
        raise

    from app.realtime import publish_match_update

    publish_match_update(match.id)

    session.expire_all()
    match_payload = serialize_match(get_match(session, match.id), session)
    return UndoResponse(
        match=match_payload,
        innings_id=innings_id,
        delivery_count=state.delivery_count,
        legal_delivery_count=state.legal_delivery_count,
        innings_total_runs=state.innings_total_runs,
        next_over_number=state.next_over_number,
        next_ball_in_over=state.next_ball_in_over,
        free_hit_pending=state.free_hit_pending,
        replacement_required=state.replacement_required,
        innings_status=state.innings_status,
        match_status=match_payload.status,
        striker=(
            next(
                (
                    inn.striker
                    for inn in match_payload.innings
                    if inn.id == innings_id
                ),
                None,
            )
        ),
        non_striker=(
            next(
                (
                    inn.non_striker
                    for inn in match_payload.innings
                    if inn.id == innings_id
                ),
                None,
            )
        ),
    )
