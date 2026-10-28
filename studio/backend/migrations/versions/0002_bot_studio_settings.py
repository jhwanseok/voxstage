"""bot.studio_settings: bot defaults the engine does not read yet (hand-off number, policy values)

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('bot', sa.Column('studio_settings', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
                                   nullable=True))


def downgrade() -> None:
    op.drop_column('bot', 'studio_settings')
