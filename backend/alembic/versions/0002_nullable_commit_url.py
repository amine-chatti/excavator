"""Allow commits without a remote URL."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0002_nullable_commit_url"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("commits") as batch_op:
        batch_op.alter_column("url", existing_type=sa.String(), nullable=True)


def downgrade() -> None:
    op.execute("UPDATE commits SET url = '' WHERE url IS NULL")
    with op.batch_alter_table("commits") as batch_op:
        batch_op.alter_column("url", existing_type=sa.String(), nullable=False)
