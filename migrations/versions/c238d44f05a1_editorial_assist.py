"""Durable editorial model tasks, isolated from human decisions."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "c238d44f05a1"
down_revision = "b1623e091a22"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "assist_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("execution_key", sa.String(), nullable=False),
        sa.Column("stage", sa.String(), nullable=False),
        sa.Column("prompt_version", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("input", JSONB(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("attempts_log", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("output", JSONB(), nullable=True),
        sa.Column("raw_output", sa.Text(), nullable=True),
        sa.Column("metadata", JSONB(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "applied_event_id", sa.String(), sa.ForeignKey("editorial_events.id"), nullable=True
        ),
        sa.UniqueConstraint("execution_key"),
    )


def downgrade():
    op.drop_table("assist_runs")
