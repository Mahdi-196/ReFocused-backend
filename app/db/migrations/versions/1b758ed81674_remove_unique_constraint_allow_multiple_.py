"""remove_unique_constraint_allow_multiple_mood_entries_per_day

Revision ID: 1b758ed81674
Revises: 688e11d1524b
Create Date: 2025-06-30 12:27:11.076928

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1b758ed81674'
down_revision: Union[str, None] = '688e11d1524b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove the unique constraint to allow multiple mood entries per day
    op.drop_constraint('uix_user_entry_date', 'mood_entries', type_='unique')
    
    # Add new index for efficiently finding the most recent entry per day
    op.create_index('idx_mood_entries_user_date_created', 'mood_entries', ['user_id', 'entry_date', 'created_at'])


def downgrade() -> None:
    # Remove the new index
    op.drop_index('idx_mood_entries_user_date_created', 'mood_entries')
    
    # Recreate the unique constraint (this may fail if there are duplicate entries)
    op.create_unique_constraint('uix_user_entry_date', 'mood_entries', ['user_id', 'entry_date']) 