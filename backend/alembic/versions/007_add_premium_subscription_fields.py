"""add premium subscription fields to users

Revision ID: 007
Revises: 006
Create Date: 2026-08-16 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('premium_expires_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('revenuecat_customer_id', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('premium_product_id', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('premium_event_at_ms', sa.BigInteger(), nullable=True))
    op.create_index(op.f('ix_users_revenuecat_customer_id'), 'users', ['revenuecat_customer_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_users_revenuecat_customer_id'), table_name='users')
    op.drop_column('users', 'premium_event_at_ms')
    op.drop_column('users', 'premium_product_id')
    op.drop_column('users', 'revenuecat_customer_id')
    op.drop_column('users', 'premium_expires_at')
