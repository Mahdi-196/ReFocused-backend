"""add_goals_completed_at

Revision ID: 007_add_goals_completed_at
Revises: 006_create_duration_based_goals
Create Date: 2024-12-30 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '007_add_goals_completed_at'
down_revision = '006_create_duration_based_goals'
branch_labels = None
depends_on = None


def upgrade():
    """Add completed_at column to both goal tables with proper indexes and data migration."""
    
    # Add completed_at column to goals_2_week table
    op.add_column('goals_2_week', 
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True)
    )
    
    # Add completed_at column to goals_long_term table
    op.add_column('goals_long_term', 
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True)
    )
    
    # Data migration: Backfill completed_at for existing completed goals
    # Use updated_at as the source for initial backfill
    op.execute(text("""
        UPDATE goals_2_week 
        SET completed_at = updated_at 
        WHERE is_completed = true AND completed_at IS NULL
    """))
    
    op.execute(text("""
        UPDATE goals_long_term 
        SET completed_at = updated_at 
        WHERE is_completed = true AND completed_at IS NULL
    """))
    
    # Create indexes for efficient querying
    # Index on completed_at for both tables
    op.create_index('idx_goals_2week_completed_at', 'goals_2_week', ['completed_at'])
    op.create_index('idx_goals_longterm_completed_at', 'goals_long_term', ['completed_at'])
    
    # Composite indexes for user_id and completed_at together (for user-specific queries)
    op.create_index('idx_goals_2week_user_completed_at', 'goals_2_week', ['user_id', 'completed_at'])
    op.create_index('idx_goals_longterm_user_completed_at', 'goals_long_term', ['user_id', 'completed_at'])
    
    # Additional composite indexes for performance optimization
    # Index for history queries (user_id, completed_at, is_completed)
    op.create_index('idx_goals_2week_history_query', 'goals_2_week', ['user_id', 'completed_at', 'is_completed'])
    op.create_index('idx_goals_longterm_history_query', 'goals_long_term', ['user_id', 'completed_at', 'is_completed'])
    
    # Indexes for goal_type filtering on completed goals
    op.create_index('idx_goals_2week_user_type_completed', 'goals_2_week', ['user_id', 'goal_type', 'is_completed'])
    op.create_index('idx_goals_longterm_user_type_completed', 'goals_long_term', ['user_id', 'goal_type', 'is_completed'])


def downgrade():
    """Remove completed_at column and related indexes."""
    
    # Drop indexes first
    op.drop_index('idx_goals_longterm_user_type_completed', table_name='goals_long_term')
    op.drop_index('idx_goals_2week_user_type_completed', table_name='goals_2_week')
    op.drop_index('idx_goals_longterm_history_query', table_name='goals_long_term')
    op.drop_index('idx_goals_2week_history_query', table_name='goals_2_week')
    op.drop_index('idx_goals_longterm_user_completed_at', table_name='goals_long_term')
    op.drop_index('idx_goals_2week_user_completed_at', table_name='goals_2_week')
    op.drop_index('idx_goals_longterm_completed_at', table_name='goals_long_term')
    op.drop_index('idx_goals_2week_completed_at', table_name='goals_2_week')
    
    # Drop columns
    op.drop_column('goals_long_term', 'completed_at')
    op.drop_column('goals_2_week', 'completed_at') 