"""merge migration heads

Revision ID: 11a22ae8f8ab
Revises: 001, 99fc0ccab2e9
Create Date: 2025-06-11 16:33:11.982302

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '11a22ae8f8ab'
down_revision: Union[str, None] = ('001', '99fc0ccab2e9')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass 