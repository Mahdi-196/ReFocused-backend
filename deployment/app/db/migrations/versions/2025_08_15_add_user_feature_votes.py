"""add user_feature_votes (one vote per user)

Revision ID: 2025_08_15_add_user_feature_votes
Revises: update_content_to_150k
Create Date: 2025-08-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2025_08_15_add_user_feature_votes'
down_revision: Union[str, None] = 'update_content_to_150k'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'user_feature_votes',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('vote_id', sa.String(length=200), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_unique_constraint('uix_user_feature_votes_user', 'user_feature_votes', ['user_id'])
    op.create_index('idx_user_feature_votes_user', 'user_feature_votes', ['user_id'])


def downgrade() -> None:
    op.drop_index('idx_user_feature_votes_user', table_name='user_feature_votes')
    op.drop_constraint('uix_user_feature_votes_user', 'user_feature_votes', type_='unique')
    op.drop_table('user_feature_votes')


