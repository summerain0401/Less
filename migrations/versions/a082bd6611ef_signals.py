"""Signal theses, evidence and review timeline."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "a082bd6611ef"
down_revision = "9ea704b3c216"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "signals",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("thesis", JSONB(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("needs_review", sa.Boolean(), nullable=False),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "signal_evidence",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("signal_id", sa.String(), sa.ForeignKey("signals.id"), nullable=False),
        sa.Column("evidence_id", sa.String(), sa.ForeignKey("evidence.id"), nullable=False),
        sa.Column("event_id", sa.String(), sa.ForeignKey("editorial_events.id"), nullable=False),
        sa.Column("event_revision", sa.Integer(), nullable=False),
        sa.Column("direction", sa.String(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("snapshot", JSONB(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("signal_id", "evidence_id"),
    )
    op.create_table(
        "signal_records",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("signal_id", sa.String(), sa.ForeignKey("signals.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("detail", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("signal_records")
    op.drop_table("signal_evidence")
    op.drop_table("signals")
