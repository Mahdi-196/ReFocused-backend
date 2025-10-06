"""create_duration_based_goals

Revision ID: 006_create_duration_based_goals
Revises: 005_rework_goals_system
Create Date: 2024-12-23 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '006_create_duration_based_goals'
down_revision = '3a32c88afe78'
branch_labels = None
depends_on = None


def upgrade():
    """Create new duration-based goal tables and migrate existing data."""
    
    # Create goals_2_week table
    op.create_table('goals_2_week',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('goal_type', sa.String(20), nullable=False),
        sa.Column('target_value', sa.Integer(), nullable=False),
        sa.Column('current_value', sa.Integer(), nullable=False, default=0),
        sa.Column('is_completed', sa.Boolean(), nullable=False, default=False),
        sa.Column('duration', sa.String(20), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.CheckConstraint("goal_type IN ('percentage', 'counter', 'checklist')", name='chk_goal_type'),
        sa.CheckConstraint('target_value >= 1 AND target_value <= 999', name='chk_target_value_range'),
        sa.CheckConstraint('current_value >= 0', name='chk_current_value_positive'),
        sa.CheckConstraint("duration IN ('2_week', 'long_term')", name='chk_duration_type'),
        sa.CheckConstraint("duration = '2_week'", name='chk_2week_duration'),
        sa.CheckConstraint(
            "(goal_type = 'percentage' AND target_value = 100) OR "
            "(goal_type = 'counter' AND target_value >= 2 AND target_value <= 999) OR "
            "(goal_type = 'checklist' AND target_value = 1)",
            name='chk_goal_type_target_consistency'
        ),
    )
    
    # Create indexes for goals_2_week
    op.create_index('ix_goals_2week_id', 'goals_2_week', ['id'])
    op.create_index('ix_goals_2week_name', 'goals_2_week', ['name'])
    op.create_index('ix_goals_2week_goal_type', 'goals_2_week', ['goal_type'])
    op.create_index('ix_goals_2week_is_completed', 'goals_2_week', ['is_completed'])
    op.create_index('ix_goals_2week_duration', 'goals_2_week', ['duration'])
    op.create_index('ix_goals_2week_expires_at', 'goals_2_week', ['expires_at'])
    op.create_index('idx_goals_2week_user_type', 'goals_2_week', ['user_id', 'goal_type'])
    op.create_index('idx_goals_2week_user_completed', 'goals_2_week', ['user_id', 'is_completed'])
    op.create_index('idx_goals_2week_user_expires', 'goals_2_week', ['user_id', 'expires_at'])
    op.create_index('idx_goals_2week_expires_active', 'goals_2_week', ['expires_at', 'is_completed'])
    
    # Create goals_long_term table
    op.create_table('goals_long_term',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('goal_type', sa.String(20), nullable=False),
        sa.Column('target_value', sa.Integer(), nullable=False),
        sa.Column('current_value', sa.Integer(), nullable=False, default=0),
        sa.Column('is_completed', sa.Boolean(), nullable=False, default=False),
        sa.Column('duration', sa.String(20), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.CheckConstraint("goal_type IN ('percentage', 'counter', 'checklist')", name='chk_goal_type'),
        sa.CheckConstraint('target_value >= 1 AND target_value <= 999', name='chk_target_value_range'),
        sa.CheckConstraint('current_value >= 0', name='chk_current_value_positive'),
        sa.CheckConstraint("duration IN ('2_week', 'long_term')", name='chk_duration_type'),
        sa.CheckConstraint("duration = 'long_term'", name='chk_longterm_duration'),
        sa.CheckConstraint(
            "(goal_type = 'percentage' AND target_value = 100) OR "
            "(goal_type = 'counter' AND target_value >= 2 AND target_value <= 999) OR "
            "(goal_type = 'checklist' AND target_value = 1)",
            name='chk_goal_type_target_consistency'
        ),
    )
    
    # Create indexes for goals_long_term
    op.create_index('ix_goals_longterm_id', 'goals_long_term', ['id'])
    op.create_index('ix_goals_longterm_name', 'goals_long_term', ['name'])
    op.create_index('ix_goals_longterm_goal_type', 'goals_long_term', ['goal_type'])
    op.create_index('ix_goals_longterm_is_completed', 'goals_long_term', ['is_completed'])
    op.create_index('ix_goals_longterm_duration', 'goals_long_term', ['duration'])
    op.create_index('idx_goals_longterm_user_type', 'goals_long_term', ['user_id', 'goal_type'])
    op.create_index('idx_goals_longterm_user_completed', 'goals_long_term', ['user_id', 'is_completed'])
    
    # Migrate existing goals from old 'goals' table to 'goals_long_term' (if the table exists)
    # This is a safe migration - all existing goals become long-term goals
    connection = op.get_bind()
    
    # Check if old goals table exists
    inspector = sa.inspect(connection)
    existing_tables = inspector.get_table_names()
    
    if 'goals' in existing_tables:
        # Migrate existing goals to long_term table with duration field
        op.execute(text("""
            INSERT INTO goals_long_term (
                id, name, goal_type, target_value, current_value, 
                is_completed, duration, user_id, created_at, updated_at
            )
            SELECT 
                id, name, goal_type, target_value, current_value,
                is_completed, 'long_term' as duration, user_id, created_at, updated_at
            FROM goals
        """))
        
        # Drop old goals table after successful migration
        op.drop_table('goals')


def downgrade():
    """Revert to single goals table."""
    
    # Recreate original goals table
    op.create_table('goals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('goal_type', sa.String(20), nullable=False),
        sa.Column('target_value', sa.Integer(), nullable=False),
        sa.Column('current_value', sa.Integer(), nullable=False, default=0),
        sa.Column('is_completed', sa.Boolean(), nullable=False, default=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.CheckConstraint("goal_type IN ('percentage', 'counter', 'checklist')", name='chk_goal_type'),
        sa.CheckConstraint('target_value >= 1 AND target_value <= 999', name='chk_target_value_range'),
        sa.CheckConstraint('current_value >= 0', name='chk_current_value_positive'),
        sa.CheckConstraint(
            "(goal_type = 'percentage' AND target_value = 100) OR "
            "(goal_type = 'counter' AND target_value >= 2 AND target_value <= 999) OR "
            "(goal_type = 'checklist' AND target_value = 1)",
            name='chk_goal_type_target_consistency'
        ),
    )
    
    # Recreate original indexes
    op.create_index('ix_goals_id', 'goals', ['id'])
    op.create_index('ix_goals_name', 'goals', ['name'])
    op.create_index('ix_goals_goal_type', 'goals', ['goal_type'])
    op.create_index('ix_goals_is_completed', 'goals', ['is_completed'])
    op.create_index('idx_goals_user_type', 'goals', ['user_id', 'goal_type'])
    op.create_index('idx_goals_user_completed', 'goals', ['user_id', 'is_completed'])
    
    # Migrate data back from both new tables to single goals table
    # Note: This will lose 2-week goal expiration data and some goals may be lost if IDs conflict
    op.execute(text("""
        INSERT INTO goals (
            id, name, goal_type, target_value, current_value, 
            is_completed, user_id, created_at, updated_at
        )
        SELECT 
            id, name, goal_type, target_value, current_value,
            is_completed, user_id, created_at, updated_at
        FROM goals_long_term
        UNION ALL
        SELECT 
            id + 100000, name, goal_type, target_value, current_value,
            is_completed, user_id, created_at, updated_at
        FROM goals_2_week
    """))
    
    # Drop new tables
    op.drop_table('goals_2_week')
    op.drop_table('goals_long_term') 