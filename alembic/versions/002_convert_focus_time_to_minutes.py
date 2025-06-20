"""convert focus time to minutes

Revision ID: 002_convert_focus_time_to_minutes
Revises: 001_initial
Create Date: 2024-01-15 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002_convert_focus_time_to_minutes'  
down_revision = '3f4cd12a9c14'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new column
    op.add_column('user_statistics', sa.Column('focus_time_minutes', sa.Integer(), default=0))
    
    # Convert existing data from seconds to minutes
    op.execute("""
        UPDATE user_statistics 
        SET focus_time_minutes = ROUND(focus_time_seconds / 60.0)
        WHERE focus_time_seconds IS NOT NULL
    """)
    
    # Set default for any null values
    op.execute("""
        UPDATE user_statistics 
        SET focus_time_minutes = 0 
        WHERE focus_time_minutes IS NULL
    """)
    
    # Drop old column
    op.drop_column('user_statistics', 'focus_time_seconds')


def downgrade() -> None:
    # Add back the old column
    op.add_column('user_statistics', sa.Column('focus_time_seconds', sa.Integer(), default=0))
    
    # Convert data back from minutes to seconds
    op.execute("""
        UPDATE user_statistics 
        SET focus_time_seconds = focus_time_minutes * 60
        WHERE focus_time_minutes IS NOT NULL
    """)
    
    # Set default for any null values
    op.execute("""
        UPDATE user_statistics 
        SET focus_time_seconds = 0 
        WHERE focus_time_seconds IS NULL
    """)
    
    # Drop new column
    op.drop_column('user_statistics', 'focus_time_minutes') 