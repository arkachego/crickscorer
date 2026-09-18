"""Initial CrickScorer domain schema (squashed single revision).

Revision ID: 20260918_0001
Revises:
Create Date: 2026-09-18

Creates the complete current schema in one step:

  teams, roles, players, player_role,
  matches, innings (incl. active-batter columns), deliveries,
  batter_replacements

All entity primary keys: uuid PRIMARY KEY DEFAULT uuidv7().
Roles are relational (roles + player_role M2M) — no player role enum.
Foreign keys use ON DELETE RESTRICT.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260918_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

match_format = postgresql.ENUM(
    "T10",
    "T20",
    "ONE_DAY",
    "CUSTOM",
    "TEST",
    name="match_format",
    create_type=False,
)
match_status = postgresql.ENUM(
    "CREATED",
    "IN_PROGRESS",
    "INNINGS_BREAK",
    "COMPLETED",
    name="match_status",
    create_type=False,
)
innings_status = postgresql.ENUM(
    "NOT_STARTED",
    "IN_PROGRESS",
    "COMPLETED",
    name="innings_status",
    create_type=False,
)
dismissal_type = postgresql.ENUM(
    "BOWLED",
    "CAUGHT",
    "LBW",
    "STUMPED",
    "RUN_OUT",
    "HIT_WICKET",
    name="dismissal_type",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    match_format.create(bind, checkfirst=True)
    match_status.create(bind, checkfirst=True)
    innings_status.create(bind, checkfirst=True)
    dismissal_type.create(bind, checkfirst=True)

    op.create_table(
        "teams",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("short_code", sa.String(length=8), nullable=False),
        sa.Column("flag_url", sa.String(length=512), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_teams"),
        sa.UniqueConstraint("name", name="uq_teams_name"),
        sa.UniqueConstraint("short_code", name="uq_teams_short_code"),
    )

    op.create_table(
        "roles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_roles"),
        sa.UniqueConstraint("name", name="uq_roles_name"),
    )

    op.create_table(
        "players",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("batting_order", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "batting_order IS NULL OR batting_order >= 1",
            name="ck_players_batting_order_positive",
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
            name="fk_players_team_id_teams",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_players"),
        sa.UniqueConstraint(
            "team_id",
            "batting_order",
            name="uq_players_team_batting_order",
        ),
        sa.UniqueConstraint("team_id", "name", name="uq_players_team_name"),
    )
    op.create_index("ix_players_team_id", "players", ["team_id"])

    op.create_table(
        "player_role",
        sa.Column("player_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
            name="fk_player_role_player_id_players",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            name="fk_player_role_role_id_roles",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("player_id", "role_id", name="pk_player_role"),
    )

    op.create_table(
        "matches",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column("team_1_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_2_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "batting_first_team_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("format", match_format, nullable=False),
        sa.Column("overs", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            match_status,
            server_default=sa.text("'CREATED'::match_status"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "team_1_id <> team_2_id",
            name="ck_matches_different_teams",
        ),
        sa.CheckConstraint(
            "overs IS NULL OR overs > 0",
            name="ck_matches_overs_positive",
        ),
        sa.ForeignKeyConstraint(
            ["team_1_id"],
            ["teams.id"],
            name="fk_matches_team_1_id_teams",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["team_2_id"],
            ["teams.id"],
            name="fk_matches_team_2_id_teams",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["batting_first_team_id"],
            ["teams.id"],
            name="fk_matches_batting_first_team_id_teams",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_matches"),
    )
    op.create_index("ix_matches_team_1_id", "matches", ["team_1_id"])
    op.create_index("ix_matches_team_2_id", "matches", ["team_2_id"])
    op.create_index(
        "ix_matches_batting_first_team_id",
        "matches",
        ["batting_first_team_id"],
    )

    op.create_table(
        "innings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column("match_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batting_team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("innings_number", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            innings_status,
            server_default=sa.text("'NOT_STARTED'::innings_status"),
            nullable=False,
        ),
        sa.Column("target", sa.Integer(), nullable=True),
        sa.Column("striker_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("non_striker_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "replacement_required",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "innings_number >= 1",
            name="ck_innings_number_positive",
        ),
        sa.CheckConstraint(
            "target IS NULL OR target >= 0",
            name="ck_innings_target_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["match_id"],
            ["matches.id"],
            name="fk_innings_match_id_matches",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["batting_team_id"],
            ["teams.id"],
            name="fk_innings_batting_team_id_teams",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["striker_id"],
            ["players.id"],
            name="fk_innings_striker_id_players",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["non_striker_id"],
            ["players.id"],
            name="fk_innings_non_striker_id_players",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_innings"),
        sa.UniqueConstraint(
            "match_id",
            "innings_number",
            name="uq_innings_match_number",
        ),
    )
    op.create_index("ix_innings_match_id", "innings", ["match_id"])
    op.create_index("ix_innings_batting_team_id", "innings", ["batting_team_id"])
    op.create_index("ix_innings_striker_id", "innings", ["striker_id"])
    op.create_index("ix_innings_non_striker_id", "innings", ["non_striker_id"])

    op.create_table(
        "deliveries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column("innings_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("over_number", sa.Integer(), nullable=False),
        sa.Column("ball_in_over", sa.Integer(), nullable=False),
        sa.Column("striker_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("non_striker_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bowler_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "bat_runs",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "wide_runs",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "no_ball_runs",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "bye_runs",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "leg_bye_runs",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "total_runs",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "is_legal",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "is_free_hit",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("dismissal_type", dismissal_type, nullable=True),
        sa.Column(
            "dismissed_player_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "sequence_no >= 1",
            name="ck_deliveries_sequence_positive",
        ),
        sa.CheckConstraint(
            "over_number >= 0",
            name="ck_deliveries_over_non_negative",
        ),
        sa.CheckConstraint(
            "ball_in_over >= 1",
            name="ck_deliveries_ball_positive",
        ),
        sa.CheckConstraint(
            "bat_runs >= 0",
            name="ck_deliveries_bat_runs_non_negative",
        ),
        sa.CheckConstraint(
            "wide_runs >= 0",
            name="ck_deliveries_wide_runs_non_negative",
        ),
        sa.CheckConstraint(
            "no_ball_runs >= 0",
            name="ck_deliveries_no_ball_runs_non_negative",
        ),
        sa.CheckConstraint(
            "bye_runs >= 0",
            name="ck_deliveries_bye_runs_non_negative",
        ),
        sa.CheckConstraint(
            "leg_bye_runs >= 0",
            name="ck_deliveries_leg_bye_runs_non_negative",
        ),
        sa.CheckConstraint(
            "total_runs >= 0",
            name="ck_deliveries_total_runs_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["innings_id"],
            ["innings.id"],
            name="fk_deliveries_innings_id_innings",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["striker_id"],
            ["players.id"],
            name="fk_deliveries_striker_id_players",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["non_striker_id"],
            ["players.id"],
            name="fk_deliveries_non_striker_id_players",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["bowler_id"],
            ["players.id"],
            name="fk_deliveries_bowler_id_players",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dismissed_player_id"],
            ["players.id"],
            name="fk_deliveries_dismissed_player_id_players",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_deliveries"),
        sa.UniqueConstraint(
            "innings_id",
            "sequence_no",
            name="uq_deliveries_innings_sequence",
        ),
    )
    op.create_index("ix_deliveries_innings_id", "deliveries", ["innings_id"])
    op.create_index("ix_deliveries_striker_id", "deliveries", ["striker_id"])
    op.create_index("ix_deliveries_non_striker_id", "deliveries", ["non_striker_id"])
    op.create_index("ix_deliveries_bowler_id", "deliveries", ["bowler_id"])
    op.create_index(
        "ix_deliveries_dismissed_player_id",
        "deliveries",
        ["dismissed_player_id"],
    )

    op.create_table(
        "batter_replacements",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column("innings_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("wicket_delivery_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("player_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fills_striker_slot", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["innings_id"],
            ["innings.id"],
            name="fk_batter_replacements_innings_id_innings",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["wicket_delivery_id"],
            ["deliveries.id"],
            name="fk_batter_replacements_wicket_delivery_id_deliveries",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
            name="fk_batter_replacements_player_id_players",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_batter_replacements"),
        sa.UniqueConstraint(
            "innings_id",
            "wicket_delivery_id",
            name="uq_batter_replacements_innings_wicket",
        ),
    )
    op.create_index(
        "ix_batter_replacements_innings_id",
        "batter_replacements",
        ["innings_id"],
    )
    op.create_index(
        "ix_batter_replacements_wicket_delivery_id",
        "batter_replacements",
        ["wicket_delivery_id"],
    )
    op.create_index(
        "ix_batter_replacements_player_id",
        "batter_replacements",
        ["player_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_batter_replacements_player_id", table_name="batter_replacements")
    op.drop_index(
        "ix_batter_replacements_wicket_delivery_id",
        table_name="batter_replacements",
    )
    op.drop_index("ix_batter_replacements_innings_id", table_name="batter_replacements")
    op.drop_table("batter_replacements")

    op.drop_index("ix_deliveries_dismissed_player_id", table_name="deliveries")
    op.drop_index("ix_deliveries_bowler_id", table_name="deliveries")
    op.drop_index("ix_deliveries_non_striker_id", table_name="deliveries")
    op.drop_index("ix_deliveries_striker_id", table_name="deliveries")
    op.drop_index("ix_deliveries_innings_id", table_name="deliveries")
    op.drop_table("deliveries")

    op.drop_index("ix_innings_non_striker_id", table_name="innings")
    op.drop_index("ix_innings_striker_id", table_name="innings")
    op.drop_index("ix_innings_batting_team_id", table_name="innings")
    op.drop_index("ix_innings_match_id", table_name="innings")
    op.drop_table("innings")

    op.drop_index("ix_matches_batting_first_team_id", table_name="matches")
    op.drop_index("ix_matches_team_2_id", table_name="matches")
    op.drop_index("ix_matches_team_1_id", table_name="matches")
    op.drop_table("matches")

    op.drop_table("player_role")
    op.drop_index("ix_players_team_id", table_name="players")
    op.drop_table("players")
    op.drop_table("roles")
    op.drop_table("teams")

    bind = op.get_bind()
    dismissal_type.drop(bind, checkfirst=True)
    innings_status.drop(bind, checkfirst=True)
    match_status.drop(bind, checkfirst=True)
    match_format.drop(bind, checkfirst=True)
