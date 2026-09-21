"""Version-bound reading feedback."""

import sqlalchemy as sa
from alembic import op

revision = "b1623e091a22"
down_revision = "a082bd6611ef"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "reading_feedback",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("version_id", sa.String(), sa.ForeignKey("brief_versions.id"), nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("would_read_again", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("next_day", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("reading_feedback")
