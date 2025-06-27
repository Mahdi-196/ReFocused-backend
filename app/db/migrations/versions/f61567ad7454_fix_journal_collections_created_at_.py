"""fix_journal_collections_created_at_default

Revision ID: f61567ad7454
Revises: 1eec4e4473ec
Create Date: 2025-06-26 11:56:01.777043

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f61567ad7454'
down_revision: Union[str, None] = '1eec4e4473ec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add server default to created_at column for journal_collections
    op.alter_column('journal_collections', 'created_at',
                   existing_type=sa.DateTime(timezone=True),
                   server_default=sa.text('now()'),
                   existing_nullable=False)


def downgrade() -> None:
    # Remove server default from created_at column for journal_collections
    op.alter_column('journal_collections', 'created_at',
                   existing_type=sa.DateTime(timezone=True),
                   server_default=None,
                   existing_nullable=False) 