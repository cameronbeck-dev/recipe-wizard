"""add shopping list item source, manual override, and staleness baseline

Revision ID: 008
Revises: 007
Create Date: 2026-08-16 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('shopping_list_items', sa.Column('source', sa.String(length=20), nullable=False, server_default='recipe'))
    op.add_column('shopping_list_items', sa.Column('user_quantity_override', sa.String(length=200), nullable=True))
    op.add_column('shopping_list_items', sa.Column('override_baseline_display', sa.String(length=200), nullable=True))


def downgrade():
    op.drop_column('shopping_list_items', 'override_baseline_display')
    op.drop_column('shopping_list_items', 'user_quantity_override')
    op.drop_column('shopping_list_items', 'source')
