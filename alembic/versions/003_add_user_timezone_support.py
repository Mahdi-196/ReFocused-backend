"""Add user timezone support for global date/time handling

Revision ID: 003_add_user_timezone_support
Revises: 002_convert_focus_time_to_minutes
Create Date: 2025-01-21 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '003_add_user_timezone_support'
down_revision = '002_convert_focus_time_to_minutes'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add timezone support fields to users table."""
    # Add timezone fields to users table
    op.add_column('users', sa.Column('timezone', sa.String(), nullable=False, server_default='UTC'))
    op.add_column('users', sa.Column('timezone_detected_method', sa.String(), nullable=False, server_default='auto'))
    op.add_column('users', sa.Column('timezone_confidence', sa.Float(), nullable=False, server_default='0.5'))
    op.add_column('users', sa.Column('timezone_updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')))
    
    # Create index on timezone for efficient queries
    op.create_index('idx_users_timezone', 'users', ['timezone'])


def downgrade() -> None:
    """Remove timezone support fields from users table."""
    # Remove index
    op.drop_index('idx_users_timezone', table_name='users')
    
    # Remove columns
    op.drop_column('users', 'timezone_updated_at')
    op.drop_column('users', 'timezone_confidence')
    op.drop_column('users', 'timezone_detected_method')
    op.drop_column('users', 'timezone') 