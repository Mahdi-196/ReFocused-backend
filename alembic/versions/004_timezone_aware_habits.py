"""Timezone-aware habit tracking system

Revision ID: 004_timezone_aware_habits
Revises: 003_add_user_timezone_support
Create Date: 2025-01-20 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '004_timezone_aware_habits'
down_revision = '003_add_user_timezone_support'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade to timezone-aware habit tracking system"""
    
    # Add timezone-aware fields to habits table
    op.add_column('habits', sa.Column('last_updated_utc', 
                                     sa.DateTime(timezone=True), 
                                     nullable=True,
                                     server_default=sa.text('NOW()')))
    op.add_column('habits', sa.Column('is_active', 
                                     sa.Boolean(), 
                                     nullable=False, 
                                     server_default=sa.text('true')))
    
    # Create habit_completions table for timezone-aware completion tracking
    op.create_table('habit_completions',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('habit_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False, comment='User local date'),
        sa.Column('completed', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('timezone', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['habit_id'], ['habits.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('habit_id', 'date', name='uix_habit_completion_date'),
        sa.Index('idx_habit_completions_user_date', 'user_id', 'date'),
        sa.Index('idx_habit_completions_habit', 'habit_id'),
    )
    
    # Update existing habits to have default last_updated_utc
    op.execute("UPDATE habits SET last_updated_utc = created_at WHERE last_updated_utc IS NULL")
    
    # Make last_updated_utc non-nullable now that all records have values
    op.alter_column('habits', 'last_updated_utc', nullable=False)


def downgrade() -> None:
    """Downgrade from timezone-aware habit tracking system"""
    
    # Drop habit_completions table
    op.drop_table('habit_completions')
    
    # Remove timezone-aware fields from habits table
    op.drop_column('habits', 'last_updated_utc')
    op.drop_column('habits', 'is_active') 