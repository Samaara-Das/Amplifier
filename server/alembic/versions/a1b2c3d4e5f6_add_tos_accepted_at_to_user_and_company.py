"""add_tos_accepted_at_to_user_and_company

Revision ID: a1b2c3d4e5f6
Revises: c5967048d886
Create Date: 2026-04-30 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'c5967048d886'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('tos_accepted_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('companies', sa.Column('tos_accepted_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('companies', 'tos_accepted_at')
    op.drop_column('users', 'tos_accepted_at')
