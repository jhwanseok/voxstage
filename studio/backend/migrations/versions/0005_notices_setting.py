"""notices.yaml becomes a modelled bot setting: move raw `domain_file` rows into `domain_setting(kind=notices)`

Bots imported before ST3 hold `notices.yaml` as a raw file. Data only; no schema change.

Revision ID: 0005
Revises: 0004
"""
import json
import uuid

from alembic import op
import sqlalchemy as sa

from studio_backend import yamlio

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, bot_id, content, updated_by FROM domain_file "
                                "WHERE bot_id IS NOT NULL AND path = 'notices.yaml'")).fetchall()
    for fid, bot_id, content, updated_by in rows:
        exists = conn.execute(sa.text("SELECT 1 FROM domain_setting WHERE bot_id = :b AND kind = 'notices'"),
                              {"b": bot_id}).first()
        if exists is None:
            conn.execute(sa.text("INSERT INTO domain_setting (id, bot_id, kind, body, revision, created_at, "
                                 "updated_at, updated_by) VALUES (:id, :b, 'notices', CAST(:body AS JSONB), 1, now(), "
                                 "now(), :u)"),
                         {"id": str(uuid.uuid4()), "b": bot_id, "body": json.dumps(yamlio.load(content) or {}),
                          "u": updated_by})
        conn.execute(sa.text("DELETE FROM domain_file WHERE id = :id"), {"id": fid})


def downgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, bot_id, body, updated_by FROM domain_setting "
                                "WHERE bot_id IS NOT NULL AND kind = 'notices'")).fetchall()
    for sid, bot_id, body, updated_by in rows:
        doc = body if isinstance(body, dict) else json.loads(body)
        conn.execute(sa.text("INSERT INTO domain_file (id, bot_id, path, content, content_type, revision, "
                             "created_at, updated_at, updated_by) VALUES (:id, :b, 'notices.yaml', :c, 'text/yaml', 1, "
                             "now(), now(), :u)"),
                     {"id": str(uuid.uuid4()), "b": bot_id, "c": yamlio.dump(doc), "u": updated_by})
        conn.execute(sa.text("DELETE FROM domain_setting WHERE id = :id"), {"id": sid})
