"""update_journal_content_length_to_101k

Revision ID: 089f5e5bbd6c
Revises: da0d4487d4df
Create Date: 2025-08-13 10:35:30.860597

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '089f5e5bbd6c'
down_revision: Union[str, None] = 'da0d4487d4df'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the old constraint
    op.drop_constraint('chk_entry_content_length', 'journal_entries', type_='check')
    
    # Add the new constraint allowing 101,000 characters
    op.create_check_constraint(
        'chk_entry_content_length',
        'journal_entries',
        'LENGTH(content) <= 101000'
    )


def downgrade() -> None:
    # Drop the new constraint
    op.drop_constraint('chk_entry_content_length', 'journal_entries', type_='check')
    
    # Restore the old constraint
    op.create_check_constraint(
        'chk_entry_content_length',
        'journal_entries',
        'LENGTH(content) <= 50000'
    ) 