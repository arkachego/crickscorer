"""Innings batting/bowling scorecard aggregation from deliveries."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.enums import DismissalType
from app.db.models import Delivery, Innings, Player
from app.schemas.delivery import PlayerBrief
from app.schemas.match import (
    BatterScorecardRow,
    BowlerScorecardRow,
    ExtrasBreakdown,
    InningsScorecard,
)
from app.services.strike_rotation import LEGAL_BALLS_PER_OVER

ROLE_COACH = "Coach"

BOWLER_CREDITED_DISMISSALS = frozenset(
    {
        DismissalType.BOWLED,
        DismissalType.CAUGHT,
        DismissalType.LBW,
        DismissalType.STUMPED,
        DismissalType.HIT_WICKET,
    }
)


def format_overs_display(legal_delivery_count: int) -> str:
    overs = legal_delivery_count // LEGAL_BALLS_PER_OVER
    balls = legal_delivery_count % LEGAL_BALLS_PER_OVER
    return f"{overs}.{balls}"


def overs_as_decimal(legal_delivery_count: int) -> float:
    overs = legal_delivery_count // LEGAL_BALLS_PER_OVER
    balls = legal_delivery_count % LEGAL_BALLS_PER_OVER
    return overs + (balls / LEGAL_BALLS_PER_OVER)


def _strike_rate(runs: int, balls: int) -> float:
    if balls <= 0:
        return 0.0
    return round((runs / balls) * 100, 2)


def _economy(runs: int, legal_balls: int) -> float:
    decimal = overs_as_decimal(legal_balls)
    if decimal <= 0:
        return 0.0
    return round(runs / decimal, 2)


def _dismissal_text(
    dismissal_type: DismissalType,
    *,
    bowler_name: str,
) -> str:
    if dismissal_type is DismissalType.BOWLED:
        return f"b {bowler_name}"
    if dismissal_type is DismissalType.CAUGHT:
        return f"c b {bowler_name}"
    if dismissal_type is DismissalType.LBW:
        return f"lbw b {bowler_name}"
    if dismissal_type is DismissalType.STUMPED:
        return f"st b {bowler_name}"
    if dismissal_type is DismissalType.RUN_OUT:
        return "run out"
    if dismissal_type is DismissalType.HIT_WICKET:
        return "hit wicket"
    return dismissal_type.value.replace("_", " ").lower()


def _role_names(player: Player) -> set[str]:
    return {role.name for role in player.roles}


def _is_batting_xi(player: Player) -> bool:
    if player.batting_order is None:
        return False
    if ROLE_COACH in _role_names(player):
        return False
    return True


def _player_brief(player: Player) -> PlayerBrief:
    return PlayerBrief.model_validate(player)


def _chargeable_bowler_runs(delivery: Delivery) -> int:
    return (
        int(delivery.bat_runs)
        + int(delivery.wide_runs)
        + int(delivery.no_ball_runs)
    )


@dataclass
class _BatterAgg:
    player: Player
    runs: int = 0
    balls: int = 0
    fours: int = 0
    sixes: int = 0
    dismissal_type: DismissalType | None = None
    dismissal_bowler_name: str | None = None


@dataclass
class _BowlerAgg:
    player: Player
    legal_balls: int = 0
    runs: int = 0
    wickets: int = 0
    noballs: int = 0
    wides: int = 0
    over_runs: dict[int, int] = field(default_factory=dict)
    over_legal: dict[int, int] = field(default_factory=dict)


def build_innings_scorecard_from_deliveries(
    *,
    deliveries: list[Delivery],
    batting_players: list[Player],
    striker_id: uuid.UUID | None = None,
    non_striker_id: uuid.UUID | None = None,
) -> InningsScorecard:
    """Aggregate batting/bowling figures from an ordered delivery list."""
    batters: dict[uuid.UUID, _BatterAgg] = {}
    bowlers: dict[uuid.UUID, _BowlerAgg] = {}
    players_by_id = {player.id: player for player in batting_players}
    roster_order = {
        player.id: index for index, player in enumerate(batting_players)
    }

    def resolve_player(player: Player) -> Player:
        """Prefer roster row so batting_order matches the team player list."""
        return players_by_id.get(player.id, player)

    def ensure_batter(player: Player) -> _BatterAgg:
        resolved = resolve_player(player)
        agg = batters.get(resolved.id)
        if agg is None:
            agg = _BatterAgg(player=resolved)
            batters[resolved.id] = agg
        return agg

    def ensure_bowler(player: Player) -> _BowlerAgg:
        agg = bowlers.get(player.id)
        if agg is None:
            agg = _BowlerAgg(player=player)
            bowlers[player.id] = agg
        return agg

    byes = 0
    leg_byes = 0
    wides = 0
    noballs = 0
    total_runs = 0
    legal_count = 0
    dismissed_ids: set[uuid.UUID] = set()

    for delivery in deliveries:
        total_runs += int(delivery.total_runs)
        byes += int(delivery.bye_runs)
        leg_byes += int(delivery.leg_bye_runs)
        wides += int(delivery.wide_runs)
        noballs += int(delivery.no_ball_runs)
        if delivery.is_legal:
            legal_count += 1

        striker = delivery.striker
        non_striker = delivery.non_striker
        bowler = delivery.bowler

        ensure_batter(striker)
        ensure_batter(non_striker)
        batter = ensure_batter(striker)

        is_wide = int(delivery.wide_runs) > 0
        if not is_wide:
            batter.balls += 1
            bat_runs = int(delivery.bat_runs)
            batter.runs += bat_runs
            if bat_runs == 4:
                batter.fours += 1
            elif bat_runs == 6:
                batter.sixes += 1

        bowl = ensure_bowler(bowler)
        chargeable = _chargeable_bowler_runs(delivery)
        bowl.runs += chargeable
        if int(delivery.wide_runs) > 0:
            bowl.wides += 1
        if int(delivery.no_ball_runs) > 0:
            bowl.noballs += 1
        if delivery.is_legal:
            bowl.legal_balls += 1
            bowl.over_legal[delivery.over_number] = (
                bowl.over_legal.get(delivery.over_number, 0) + 1
            )
        bowl.over_runs[delivery.over_number] = (
            bowl.over_runs.get(delivery.over_number, 0) + chargeable
        )

        if (
            delivery.dismissed_player_id is not None
            and delivery.dismissal_type is not None
        ):
            dismissed_id = delivery.dismissed_player_id
            dismissed_ids.add(dismissed_id)
            dismissed_player = delivery.dismissed_player
            if dismissed_player is None:
                dismissed_player = players_by_id.get(dismissed_id)
            if dismissed_player is not None:
                dismissed_agg = ensure_batter(dismissed_player)
                dismissed_agg.dismissal_type = delivery.dismissal_type
                dismissed_agg.dismissal_bowler_name = bowler.name
            if delivery.dismissal_type in BOWLER_CREDITED_DISMISSALS:
                bowl.wickets += 1

    for player_id in (striker_id, non_striker_id):
        if player_id is None:
            continue
        player = players_by_id.get(player_id)
        if player is not None:
            ensure_batter(player)

    batter_rows: list[BatterScorecardRow] = []
    for agg in sorted(
        batters.values(),
        key=lambda item: (
            roster_order.get(
                item.player.id,
                10_000 + (item.player.batting_order or 10_000),
            ),
            item.player.batting_order is None,
            item.player.batting_order or 10_000,
            item.player.name,
        ),
    ):
        is_not_out = agg.dismissal_type is None
        if is_not_out:
            dismissal_text = "not out"
        else:
            dismissal_text = _dismissal_text(
                agg.dismissal_type,  # type: ignore[arg-type]
                bowler_name=agg.dismissal_bowler_name or "?",
            )
        batter_rows.append(
            BatterScorecardRow(
                player=_player_brief(agg.player),
                dismissal_text=dismissal_text,
                is_not_out=is_not_out,
                runs=agg.runs,
                balls=agg.balls,
                fours=agg.fours,
                sixes=agg.sixes,
                strike_rate=_strike_rate(agg.runs, agg.balls),
            )
        )

    batted_ids = set(batters.keys())
    did_not_bat = [
        _player_brief(player)
        for player in sorted(
            (
                player
                for player in batting_players
                if _is_batting_xi(player) and player.id not in batted_ids
            ),
            key=lambda item: (item.batting_order or 10_000, item.name),
        )
    ]

    bowler_rows: list[BowlerScorecardRow] = []
    # Preserve first-appearance order from deliveries.
    bowler_order = list(bowlers.keys())
    for bowler_id in bowler_order:
        agg = bowlers[bowler_id]
        maidens = 0
        for over_number, legal_in_over in agg.over_legal.items():
            if (
                legal_in_over >= LEGAL_BALLS_PER_OVER
                and agg.over_runs.get(over_number, 0) == 0
            ):
                maidens += 1
        bowler_rows.append(
            BowlerScorecardRow(
                player=_player_brief(agg.player),
                overs=format_overs_display(agg.legal_balls),
                maidens=maidens,
                runs=agg.runs,
                wickets=agg.wickets,
                noballs=agg.noballs,
                wides=agg.wides,
                economy=_economy(agg.runs, agg.legal_balls),
            )
        )

    decimal_overs = overs_as_decimal(legal_count)
    run_rate = round(total_runs / decimal_overs, 2) if decimal_overs > 0 else 0.0

    return InningsScorecard(
        batters=batter_rows,
        extras=ExtrasBreakdown(
            byes=byes,
            leg_byes=leg_byes,
            wides=wides,
            noballs=noballs,
            total=byes + leg_byes + wides + noballs,
        ),
        did_not_bat=did_not_bat,
        bowlers=bowler_rows,
        total_runs=total_runs,
        wickets=len(dismissed_ids),
        overs_display=format_overs_display(legal_count),
        run_rate=run_rate,
    )


def build_innings_scorecard(
    session: Session,
    innings: Innings,
    *,
    deliveries: list[Delivery] | None = None,
) -> InningsScorecard:
    """Load deliveries + batting XI and build the innings scorecard."""
    if deliveries is None:
        deliveries = list(
            session.scalars(
                select(Delivery)
                .where(Delivery.innings_id == innings.id)
                .options(
                    selectinload(Delivery.striker),
                    selectinload(Delivery.non_striker),
                    selectinload(Delivery.bowler),
                    selectinload(Delivery.dismissed_player),
                )
                .order_by(Delivery.sequence_no.asc(), Delivery.id.asc())
            )
        )

    batting_players = list(
        session.scalars(
            select(Player)
            .where(Player.team_id == innings.batting_team_id)
            .options(selectinload(Player.roles))
            .order_by(Player.batting_order.asc().nulls_last(), Player.name.asc())
        )
    )

    return build_innings_scorecard_from_deliveries(
        deliveries=deliveries,
        batting_players=batting_players,
        striker_id=innings.striker_id,
        non_striker_id=innings.non_striker_id,
    )
