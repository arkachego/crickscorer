"""Unit tests for innings scorecard aggregation."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.db.enums import DismissalType
from app.services.scorecard import (
    build_innings_scorecard_from_deliveries,
    format_overs_display,
)


def _player(
    name: str,
    *,
    batting_order: int | None = 1,
    roles: list[str] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        name=name,
        batting_order=batting_order,
        roles=[SimpleNamespace(name=role) for role in (roles or ["Batsman"])],
    )


def _delivery(
    *,
    striker: SimpleNamespace,
    non_striker: SimpleNamespace,
    bowler: SimpleNamespace,
    over_number: int = 0,
    ball_in_over: int = 1,
    bat_runs: int = 0,
    wide_runs: int = 0,
    no_ball_runs: int = 0,
    bye_runs: int = 0,
    leg_bye_runs: int = 0,
    is_legal: bool = True,
    dismissal_type: DismissalType | None = None,
    dismissed_player: SimpleNamespace | None = None,
) -> SimpleNamespace:
    total = bat_runs + wide_runs + no_ball_runs + bye_runs + leg_bye_runs
    return SimpleNamespace(
        striker=striker,
        non_striker=non_striker,
        bowler=bowler,
        striker_id=striker.id,
        non_striker_id=non_striker.id,
        bowler_id=bowler.id,
        over_number=over_number,
        ball_in_over=ball_in_over,
        bat_runs=bat_runs,
        wide_runs=wide_runs,
        no_ball_runs=no_ball_runs,
        bye_runs=bye_runs,
        leg_bye_runs=leg_bye_runs,
        total_runs=total,
        is_legal=is_legal,
        dismissal_type=dismissal_type,
        dismissed_player_id=dismissed_player.id if dismissed_player else None,
        dismissed_player=dismissed_player,
    )


def test_empty_innings_scorecard() -> None:
    opener = _player("A", batting_order=1)
    number_two = _player("B", batting_order=2)
    card = build_innings_scorecard_from_deliveries(
        deliveries=[],
        batting_players=[opener, number_two],  # type: ignore[arg-type]
    )
    assert card.batters == []
    assert card.bowlers == []
    assert card.extras.total == 0
    assert card.total_runs == 0
    assert card.wickets == 0
    assert card.overs_display == "0.0"
    assert {p.name for p in card.did_not_bat} == {"A", "B"}


def test_batter_runs_balls_boundaries_and_strike_rate() -> None:
    striker = _player("Striker", batting_order=1)
    non_striker = _player("Non", batting_order=2)
    bowler = _player("Bowler", batting_order=9, roles=["Bowler"])

    deliveries = [
        _delivery(striker=striker, non_striker=non_striker, bowler=bowler, bat_runs=4),
        _delivery(
            striker=striker,
            non_striker=non_striker,
            bowler=bowler,
            ball_in_over=2,
            bat_runs=6,
        ),
        _delivery(
            striker=striker,
            non_striker=non_striker,
            bowler=bowler,
            ball_in_over=3,
            bat_runs=1,
        ),
        # Wide: not a ball faced, no bat runs.
        _delivery(
            striker=striker,
            non_striker=non_striker,
            bowler=bowler,
            ball_in_over=4,
            wide_runs=1,
            is_legal=False,
        ),
        # No-ball with bat runs: counts as ball faced.
        _delivery(
            striker=striker,
            non_striker=non_striker,
            bowler=bowler,
            ball_in_over=4,
            bat_runs=2,
            no_ball_runs=1,
            is_legal=False,
        ),
    ]

    card = build_innings_scorecard_from_deliveries(
        deliveries=deliveries,  # type: ignore[arg-type]
        batting_players=[striker, non_striker],  # type: ignore[arg-type]
    )
    assert len(card.batters) == 2
    top = next(row for row in card.batters if row.player.name == "Striker")
    assert top.runs == 13
    assert top.balls == 4
    assert top.fours == 1
    assert top.sixes == 1
    assert top.strike_rate == 325.0
    assert top.is_not_out is True
    assert top.dismissal_text == "not out"

    non = next(row for row in card.batters if row.player.name == "Non")
    assert non.runs == 0
    assert non.balls == 0


def test_dismissal_text_mapping() -> None:
    striker = _player("Out", batting_order=1)
    non_striker = _player("Stay", batting_order=2)
    bowler = _player("Shaheen", batting_order=9, roles=["Bowler"])

    cases = [
        (DismissalType.BOWLED, "b Shaheen"),
        (DismissalType.CAUGHT, "c b Shaheen"),
        (DismissalType.LBW, "lbw b Shaheen"),
        (DismissalType.STUMPED, "st b Shaheen"),
        (DismissalType.RUN_OUT, "run out"),
        (DismissalType.HIT_WICKET, "hit wicket"),
    ]
    for dismissal_type, expected in cases:
        card = build_innings_scorecard_from_deliveries(
            deliveries=[  # type: ignore[arg-type]
                _delivery(
                    striker=striker,
                    non_striker=non_striker,
                    bowler=bowler,
                    dismissal_type=dismissal_type,
                    dismissed_player=striker,
                )
            ],
            batting_players=[striker, non_striker],  # type: ignore[arg-type]
        )
        out = next(row for row in card.batters if row.player.name == "Out")
        assert out.dismissal_text == expected
        assert out.is_not_out is False


def test_bowler_figures_maiden_and_economy() -> None:
    striker = _player("S", batting_order=1)
    non_striker = _player("N", batting_order=2)
    bowler = _player("Pace", batting_order=9, roles=["Bowler"])

    deliveries = []
    # Maiden over: 6 legal dots.
    for ball in range(1, 7):
        deliveries.append(
            _delivery(
                striker=striker,
                non_striker=non_striker,
                bowler=bowler,
                over_number=0,
                ball_in_over=ball,
                bat_runs=0,
            )
        )
    # Second over: 4 runs + one wide.
    deliveries.append(
        _delivery(
            striker=striker,
            non_striker=non_striker,
            bowler=bowler,
            over_number=1,
            ball_in_over=1,
            bat_runs=4,
        )
    )
    deliveries.append(
        _delivery(
            striker=striker,
            non_striker=non_striker,
            bowler=bowler,
            over_number=1,
            ball_in_over=2,
            wide_runs=1,
            is_legal=False,
        )
    )
    deliveries.append(
        _delivery(
            striker=striker,
            non_striker=non_striker,
            bowler=bowler,
            over_number=1,
            ball_in_over=2,
            bat_runs=0,
            dismissal_type=DismissalType.BOWLED,
            dismissed_player=striker,
        )
    )

    card = build_innings_scorecard_from_deliveries(
        deliveries=deliveries,  # type: ignore[arg-type]
        batting_players=[striker, non_striker],  # type: ignore[arg-type]
    )
    assert len(card.bowlers) == 1
    row = card.bowlers[0]
    assert row.player.name == "Pace"
    assert row.overs == "1.2"
    assert row.maidens == 1
    assert row.runs == 5  # 4 bat + 1 wide
    assert row.wickets == 1
    assert row.wides == 1
    assert row.noballs == 0
    assert row.economy == round(5 / (1 + 2 / 6), 2)


def test_extras_and_did_not_bat() -> None:
    a = _player("A", batting_order=1)
    b = _player("B", batting_order=2)
    c = _player("C", batting_order=3)
    coach = _player("Coach", batting_order=None, roles=["Coach"])
    bowler = _player("Bowl", batting_order=9, roles=["Bowler"])

    deliveries = [
        _delivery(
            striker=a,
            non_striker=b,
            bowler=bowler,
            bye_runs=1,
            is_legal=True,
        ),
        _delivery(
            striker=a,
            non_striker=b,
            bowler=bowler,
            ball_in_over=2,
            leg_bye_runs=2,
        ),
        _delivery(
            striker=a,
            non_striker=b,
            bowler=bowler,
            ball_in_over=3,
            wide_runs=1,
            is_legal=False,
        ),
        _delivery(
            striker=a,
            non_striker=b,
            bowler=bowler,
            ball_in_over=3,
            no_ball_runs=1,
            is_legal=False,
        ),
    ]
    card = build_innings_scorecard_from_deliveries(
        deliveries=deliveries,  # type: ignore[arg-type]
        batting_players=[a, b, c, coach],  # type: ignore[arg-type]
    )
    assert card.extras.byes == 1
    assert card.extras.leg_byes == 2
    assert card.extras.wides == 1
    assert card.extras.noballs == 1
    assert card.extras.total == 5
    assert [p.name for p in card.did_not_bat] == ["C"]
    assert "Coach" not in {p.name for p in card.did_not_bat}


def test_format_overs_display() -> None:
    assert format_overs_display(0) == "0.0"
    assert format_overs_display(6) == "1.0"
    assert format_overs_display(7) == "1.1"
    assert format_overs_display(44) == "7.2"


def test_run_out_does_not_credit_bowler_wicket() -> None:
    striker = _player("Out", batting_order=1)
    non_striker = _player("Stay", batting_order=2)
    bowler = _player("Bowl", batting_order=9, roles=["Bowler"])
    card = build_innings_scorecard_from_deliveries(
        deliveries=[  # type: ignore[arg-type]
            _delivery(
                striker=striker,
                non_striker=non_striker,
                bowler=bowler,
                dismissal_type=DismissalType.RUN_OUT,
                dismissed_player=striker,
            )
        ],
        batting_players=[striker, non_striker],  # type: ignore[arg-type]
    )
    assert card.bowlers[0].wickets == 0
    assert card.wickets == 1


def test_batter_rows_follow_roster_batting_order() -> None:
    """Scorecard order matches team player batting_order, not delivery appearance."""
    number_one = _player("Sahibzada Farhan", batting_order=1)
    number_two = _player("Fakhar Zaman", batting_order=2)
    number_three = _player("Saim Ayub", batting_order=3)
    bowler = _player("Bumrah", batting_order=9, roles=["Bowler"])

    # Appear on deliveries as #3 / #2 first; #1 only later as dismissal subject.
    # Roster order must still win.
    delivery_three = SimpleNamespace(
        id=number_three.id,
        name=number_three.name,
        batting_order=None,
        roles=number_three.roles,
    )
    delivery_two = SimpleNamespace(
        id=number_two.id,
        name=number_two.name,
        batting_order=None,
        roles=number_two.roles,
    )
    delivery_one = SimpleNamespace(
        id=number_one.id,
        name=number_one.name,
        batting_order=None,
        roles=number_one.roles,
    )

    card = build_innings_scorecard_from_deliveries(
        deliveries=[  # type: ignore[arg-type]
            _delivery(
                striker=delivery_three,
                non_striker=delivery_two,
                bowler=bowler,
                bat_runs=0,
            ),
            _delivery(
                striker=delivery_one,
                non_striker=delivery_two,
                bowler=bowler,
                ball_in_over=2,
                bat_runs=0,
                dismissal_type=DismissalType.BOWLED,
                dismissed_player=delivery_one,
            ),
            _delivery(
                striker=delivery_two,
                non_striker=delivery_three,
                bowler=bowler,
                ball_in_over=3,
                bat_runs=0,
            ),
        ],
        batting_players=[number_one, number_two, number_three],  # type: ignore[arg-type]
        striker_id=number_two.id,
        non_striker_id=number_three.id,
    )

    assert [row.player.name for row in card.batters] == [
        "Sahibzada Farhan",
        "Fakhar Zaman",
        "Saim Ayub",
    ]
