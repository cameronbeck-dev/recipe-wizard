"""add guest_usage table and guest fields on recipe_jobs

Revision ID: 009
Revises: 008
Create Date: 2026-08-16 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('guest_usage',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('device_id', sa.String(length=36), nullable=False),
        sa.Column('period_started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('generation_count', sa.Integer(), nullable=False),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_guest_usage_device_id'), 'guest_usage', ['device_id'], unique=True)
    op.create_index(op.f('ix_guest_usage_id'), 'guest_usage', ['id'], unique=False)

    op.add_column('recipe_jobs', sa.Column('device_id', sa.String(), nullable=True))
    op.create_index(op.f('ix_recipe_jobs_device_id'), 'recipe_jobs', ['device_id'], unique=False)
    op.add_column('recipe_jobs', sa.Column('result_json', sa.JSON(), nullable=True))
    op.alter_column('recipe_jobs', 'user_id', existing_type=sa.Integer(), nullable=True)


def downgrade():
    op.alter_column('recipe_jobs', 'user_id', existing_type=sa.Integer(), nullable=False)
    op.drop_column('recipe_jobs', 'result_json')
    op.drop_index(op.f('ix_recipe_jobs_device_id'), table_name='recipe_jobs')
    op.drop_column('recipe_jobs', 'device_id')

    op.drop_index(op.f('ix_guest_usage_id'), table_name='guest_usage')
    op.drop_index(op.f('ix_guest_usage_device_id'), table_name='guest_usage')
    op.drop_table('guest_usage')
