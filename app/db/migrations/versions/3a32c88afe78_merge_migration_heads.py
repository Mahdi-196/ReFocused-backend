"""merge_migration_heads

Revision ID: 3a32c88afe78
Revises: 4b6db1e74c13, e4a71160e85e
Create Date: 2025-07-01 23:12:06.302911

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3a32c88afe78'
down_revision: Union[str, None] = ('4b6db1e74c13', 'e4a71160e85e')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass 