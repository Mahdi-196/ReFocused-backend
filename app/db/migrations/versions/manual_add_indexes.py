"""Add performance indexes to study models

Revision ID: manual_add_indexes
Revises: e4a71160e85e
Create Date: 2025-06-13 23:28:00

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'manual_add_indexes'
down_revision = 'e4a71160e85e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add index for faster lookups by user_id and creation date
    op.create_index(
        'idx_studyset_user_created', 
        'study_sets', 
        ['user_id', 'created_at'],
        postgresql_ops={'created_at': 'DESC'}
    )
    
    # Add index for searching by title
    op.create_index(
        'idx_studyset_title', 
        'study_sets', 
        ['title']
    )
    
    # Add index for faster lookups by set_id (if it doesn't already exist)
    try:
        op.create_index(
            'idx_flashcard_set', 
            'flashcards', 
            ['set_id']
        )
    except sa.exc.OperationalError:
        # Index might already exist as ix_flashcards_set_id
        pass


def downgrade() -> None:
    # Drop the indexes
    op.drop_index('idx_studyset_user_created', table_name='study_sets')
    op.drop_index('idx_studyset_title', table_name='study_sets')
    
    try:
        op.drop_index('idx_flashcard_set', table_name='flashcards')
    except sa.exc.OperationalError:
        # Index might not exist
        pass 