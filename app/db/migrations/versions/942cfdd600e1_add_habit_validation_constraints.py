"""add_habit_validation_constraints

Revision ID: 942cfdd600e1
Revises: 336d54ba80d0
Create Date: 2025-06-23 11:57:23.510509

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '942cfdd600e1'
down_revision: Union[str, None] = '336d54ba80d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add validation constraints to habits table"""
    # Add check constraint for non-empty habit names
    op.create_check_constraint(
        'chk_habit_name_not_empty',
        'habits',
        'LENGTH(TRIM(name)) > 0'
    )
    
    # Clean up any existing habits with empty names (if any)
    op.execute("UPDATE habits SET name = 'Unnamed Habit' WHERE LENGTH(TRIM(name)) = 0 OR name IS NULL")
    
    # Clean up any existing duplicate favorites (keep only 3 most recent per user)
    op.execute("""
        WITH ranked_favorites AS (
            SELECT id, user_id,
                   ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY created_at DESC) as rn
            FROM habits 
            WHERE is_favorite = TRUE AND is_active = TRUE
        )
        UPDATE habits 
        SET is_favorite = FALSE 
        WHERE id IN (
            SELECT id FROM ranked_favorites WHERE rn > 3
        )
    """)


def downgrade() -> None:
    """Remove validation constraints from habits table"""
    # Drop check constraint
    op.drop_constraint('chk_habit_name_not_empty', 'habits', type_='check') 