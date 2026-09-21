"""Retain reversible event merge and split history.

Written offline; validate against PostgreSQL before deploying.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "7f08cb14a832"
down_revision = "dd6b1e14fcd1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "editorial_events",
        sa.Column("lifecycle", sa.String(), nullable=False, server_default="active"),
    )
    op.add_column("editorial_events", sa.Column("redirected_to", sa.String(), nullable=True))
    op.create_foreign_key(
        "fk_event_redirect", "editorial_events", "editorial_events", ["redirected_to"], ["id"]
    )
    op.create_table(
        "cluster_operations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("before", postgresql.JSONB(), nullable=False),
        sa.Column("after_revisions", postgresql.JSONB(), nullable=False),
        sa.Column("created_event_ids", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("restored_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("restored_by", sa.String(), nullable=True),
        sa.Column("restore_reason", sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_table("cluster_operations")
    op.drop_constraint("fk_event_redirect", "editorial_events", type_="foreignkey")
    op.drop_column("editorial_events", "redirected_to")
    op.drop_column("editorial_events", "lifecycle")
