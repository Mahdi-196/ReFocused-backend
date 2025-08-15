"""merge_migration_heads_before_content_length_update

Revision ID: da0d4487d4df
Revises: 012_add_daily_streak_tracking, 0dec1d73bb6b
Create Date: 2025-08-13 10:35:28.758332

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'da0d4487d4df'
down_revision: Union[str, None] = ('012_add_daily_streak_tracking', '0dec1d73bb6b')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass 