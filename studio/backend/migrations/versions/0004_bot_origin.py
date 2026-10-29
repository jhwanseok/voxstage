"""bot.origin: a copied bot's source and what is still written in the source's language (새 상담봇 만들기)

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('bot', sa.Column('origin', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
                                   nullable=True))


def downgrade() -> None:
    op.drop_column('bot', 'origin')
