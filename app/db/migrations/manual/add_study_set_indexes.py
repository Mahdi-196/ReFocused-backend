"""Add performance indexes to study models manually

This migration adds the following indexes:
- idx_studyset_user_created on study_sets(user_id, created_at DESC)
- idx_studyset_title on study_sets(title)
- idx_flashcard_set on flashcards(set_id)
"""

from alembic import op

# Set revision IDs and dependencies to None for manual migrations
revision = None
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    """Add the new indexes."""
    # Add index for faster lookups by user_id and creation date
    op.create_index(
        'idx_studyset_user_created', 
        'study_sets', 
        ['user_id', 'created_at'], 
        unique=False,
        postgresql_ops={'created_at': 'DESC'}
    )
    
    # Add index for searching by title
    op.create_index(
        'idx_studyset_title', 
        'study_sets', 
        ['title'], 
        unique=False
    )
    
    # Add index for faster lookups by set_id
    op.create_index(
        'idx_flashcard_set', 
        'flashcards', 
        ['set_id'], 
        unique=False
    )

def downgrade():
    """Remove the new indexes."""
    # Drop the indexes
    op.drop_index('idx_studyset_user_created', table_name='study_sets')
    op.drop_index('idx_studyset_title', table_name='study_sets')
    op.drop_index('idx_flashcard_set', table_name='flashcards') 