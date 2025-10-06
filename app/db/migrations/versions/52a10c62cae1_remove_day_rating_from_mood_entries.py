"""remove_day_rating_from_mood_entries

Revision ID: 52a10c62cae1
Revises: 068a2eb6dce2
Create Date: 2025-06-30 12:20:41.188408

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '52a10c62cae1'
down_revision: Union[str, None] = '068a2eb6dce2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove day_rating column from mood_entries table
    op.drop_column('mood_entries', 'day_rating')


def downgrade() -> None:
    # Add back day_rating column if downgrading
    op.add_column('mood_entries', sa.Column('day_rating', sa.Integer(), nullable=False, server_default='3')) 