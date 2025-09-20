"""remove_note_from_mood_entries

Revision ID: 688e11d1524b
Revises: 52a10c62cae1
Create Date: 2025-06-30 12:21:37.844776

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '688e11d1524b'
down_revision: Union[str, None] = '52a10c62cae1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove note column from mood_entries table
    op.drop_column('mood_entries', 'note')


def downgrade() -> None:
    # Add back note column if downgrading
    op.add_column('mood_entries', sa.Column('note', sa.Text(), nullable=True)) 