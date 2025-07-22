"""add daily streak tracking

Revision ID: 012_add_daily_streak_tracking
Revises: 11a22ae8f8ab
Create Date: 2025-07-21 01:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '012_add_daily_streak_tracking'
down_revision: Union[str, None] = '11a22ae8f8ab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add daily streak tracking columns to users table
    op.add_column('users', sa.Column('current_streak', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('longest_streak', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('last_interaction_date', sa.Date(), nullable=True))
    op.add_column('users', sa.Column('streak_updated_at', sa.DateTime(timezone=True), nullable=True))
    
    # Create user_daily_streaks table
    op.create_table('user_daily_streaks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('interaction_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('first_interaction', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_interaction', sa.DateTime(timezone=True), nullable=True),
        sa.Column('interaction_types', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('timezone', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'date', name='uix_user_daily_streak_date')
    )
    
    # Create indexes for performance
    op.create_index('idx_user_daily_streaks_user_date', 'user_daily_streaks', ['user_id', 'date'], unique=False)
    op.create_index(op.f('ix_user_daily_streaks_date'), 'user_daily_streaks', ['date'], unique=False)
    op.create_index(op.f('ix_user_daily_streaks_user_id'), 'user_daily_streaks', ['user_id'], unique=False)


def downgrade() -> None:
    # Drop user_daily_streaks table and indexes
    op.drop_index(op.f('ix_user_daily_streaks_user_id'), table_name='user_daily_streaks')
    op.drop_index(op.f('ix_user_daily_streaks_date'), table_name='user_daily_streaks')
    op.drop_index('idx_user_daily_streaks_user_date', table_name='user_daily_streaks')
    op.drop_table('user_daily_streaks')
    
    # Remove streak columns from users table
    op.drop_column('users', 'streak_updated_at')
    op.drop_column('users', 'last_interaction_date')
    op.drop_column('users', 'longest_streak')
    op.drop_column('users', 'current_streak') 