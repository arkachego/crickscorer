"""Scoring engine — deliveries, extras, Free Hit, wickets, replacement (Phase 11).

Score is derived from persisted deliveries (sum of total_runs).
Active batters live on innings.striker_id / non_striker_id.
After each non-wicket delivery the server rotates strike for odd
crossing runs and again at the end of an over.
Over numbering is zero-based. sequence_no counts every delivery;
ball_in_over advances on legal deliveries only.

Free Hit is derived from the previous delivery's no_ball_runs > 0.
Dismissed players are derived from deliveries.dismissed_player_id.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.enums import DeliveryType, DismissalType, InningsStatus, MatchStatus
from app.db.models import BatterReplacement, Delivery, Innings, Match, Player
from app.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.schemas.delivery import (
    PHASE_11_DISMISSAL_TYPES,
    VALID_BAT_RUNS,
    DeliveryCreateRequest,
    DeliveryHistoryItem,
    DeliveryResponse,
    PlayerBrief,
    ReplacementRequest,
    WicketInfo,
)
from app.schemas.match import MatchResponse
from app.services.matches import apply_innings_completion, get_match, serialize_match
from app.services.strike_rotation import (
    LEGAL_BALLS_PER_OVER,
    crossing_runs_for_rotation,
    max_legal_deliveries,
    next_delivery_position,
    rotate_strike_ids,
)

ROLE_BOWLER = "Bowler"
ROLE_COACH = "Coach"

# NORMAL allows these; NO_BALL allows only RUN_OUT. WIDE/BYE/LEG_BYE reject wickets.
NORMAL_WICKET_TYPES = PHASE_11_DISMISSAL_TYPES
NO_BALL_WICKET_TYPES = frozenset({DismissalType.RUN_OUT})


@dataclass(frozen=True, slots=True)
class ResolvedOutcome:
    delivery_type: DeliveryType
    bat_runs: int
    wide_runs: int
    no_ball_runs: int
    bye_runs: int
    leg_bye_runs: int
    total_runs: int
    is_legal: bool


def _apply_strike_rotation(
    innings: Innings,
    outcome: ResolvedOutcome,
    *,
    ended_over: bool,
) -> None:
    """Update innings active pair for the next delivery."""
    if innings.striker_id is None or innings.non_striker_id is None:
        return
    if innings.replacement_required:
        return
    next_striker, next_non = rotate_strike_ids(
        innings.striker_id,
        innings.non_striker_id,
        crossing_runs=crossing_runs_for_rotation(
            bat_runs=outcome.bat_runs,
            wide_runs=outcome.wide_runs,
            bye_runs=outcome.bye_runs,
            leg_bye_runs=outcome.leg_bye_runs,
        ),
        ended_over=ended_over,
    )
    innings.striker_id = next_striker
    innings.non_striker_id = next_non


def derive_delivery_type(delivery: Delivery) -> DeliveryType:
    """Recover mutually exclusive outcome from persisted extra/bat fields."""
    if delivery.wide_runs > 0:
        return DeliveryType.WIDE
    if delivery.no_ball_runs > 0:
        return DeliveryType.NO_BALL
    if delivery.bye_runs > 0:
        return DeliveryType.BYE
    if delivery.leg_bye_runs > 0:
        return DeliveryType.LEG_BYE
    return DeliveryType.NORMAL


def resolve_outcome(payload: DeliveryCreateRequest) -> ResolvedOutcome:
    """Map a validated request into persisted run components."""
    dtype = payload.delivery_type

    if dtype is DeliveryType.NORMAL:
        bat = int(payload.bat_runs)
        if bat not in VALID_BAT_RUNS:
            raise ValidationAppError(
                "INVALID_BAT_RUNS",
                "bat_runs must be one of 0, 1, 2, 3, 4, or 6.",
            )
        return ResolvedOutcome(
            delivery_type=dtype,
            bat_runs=bat,
            wide_runs=0,
            no_ball_runs=0,
            bye_runs=0,
            leg_bye_runs=0,
            total_runs=bat,
            is_legal=True,
        )

    if dtype is DeliveryType.WIDE:
        if payload.bat_runs != 0:
            raise ValidationAppError(
                "INVALID_DELIVERY_COMBINATION",
                "WIDE deliveries cannot include bat runs.",
            )
        if payload.extra_runs is None or payload.extra_runs < 1:
            raise ValidationAppError(
                "INVALID_EXTRA_RUNS",
                "WIDE deliveries require extra_runs >= 1.",
            )
        wide = int(payload.extra_runs)
        return ResolvedOutcome(
            delivery_type=dtype,
            bat_runs=0,
            wide_runs=wide,
            no_ball_runs=0,
            bye_runs=0,
            leg_bye_runs=0,
            total_runs=wide,
            is_legal=False,
        )

    if dtype is DeliveryType.NO_BALL:
        bat = int(payload.bat_runs)
        if bat not in VALID_BAT_RUNS:
            raise ValidationAppError(
                "INVALID_BAT_RUNS",
                "bat_runs must be one of 0, 1, 2, 3, 4, or 6.",
            )
        if payload.extra_runs is not None:
            raise ValidationAppError(
                "INVALID_DELIVERY_COMBINATION",
                "NO_BALL penalty is server-enforced; do not send extra_runs.",
            )
        return ResolvedOutcome(
            delivery_type=dtype,
            bat_runs=bat,
            wide_runs=0,
            no_ball_runs=1,
            bye_runs=0,
            leg_bye_runs=0,
            total_runs=1 + bat,
            is_legal=False,
        )

    if dtype is DeliveryType.BYE:
        if payload.bat_runs != 0:
            raise ValidationAppError(
                "INVALID_DELIVERY_COMBINATION",
                "BYE deliveries cannot include bat runs.",
            )
        if payload.extra_runs is None or payload.extra_runs < 1:
            raise ValidationAppError(
                "INVALID_EXTRA_RUNS",
                "BYE deliveries require extra_runs >= 1.",
            )
        bye = int(payload.extra_runs)
        return ResolvedOutcome(
            delivery_type=dtype,
            bat_runs=0,
            wide_runs=0,
            no_ball_runs=0,
            bye_runs=bye,
            leg_bye_runs=0,
            total_runs=bye,
            is_legal=True,
        )

    if dtype is DeliveryType.LEG_BYE:
        if payload.bat_runs != 0:
            raise ValidationAppError(
                "INVALID_DELIVERY_COMBINATION",
                "LEG_BYE deliveries cannot include bat runs.",
            )
        if payload.extra_runs is None or payload.extra_runs < 1:
            raise ValidationAppError(
                "INVALID_EXTRA_RUNS",
                "LEG_BYE deliveries require extra_runs >= 1.",
            )
        leg = int(payload.extra_runs)
        return ResolvedOutcome(
            delivery_type=dtype,
            bat_runs=0,
            wide_runs=0,
            no_ball_runs=0,
            bye_runs=0,
            leg_bye_runs=leg,
            total_runs=leg,
            is_legal=True,
        )

    raise ValidationAppError(
        "INVALID_DELIVERY_TYPE",
        f"Unsupported delivery_type: {dtype}",
    )


def _role_names(player: Player) -> set[str]:
    return {role.name for role in player.roles}


def _get_player(session: Session, player_id: uuid.UUID, *, field: str) -> Player:
    player = session.scalar(
        select(Player)
        .where(Player.id == player_id)
        .options(selectinload(Player.roles))
    )
    if player is None:
        raise NotFoundError(
            "PLAYER_NOT_FOUND",
            f"Player referenced by {field} was not found.",
        )
    return player


def _reject_coach(player: Player, *, field: str) -> None:
    if ROLE_COACH in _role_names(player):
        raise ValidationAppError(
            "COACH_NOT_ALLOWED",
            f"{field} cannot be a coach.",
        )


def _require_playing_xi(player: Player, *, field: str) -> None:
    """Playing-XI membership (batting_order IS NOT NULL), not Batsman role."""
    if player.batting_order is None:
        raise ValidationAppError(
            "PLAYER_NOT_ELIGIBLE",
            f"{field} must be a playing-XI member (non-null batting_order).",
        )
    if ROLE_COACH in _role_names(player):
        raise ValidationAppError(
            "COACH_NOT_ALLOWED",
            f"{field} cannot be a coach.",
        )


def _require_bowler(player: Player, *, field: str) -> None:
    if ROLE_BOWLER not in _role_names(player):
        raise ValidationAppError(
            "PLAYER_NOT_BOWLER",
            f"{field} must have the Bowler role.",
        )


def _bowling_team_id(match: Match, batting_team_id: uuid.UUID) -> uuid.UUID:
    if match.team_1_id == batting_team_id:
        return match.team_2_id
    if match.team_2_id == batting_team_id:
        return match.team_1_id
    raise ConflictError(
        "INVALID_INNINGS_TEAM",
        "Innings batting team is not one of the match teams.",
    )


def _innings_total_runs(session: Session, innings_id: uuid.UUID) -> int:
    total = session.scalar(
        select(func.coalesce(func.sum(Delivery.total_runs), 0)).where(
            Delivery.innings_id == innings_id
        )
    )
    return int(total or 0)


def _legal_delivery_count(session: Session, innings_id: uuid.UUID) -> int:
    count = session.scalar(
        select(func.count())
        .select_from(Delivery)
        .where(Delivery.innings_id == innings_id, Delivery.is_legal.is_(True))
    )
    return int(count or 0)


def _delivery_count(session: Session, innings_id: uuid.UUID) -> int:
    count = session.scalar(
        select(func.count())
        .select_from(Delivery)
        .where(Delivery.innings_id == innings_id)
    )
    return int(count or 0)


def _pending_free_hit(session: Session, innings_id: uuid.UUID) -> bool:
    previous_no_ball = session.scalar(
        select(Delivery.no_ball_runs)
        .where(Delivery.innings_id == innings_id)
        .order_by(Delivery.sequence_no.desc())
        .limit(1)
    )
    return previous_no_ball is not None and int(previous_no_ball) > 0


def _dismissed_player_ids(session: Session, innings_id: uuid.UUID) -> set[uuid.UUID]:
    rows = session.scalars(
        select(Delivery.dismissed_player_id).where(
            Delivery.innings_id == innings_id,
            Delivery.dismissed_player_id.is_not(None),
        )
    )
    return {pid for pid in rows if pid is not None}


def _active_batter_ids(innings: Innings) -> set[uuid.UUID]:
    ids: set[uuid.UUID] = set()
    if innings.striker_id is not None:
        ids.add(innings.striker_id)
    if innings.non_striker_id is not None:
        ids.add(innings.non_striker_id)
    return ids


def _batting_team_players(session: Session, batting_team_id: uuid.UUID) -> list[Player]:
    return list(
        session.scalars(
            select(Player)
            .where(Player.team_id == batting_team_id)
            .options(selectinload(Player.roles))
        )
    )


def _is_eligible_batter(
    player: Player,
    *,
    dismissed: set[uuid.UUID],
    active: set[uuid.UUID],
) -> bool:
    """Playing-XI eligibility: batting_order set, not coach/dismissed/active."""
    if player.batting_order is None:
        return False
    roles = _role_names(player)
    if ROLE_COACH in roles:
        return False
    if player.id in dismissed:
        return False
    if player.id in active:
        return False
    return True


def _eligible_replacements(
    session: Session,
    innings: Innings,
) -> list[Player]:
    dismissed = _dismissed_player_ids(session, innings.id)
    active = _active_batter_ids(innings)
    return [
        p
        for p in _batting_team_players(session, innings.batting_team_id)
        if _is_eligible_batter(p, dismissed=dismissed, active=active)
    ]


def _validate_wicket_for_delivery(
    *,
    delivery_type: DeliveryType,
    dismissal_type: DismissalType,
    is_free_hit: bool,
) -> None:
    if is_free_hit:
        raise ConflictError(
            "WICKET_NOT_ALLOWED_ON_FREE_HIT",
            "Wickets are not allowed on a Free Hit delivery.",
        )
    if dismissal_type not in PHASE_11_DISMISSAL_TYPES:
        raise ValidationAppError(
            "INVALID_DISMISSAL_TYPE",
            f"Dismissal type {dismissal_type.value} is not supported in Phase 11.",
        )
    if delivery_type is DeliveryType.NORMAL:
        if dismissal_type not in NORMAL_WICKET_TYPES:
            raise ValidationAppError(
                "INVALID_DISMISSAL_TYPE",
                f"{dismissal_type.value} is not allowed on NORMAL deliveries.",
            )
        return
    if delivery_type is DeliveryType.NO_BALL:
        if dismissal_type not in NO_BALL_WICKET_TYPES:
            raise ValidationAppError(
                "INVALID_DISMISSAL_TYPE",
                "Only RUN_OUT is allowed on NO_BALL deliveries in Phase 11.",
            )
        return
    raise ValidationAppError(
        "WICKET_NOT_ALLOWED_FOR_DELIVERY_TYPE",
        f"Wickets are not allowed on {delivery_type.value} deliveries.",
    )


def _apply_active_pair_from_request(innings: Innings, payload: DeliveryCreateRequest) -> None:
    """Set or sync active batters from the delivery request."""
    if innings.striker_id is None and innings.non_striker_id is None:
        innings.striker_id = payload.striker_id
        innings.non_striker_id = payload.non_striker_id
        return

    active = _active_batter_ids(innings)
    requested = {payload.striker_id, payload.non_striker_id}
    if active != requested:
        raise ValidationAppError(
            "PLAYER_NOT_ACTIVE",
            "striker_id and non_striker_id must be the current active batting pair.",
        )
    # Sync strike assignment from client for this delivery (who faced the ball).
    innings.striker_id = payload.striker_id
    innings.non_striker_id = payload.non_striker_id


def _apply_wicket_to_active_state(
    session: Session,
    innings: Innings,
    match: Match,
    dismissed_id: uuid.UUID,
) -> None:
    """Clear dismissed slot; all-out or set replacement_required."""
    if innings.striker_id == dismissed_id:
        innings.striker_id = None
    elif innings.non_striker_id == dismissed_id:
        innings.non_striker_id = None
    else:
        raise ValidationAppError(
            "PLAYER_NOT_ACTIVE",
            "Dismissed player must be the current striker or non-striker.",
        )

    remaining = _active_batter_ids(innings)
    if len(remaining) != 1:
        raise ConflictError(
            "INVALID_ACTIVE_BATTERS",
            "After a wicket exactly one active batter must remain.",
        )

    if _eligible_replacements(session, innings):
        innings.replacement_required = True
    else:
        innings.replacement_required = False
        apply_innings_completion(innings, match)


def list_innings_deliveries(
    session: Session,
    innings_id: uuid.UUID,
) -> list[DeliveryHistoryItem]:
    """Return chronological delivery history for Admin recent-history display."""
    innings = session.get(Innings, innings_id)
    if innings is None:
        raise NotFoundError("INNINGS_NOT_FOUND", "Innings was not found.")

    rows = list(
        session.scalars(
            select(Delivery)
            .where(Delivery.innings_id == innings_id)
            .options(
                selectinload(Delivery.striker),
                selectinload(Delivery.non_striker),
                selectinload(Delivery.bowler),
                selectinload(Delivery.dismissed_player),
            )
            .order_by(Delivery.sequence_no.asc(), Delivery.id.asc())
        )
    )
    items: list[DeliveryHistoryItem] = []
    for row in rows:
        wicket_info: WicketInfo | None = None
        if (
            row.dismissed_player_id is not None
            and row.dismissal_type is not None
            and row.dismissed_player is not None
        ):
            wicket_info = WicketInfo(
                dismissed_player=PlayerBrief.model_validate(row.dismissed_player),
                dismissal_type=row.dismissal_type,
            )
        items.append(
            DeliveryHistoryItem(
                id=row.id,
                sequence_no=row.sequence_no,
                over_number=row.over_number,
                ball_in_over=row.ball_in_over,
                delivery_type=derive_delivery_type(row),
                bat_runs=row.bat_runs,
                wide_runs=row.wide_runs,
                no_ball_runs=row.no_ball_runs,
                bye_runs=row.bye_runs,
                leg_bye_runs=row.leg_bye_runs,
                total_runs=row.total_runs,
                is_legal=row.is_legal,
                is_free_hit=row.is_free_hit,
                striker=PlayerBrief.model_validate(row.striker),
                non_striker=PlayerBrief.model_validate(row.non_striker),
                bowler=PlayerBrief.model_validate(row.bowler),
                wicket=wicket_info,
            )
        )
    return items


def submit_delivery(
    session: Session,
    innings_id: uuid.UUID,
    payload: DeliveryCreateRequest,
) -> DeliveryResponse:
    """Validate, persist one delivery, apply wicket/replacement/all-out rules."""
    outcome = resolve_outcome(payload)

    innings = session.scalar(
        select(Innings)
        .where(Innings.id == innings_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if innings is None:
        raise NotFoundError(
            "INNINGS_NOT_FOUND",
            "Innings was not found.",
        )

    match = session.scalar(
        select(Match)
        .where(Match.id == innings.match_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if match is None:
        raise NotFoundError(
            "MATCH_NOT_FOUND",
            "Match was not found.",
        )

    if innings.status is not InningsStatus.IN_PROGRESS:
        raise ConflictError(
            "INVALID_INNINGS_TRANSITION",
            f"Innings in status {innings.status.value} cannot accept deliveries.",
        )
    if match.status is not MatchStatus.IN_PROGRESS:
        raise ConflictError(
            "INVALID_MATCH_TRANSITION",
            f"Match in status {match.status.value} cannot accept deliveries.",
        )

    if innings.replacement_required:
        raise ConflictError(
            "REPLACEMENT_REQUIRED",
            "A replacement batter must be selected before the next delivery.",
        )

    if payload.striker_id == payload.non_striker_id:
        raise ValidationAppError(
            "STRIKER_EQUALS_NON_STRIKER",
            "striker_id and non_striker_id must be different players.",
        )

    striker = _get_player(session, payload.striker_id, field="striker_id")
    non_striker = _get_player(session, payload.non_striker_id, field="non_striker_id")
    bowler = _get_player(session, payload.bowler_id, field="bowler_id")

    batting_team_id = innings.batting_team_id
    bowling_team_id = _bowling_team_id(match, batting_team_id)

    if striker.team_id != batting_team_id:
        raise ValidationAppError(
            "INVALID_STRIKER_TEAM",
            "striker_id must belong to the batting team.",
        )
    if non_striker.team_id != batting_team_id:
        raise ValidationAppError(
            "INVALID_NON_STRIKER_TEAM",
            "non_striker_id must belong to the batting team.",
        )
    if bowler.team_id != bowling_team_id:
        raise ValidationAppError(
            "INVALID_BOWLER_TEAM",
            "bowler_id must belong to the bowling team.",
        )

    _reject_coach(striker, field="striker_id")
    _reject_coach(non_striker, field="non_striker_id")
    _reject_coach(bowler, field="bowler_id")
    _require_playing_xi(striker, field="striker_id")
    _require_playing_xi(non_striker, field="non_striker_id")
    _require_bowler(bowler, field="bowler_id")

    dismissed = _dismissed_player_ids(session, innings.id)
    if payload.striker_id in dismissed or payload.non_striker_id in dismissed:
        raise ValidationAppError(
            "PLAYER_ALREADY_DISMISSED",
            "A dismissed player cannot bat again in this innings.",
        )

    _apply_active_pair_from_request(innings, payload)

    if match.overs is None or match.overs < 1:
        raise ConflictError(
            "INVALID_MATCH_OVERS",
            "Match does not have a valid overs configuration.",
        )

    prior_legal = _legal_delivery_count(session, innings.id)
    prior_total = _delivery_count(session, innings.id)
    max_legal = max_legal_deliveries(match.overs)
    if prior_legal >= max_legal:
        raise ConflictError(
            "INNINGS_OVERS_COMPLETE",
            "Innings has already reached the configured overs.",
        )

    sequence_no, over_number, ball_in_over = next_delivery_position(
        delivery_count=prior_total,
        legal_count=prior_legal,
    )
    is_free_hit = _pending_free_hit(session, innings.id)

    dismissal_type: DismissalType | None = None
    dismissed_player_id: uuid.UUID | None = None
    dismissed_player: Player | None = None

    if payload.wicket is not None:
        _validate_wicket_for_delivery(
            delivery_type=outcome.delivery_type,
            dismissal_type=payload.wicket.dismissal_type,
            is_free_hit=is_free_hit,
        )
        dismissed_player_id = payload.wicket.dismissed_player_id
        if dismissed_player_id not in {payload.striker_id, payload.non_striker_id}:
            raise ValidationAppError(
                "PLAYER_NOT_ACTIVE",
                "dismissed_player_id must be the striker or non-striker.",
            )
        if dismissed_player_id in dismissed:
            raise ValidationAppError(
                "PLAYER_ALREADY_DISMISSED",
                "Player has already been dismissed in this innings.",
            )
        dismissed_player = (
            striker if dismissed_player_id == striker.id else non_striker
        )
        _reject_coach(dismissed_player, field="dismissed_player_id")
        dismissal_type = payload.wicket.dismissal_type

    delivery = Delivery(
        innings_id=innings.id,
        sequence_no=sequence_no,
        over_number=over_number,
        ball_in_over=ball_in_over,
        striker_id=striker.id,
        non_striker_id=non_striker.id,
        bowler_id=bowler.id,
        bat_runs=outcome.bat_runs,
        wide_runs=outcome.wide_runs,
        no_ball_runs=outcome.no_ball_runs,
        bye_runs=outcome.bye_runs,
        leg_bye_runs=outcome.leg_bye_runs,
        total_runs=outcome.total_runs,
        is_legal=outcome.is_legal,
        is_free_hit=is_free_hit,
        dismissal_type=dismissal_type,
        dismissed_player_id=dismissed_player_id,
    )
    session.add(delivery)
    session.flush()

    overs_complete = outcome.is_legal and prior_legal + 1 >= max_legal
    ended_over = outcome.is_legal and ball_in_over == LEGAL_BALLS_PER_OVER

    if dismissed_player_id is not None:
        if overs_complete:
            # Final legal ball ends the innings; no replacement needed.
            if innings.striker_id == dismissed_player_id:
                innings.striker_id = None
            elif innings.non_striker_id == dismissed_player_id:
                innings.non_striker_id = None
            innings.replacement_required = False
            apply_innings_completion(innings, match)
        else:
            _apply_wicket_to_active_state(session, innings, match, dismissed_player_id)
    elif overs_complete:
        apply_innings_completion(innings, match)
    else:
        _apply_strike_rotation(innings, outcome, ended_over=ended_over)

    try:
        session.commit()
    except Exception:
        session.rollback()
        raise

    from app.realtime import publish_match_update_from_innings

    publish_match_update_from_innings(session, innings_id)

    session.expire_all()

    persisted = session.scalar(
        select(Delivery)
        .where(Delivery.id == delivery.id)
        .options(
            selectinload(Delivery.striker),
            selectinload(Delivery.non_striker),
            selectinload(Delivery.bowler),
            selectinload(Delivery.dismissed_player),
        )
    )
    if persisted is None:
        raise RuntimeError("Delivery could not be reloaded after commit")

    refreshed_innings = session.get(Innings, innings_id)
    refreshed_match = get_match(session, match.id)
    if refreshed_innings is None:
        raise RuntimeError("Innings could not be reloaded after commit")

    wicket_info: WicketInfo | None = None
    if (
        persisted.dismissed_player_id is not None
        and persisted.dismissal_type is not None
        and persisted.dismissed_player is not None
    ):
        wicket_info = WicketInfo(
            dismissed_player=PlayerBrief.model_validate(persisted.dismissed_player),
            dismissal_type=persisted.dismissal_type,
        )

    return DeliveryResponse(
        id=persisted.id,
        innings_id=persisted.innings_id,
        sequence_no=persisted.sequence_no,
        over_number=persisted.over_number,
        ball_in_over=persisted.ball_in_over,
        striker=PlayerBrief.model_validate(persisted.striker),
        non_striker=PlayerBrief.model_validate(persisted.non_striker),
        bowler=PlayerBrief.model_validate(persisted.bowler),
        delivery_type=derive_delivery_type(persisted),
        bat_runs=persisted.bat_runs,
        wide_runs=persisted.wide_runs,
        no_ball_runs=persisted.no_ball_runs,
        bye_runs=persisted.bye_runs,
        leg_bye_runs=persisted.leg_bye_runs,
        total_runs=persisted.total_runs,
        is_legal=persisted.is_legal,
        is_free_hit=persisted.is_free_hit,
        wicket=wicket_info,
        innings_status=refreshed_innings.status,
        match_status=refreshed_match.status,
        innings_total_runs=_innings_total_runs(session, innings_id),
        replacement_required=bool(refreshed_innings.replacement_required),
    )


def submit_replacement(
    session: Session,
    innings_id: uuid.UUID,
    payload: ReplacementRequest,
) -> MatchResponse:
    """Fill the vacant active-batter slot after a wicket."""
    innings = session.scalar(
        select(Innings)
        .where(Innings.id == innings_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if innings is None:
        raise NotFoundError(
            "INNINGS_NOT_FOUND",
            "Innings was not found.",
        )

    match = session.scalar(
        select(Match)
        .where(Match.id == innings.match_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if match is None:
        raise NotFoundError(
            "MATCH_NOT_FOUND",
            "Match was not found.",
        )

    if innings.status is not InningsStatus.IN_PROGRESS:
        raise ConflictError(
            "INVALID_INNINGS_TRANSITION",
            f"Innings in status {innings.status.value} cannot accept a replacement.",
        )
    if match.status is not MatchStatus.IN_PROGRESS:
        raise ConflictError(
            "INVALID_MATCH_TRANSITION",
            f"Match in status {match.status.value} cannot accept a replacement.",
        )
    if not innings.replacement_required:
        raise ConflictError(
            "REPLACEMENT_NOT_REQUIRED",
            "No replacement is currently required for this innings.",
        )

    vacant_striker = innings.striker_id is None
    vacant_non_striker = innings.non_striker_id is None
    if vacant_striker == vacant_non_striker:
        raise ConflictError(
            "INVALID_ACTIVE_BATTERS",
            "Replacement requires exactly one vacant active-batter slot.",
        )

    player = _get_player(session, payload.player_id, field="player_id")
    if player.team_id != innings.batting_team_id:
        raise ValidationAppError(
            "PLAYER_NOT_ELIGIBLE",
            "Replacement must belong to the batting team.",
        )
    _reject_coach(player, field="player_id")
    _require_playing_xi(player, field="player_id")

    dismissed = _dismissed_player_ids(session, innings.id)
    active = _active_batter_ids(innings)
    if not _is_eligible_batter(player, dismissed=dismissed, active=active):
        if player.id in dismissed:
            raise ValidationAppError(
                "PLAYER_ALREADY_DISMISSED",
                "A dismissed player cannot be a replacement.",
            )
        if player.id in active:
            raise ValidationAppError(
                "PLAYER_NOT_ELIGIBLE",
                "Replacement cannot already be an active batter.",
            )
        raise ValidationAppError(
            "PLAYER_NOT_ELIGIBLE",
            "Player is not eligible as a replacement batter.",
        )

    if vacant_striker:
        innings.striker_id = player.id
    else:
        innings.non_striker_id = player.id
    innings.replacement_required = False

    wicket_delivery = session.scalar(
        select(Delivery)
        .where(
            Delivery.innings_id == innings.id,
            Delivery.dismissed_player_id.is_not(None),
        )
        .order_by(Delivery.sequence_no.desc(), Delivery.id.desc())
        .limit(1)
    )
    if wicket_delivery is None:
        raise ConflictError(
            "WICKET_NOT_FOUND",
            "No wicket delivery found for this replacement.",
        )
    session.add(
        BatterReplacement(
            innings_id=innings.id,
            wicket_delivery_id=wicket_delivery.id,
            player_id=player.id,
            fills_striker_slot=vacant_striker,
        )
    )

    try:
        session.commit()
    except Exception:
        session.rollback()
        raise

    from app.realtime import publish_match_update

    publish_match_update(match.id)

    session.expire_all()
    return serialize_match(get_match(session, match.id), session)
