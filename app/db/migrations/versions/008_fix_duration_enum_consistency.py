"""Fix duration enum consistency

Revision ID: 008_fix_duration_enum
Revises: 007_add_goals_completed_at
Create Date: 2024-01-24 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '008_fix_duration_enum'
down_revision = '007_add_goals_completed_at'
branch_labels = None
depends_on = None

def upgrade():
    """Update duration values from '2_week' to 'two_week' for consistency."""
    
    # Drop existing check constraints first
    op.drop_constraint('chk_duration_type', 'goals_2_week', type_='check')
    op.drop_constraint('chk_2week_duration', 'goals_2_week', type_='check')
    op.drop_constraint('chk_duration_type', 'goals_long_term', type_='check')
    op.drop_constraint('chk_longterm_duration', 'goals_long_term', type_='check')
    
    # Update existing data in goals_2_week table
    op.execute("UPDATE goals_2_week SET duration = 'two_week' WHERE duration = '2_week';")
    
    # Update existing data in goals_long_term table (should already be correct, but just in case)
    op.execute("UPDATE goals_long_term SET duration = 'long_term' WHERE duration != 'long_term';")
    
    # Create new check constraints with updated values
    op.create_check_constraint(
        'chk_duration_type',
        'goals_2_week',
        'duration IN (\'two_week\', \'long_term\')'
    )
    op.create_check_constraint(
        'chk_2week_duration',
        'goals_2_week', 
        'duration = \'two_week\''
    )
    op.create_check_constraint(
        'chk_duration_type',
        'goals_long_term',
        'duration IN (\'two_week\', \'long_term\')'
    )
    op.create_check_constraint(
        'chk_longterm_duration',
        'goals_long_term',
        'duration = \'long_term\''
    )

def downgrade():
    """Revert duration values back to '2_week' from 'two_week'."""
    
    # Update data back to original format
    op.execute("UPDATE goals_2_week SET duration = '2_week' WHERE duration = 'two_week';")
    
    # Drop new check constraints
    op.drop_constraint('chk_duration_type', 'goals_2_week', type_='check')
    op.drop_constraint('chk_2week_duration', 'goals_2_week', type_='check') 
    op.drop_constraint('chk_duration_type', 'goals_long_term', type_='check')
    op.drop_constraint('chk_longterm_duration', 'goals_long_term', type_='check')
    
    # Restore original check constraints
    op.create_check_constraint(
        'chk_duration_type',
        'goals_2_week',
        'duration IN (\'2_week\', \'long_term\')'
    )
    op.create_check_constraint(
        'chk_2week_duration',
        'goals_2_week',
        'duration = \'2_week\''
    )
    op.create_check_constraint(
        'chk_duration_type', 
        'goals_long_term',
        'duration IN (\'2_week\', \'long_term\')'
    )
    op.create_check_constraint(
        'chk_longterm_duration',
        'goals_long_term',
        'duration = \'long_term\''
    ) 