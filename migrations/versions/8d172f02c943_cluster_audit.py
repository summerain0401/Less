"""Fixed cluster audit samples and append-only human labels."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "8d172f02c943"
down_revision = "7f08cb14a832"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cluster_audit_batches",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("seed", sa.String(), nullable=False),
        sa.Column("purpose", sa.String(), nullable=False),
        sa.Column("method", sa.String(), nullable=False),
        sa.Column("target_count", sa.Integer(), nullable=False),
        sa.Column("population_events", sa.Integer(), nullable=False),
        sa.Column("considered_events", sa.Integer(), nullable=False),
        sa.Column("population_pairs", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "cluster_audit_pairs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "batch_id", sa.String(), sa.ForeignKey("cluster_audit_batches.id"), nullable=False
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("prediction", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("batch_id", "position"),
    )
    op.create_table(
        "cluster_audit_labels",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("pair_id", sa.String(), sa.ForeignKey("cluster_audit_pairs.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("verdict", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("original_checked", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("pair_id", "revision"),
    )


def downgrade():
    op.drop_table("cluster_audit_labels")
    op.drop_table("cluster_audit_pairs")
    op.drop_table("cluster_audit_batches")
