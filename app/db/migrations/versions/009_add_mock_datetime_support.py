"""Add mock datetime support for time travel testing

Revision ID: 009_add_mock_datetime_support
Revises: 008_fix_duration_enum
Create Date: 2025-01-21 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '009_add_mock_datetime_support'
down_revision = '008_fix_duration_enum'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add mock datetime support fields to users table for testing."""
    # Add mock date/time fields to users table
    op.add_column('users', sa.Column('mock_date_enabled', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('users', sa.Column('mock_datetime_override', sa.DateTime(timezone=True), nullable=True))
    
    # Create index on mock_date_enabled for efficient queries by debug endpoints
    op.create_index('idx_users_mock_date_enabled', 'users', ['mock_date_enabled'])


def downgrade() -> None:
    """Remove mock datetime support fields from users table."""
    # Remove index
    op.drop_index('idx_users_mock_date_enabled', table_name='users')
    
    # Remove columns
    op.drop_column('users', 'mock_datetime_override')
    op.drop_column('users', 'mock_date_enabled') 