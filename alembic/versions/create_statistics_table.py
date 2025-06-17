"""create statistics table

Revision ID: 3f4cd12a9c14
Revises: <prevision_id>
Create Date: 2023-06-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3f4cd12a9c14'
down_revision = None  # Replace with the actual previous migration ID
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'user_statistics',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('focus_time_seconds', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('completed_sessions', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('completed_tasks', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'date', name='user_date_unique')
    )
    op.create_index(op.f('ix_user_statistics_user_id'), 'user_statistics', ['user_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_user_statistics_user_id'), table_name='user_statistics')
    op.drop_table('user_statistics') 