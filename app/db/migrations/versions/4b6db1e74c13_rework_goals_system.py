"""rework_goals_system

Revision ID: 4b6db1e74c13
Revises: 1b758ed81674
Create Date: 2025-01-27 13:01:51.493079

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '4b6db1e74c13'
down_revision: Union[str, None] = '1b758ed81674'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # First, backup existing goals to a temporary table (only if goals table exists)
    op.execute("""
        CREATE TABLE IF NOT EXISTS goals_backup AS 
        SELECT id, title, description, target_date, is_completed, priority, category, user_id, created_at, updated_at 
        FROM goals
        WHERE false
    """)
    
    # Check if goals table has data and backup if so
    op.execute("""
        INSERT INTO goals_backup 
        SELECT id, title, description, target_date, is_completed, priority, category, user_id, created_at, updated_at 
        FROM goals
    """)
    
    # Drop existing constraints and indexes that will conflict
    try:
        op.drop_index('ix_goals_title', table_name='goals')
    except:
        pass  # Index might not exist
    
    # Rename title to name
    op.alter_column('goals', 'title', new_column_name='name')
    
    # Add new columns
    op.add_column('goals', sa.Column('goal_type', sa.String(20), nullable=True))
    op.add_column('goals', sa.Column('target_value', sa.Integer(), nullable=True))
    op.add_column('goals', sa.Column('current_value', sa.Integer(), nullable=False, server_default='0'))
    
    # Convert existing goals to checklist type (simplest migration)
    op.execute("""
        UPDATE goals 
        SET 
            goal_type = 'checklist',
            target_value = 1,
            current_value = CASE WHEN is_completed THEN 1 ELSE 0 END
    """)
    
    # Make columns non-nullable after data migration
    op.alter_column('goals', 'goal_type', nullable=False)
    op.alter_column('goals', 'target_value', nullable=False)
    
    # Drop old columns that are no longer needed
    op.drop_column('goals', 'description')
    op.drop_column('goals', 'target_date')
    op.drop_column('goals', 'priority')
    op.drop_column('goals', 'category')
    
    # Add new indexes
    op.create_index('ix_goals_name', 'goals', ['name'])
    op.create_index('ix_goals_goal_type', 'goals', ['goal_type'])
    op.create_index('ix_goals_is_completed', 'goals', ['is_completed'])
    op.create_index('idx_goals_user_type', 'goals', ['user_id', 'goal_type'])
    op.create_index('idx_goals_user_completed', 'goals', ['user_id', 'is_completed'])
    
    # Add constraints
    op.create_check_constraint(
        'chk_goal_type',
        'goals',
        "goal_type IN ('percentage', 'counter', 'checklist')"
    )
    op.create_check_constraint(
        'chk_target_value_range',
        'goals',
        'target_value >= 1 AND target_value <= 999'
    )
    op.create_check_constraint(
        'chk_current_value_positive',
        'goals',
        'current_value >= 0'
    )
    op.create_check_constraint(
        'chk_goal_type_target_consistency',
        'goals',
        """(goal_type = 'percentage' AND target_value = 100) OR 
           (goal_type = 'counter' AND target_value >= 2 AND target_value <= 999) OR 
           (goal_type = 'checklist' AND target_value = 1)"""
    )


def downgrade() -> None:
    # Drop new constraints and indexes
    op.drop_constraint('chk_goal_type_target_consistency', 'goals')
    op.drop_constraint('chk_current_value_positive', 'goals')
    op.drop_constraint('chk_target_value_range', 'goals')
    op.drop_constraint('chk_goal_type', 'goals')
    
    op.drop_index('idx_goals_user_completed', table_name='goals')
    op.drop_index('idx_goals_user_type', table_name='goals')
    op.drop_index('ix_goals_is_completed', table_name='goals')
    op.drop_index('ix_goals_goal_type', table_name='goals')
    op.drop_index('ix_goals_name', table_name='goals')
    
    # Add back old columns with defaults
    op.add_column('goals', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('goals', sa.Column('target_date', sa.DateTime(timezone=True), nullable=True))
    op.add_column('goals', sa.Column('priority', sa.String(20), nullable=False, server_default='medium'))
    op.add_column('goals', sa.Column('category', sa.String(100), nullable=True))
    
    # Try to restore data from backup if it exists
    op.execute("""
        UPDATE goals 
        SET 
            description = b.description,
            target_date = b.target_date,
            priority = COALESCE(b.priority, 'medium'),
            category = b.category
        FROM goals_backup b 
        WHERE goals.id = b.id
    """)
    
    # Remove server_default after data population
    op.alter_column('goals', 'priority', server_default=None)
    
    # Drop new columns
    op.drop_column('goals', 'current_value')
    op.drop_column('goals', 'target_value')
    op.drop_column('goals', 'goal_type')
    
    # Rename name back to title
    op.alter_column('goals', 'name', new_column_name='title')
    
    # Restore old index
    op.create_index('ix_goals_title', 'goals', ['title'])
    
    # Drop backup table
    op.execute("DROP TABLE IF EXISTS goals_backup") 