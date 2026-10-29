"""types.yaml becomes a modelled shared setting: move raw `domain_file` rows into `domain_setting(kind=types)`

Domains imported before ST4 hold `types.yaml` as a raw file. Data only; no schema change.

Revision ID: 0003
Revises: 0002
"""
import json
import uuid

from alembic import op
import sqlalchemy as sa

from studio_backend import yamlio

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, domain_id, content, updated_by FROM domain_file "
                                "WHERE domain_id IS NOT NULL AND path = 'types.yaml'")).fetchall()
    for fid, domain_id, content, updated_by in rows:
        exists = conn.execute(sa.text("SELECT 1 FROM domain_setting WHERE domain_id = :d AND kind = 'types'"),
                              {"d": domain_id}).first()
        if exists is None:
            conn.execute(sa.text("INSERT INTO domain_setting (id, domain_id, kind, body, revision, created_at, "
                                 "updated_at, updated_by) VALUES (:id, :d, 'types', CAST(:body AS JSONB), 1, now(), "
                                 "now(), :u)"),
                         {"id": str(uuid.uuid4()), "d": domain_id, "body": json.dumps(yamlio.load(content) or {}),
                          "u": updated_by})
        conn.execute(sa.text("DELETE FROM domain_file WHERE id = :id"), {"id": fid})


def downgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, domain_id, body, updated_by FROM domain_setting "
                                "WHERE domain_id IS NOT NULL AND kind = 'types'")).fetchall()
    for sid, domain_id, body, updated_by in rows:
        doc = body if isinstance(body, dict) else json.loads(body)
        conn.execute(sa.text("INSERT INTO domain_file (id, domain_id, path, content, content_type, revision, "
                             "created_at, updated_at, updated_by) VALUES (:id, :d, 'types.yaml', :c, 'text/yaml', 1, "
                             "now(), now(), :u)"),
                     {"id": str(uuid.uuid4()), "d": domain_id, "c": yamlio.dump(doc), "u": updated_by})
        conn.execute(sa.text("DELETE FROM domain_setting WHERE id = :id"), {"id": sid})
