"""update_journal_content_length_to_150k

Revision ID: update_content_to_150k
Revises: 089f5e5bbd6c
Create Date: 2025-08-14 19:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'update_content_to_150k'
down_revision: Union[str, None] = '089f5e5bbd6c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the old constraint
    op.drop_constraint('chk_entry_content_length', 'journal_entries', type_='check')
    
    # Add the new constraint allowing 150,000 characters
    op.create_check_constraint(
        'chk_entry_content_length',
        'journal_entries',
        'LENGTH(content) <= 150000'
    )


def downgrade() -> None:
    # Drop the new constraint
    op.drop_constraint('chk_entry_content_length', 'journal_entries', type_='check')
    
    # Restore the old constraint (101,000 characters)
    op.create_check_constraint(
        'chk_entry_content_length',
        'journal_entries',
        'LENGTH(content) <= 101000'
    )
