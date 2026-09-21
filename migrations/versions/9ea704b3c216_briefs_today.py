"""Versioned briefs, explicit reviews and finite daily editions."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "9ea704b3c216"
down_revision = "8d172f02c943"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "briefs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("event_id", sa.String(), sa.ForeignKey("editorial_events.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("event_id"),
    )
    op.create_table(
        "brief_versions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("brief_id", sa.String(), sa.ForeignKey("briefs.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("event_revision", sa.Integer(), nullable=False),
        sa.Column("content", pg.JSONB(), nullable=False),
        sa.Column("sources", pg.JSONB(), nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("brief_id", "revision"),
    )
    op.create_table(
        "brief_reviews",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("brief_id", sa.String(), sa.ForeignKey("briefs.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "today_editions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "brief_publications",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("edition_id", sa.String(), sa.ForeignKey("today_editions.id"), nullable=False),
        sa.Column("brief_id", sa.String(), sa.ForeignKey("briefs.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("edition_id", "brief_id"),
    )


def downgrade():
    for table in (
        "brief_publications",
        "today_editions",
        "brief_reviews",
        "brief_versions",
        "briefs",
    ):
        op.drop_table(table)
