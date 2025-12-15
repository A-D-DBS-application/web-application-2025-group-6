"""Add user_id to itinerary table

Revision ID: add_user_id_itinerary
Revises: 1cb54f09dd86
Create Date: 2025-12-13 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_user_id_itinerary'
down_revision = '1cb54f09dd86'
branch_labels = None
depends_on = None


def upgrade():
    # Add user_id column to itinerary table
    with op.batch_alter_table('itinerary', schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_itinerary_user', 'users', ['user_id'], ['user_id'])


def downgrade():
    # Remove user_id column from itinerary table
    with op.batch_alter_table('itinerary', schema=None) as batch_op:
        batch_op.drop_constraint('fk_itinerary_user', type_='foreignkey')
        batch_op.drop_column('user_id')

