"""Type dictionary, session roles and flow roles (ST4, ADR 0014): shape checks, export, uses that block a removal."""

import pathlib

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from studio_backend import yamlio

A = "/api/v1"
BACKEND = pathlib.Path(__file__).resolve().parents[1]
ROOT = BACKEND.parents[1]   # the voxstage repository

# the shape of the engine's types.yaml (voxstage/rules/types.py, R16a)
DOC = {
    "types": {
        "Person": {"label": {"ko": "사람"}, "fields": {"name": {"type": "text"},
                                                       "last4": {"type": "digits", "length": 4, "label": {"ko": "계좌 끝 4자리"}}}},
        "Plan": {"fields": {"kind": {"type": "choice", "choices": ["basic", "premium"]}}},
    },
    "session_roles": {"caller": {"type": "Person", "label": {"ko": "발신자"}}},
}


@pytest.fixture()
def client(session, tmp_path, monkeypatch):
    monkeypatch.setenv("STUDIO_EXPORT_ROOT", str(tmp_path / "exports"))
    from studio_backend.main import app
    with TestClient(app) as c:
        assert c.post(f"{A}/domains/import", json={"domain": "bank"}).status_code == 201
        yield c


def put(c, body, force=True, **kw):
    """Replace the dictionary; forced by default, because the imported bank flows already use the shipped types."""
    cur = c.get(f"{A}/domains/bank/types").json()
    return c.put(f"{A}/domains/bank/types", json={"body": body, "revision": cur["revision"], "force": force, **kw})


def files(c):
    """The draft as the exporter writes it."""
    from sqlalchemy import select
    from studio_backend import db
    from studio_backend.models import Bot
    from studio_backend.portable import export_bot
    with db.session_scope() as s:
        return export_bot(s, s.scalar(select(Bot).where(Bot.slug == "bank-ko")))


def test_imported_dictionary_is_modelled_and_exported_unchanged(client):
    t = client.get(f"{A}/domains/bank/types").json()
    source = yamlio.load((ROOT / "domains" / "bank" / "types.yaml").read_text(encoding="utf-8"))
    assert t["exists"] is True and t["body"] == source
    assert {"role": "caller", "scope": "session"} in t["usage"][source["session_roles"]["caller"]["type"]]
    assert any(u.get("flow") == "book_visit" for u in t["usage"]["Person"])
    assert "digits" in t["field_types"] and "choice" in t["field_types"]
    assert yamlio.load(files(client)["bank/types.yaml"]) == source


def test_saved_dictionary_bumps_the_domain_and_is_exported(client):
    before = client.get(f"{A}/domains/bank").json()["shared_revision"]
    r = put(client, DOC)
    assert r.status_code == 200, r.text
    assert {"role": "caller", "scope": "session"} in r.json()["usage"]["Person"]
    assert client.get(f"{A}/domains/bank").json()["shared_revision"] == before + 1
    rev = r.json()["revision"]
    assert put(client, DOC).json()["revision"] == rev + 1
    assert yamlio.load(files(client)["bank/types.yaml"]) == DOC   # labels kept as written


T = {"type": "text"}


@pytest.mark.parametrize("bad, word", [
    ({"types": {"person": {"fields": {"name": T}}}}, "capital"),
    ({"types": {"Person": {"fields": {"addr": {"type": "Address"}}}, "Address": {"fields": {"city": T}}}}, "nesting"),
    ({"types": {"Person": {"fields": {"name": "text"}}}}, "needs a type"),          # the engine wants a map per field
    ({"types": {"Person": {"fields": {"kind": {"type": "choice"}}}}}, "choices"),
    ({"types": {"Person": {"fields": {"pin": {"type": "text", "length": 4}}}}}, "digits only"),
    ({"types": {"Person": {"fields": {"x": {"type": "phone"}}}}}, "must be one of"),
    ({"types": {"Person": {"fields": {}}}}, "at least one"),
    ({"types": {"Money": {"scalar": "number"}}}, "at least one"),                     # no scalar types in v1
    ({"types": {"Person": {"fields": {"name": T}, "label": "사람"}}}, "label"),
    ({"types": {}, "session_roles": {"caller": {"type": "Person"}}}, "needs a type"),
    ({"types": {"Person": {"fields": {"name": T}}}, "session_roles": {"agent": {"type": "Person"}}}, "only session role"),
    ({"types": {"Person": {"fields": {"name": T}}}, "roles": {}}, "unknown keys"),
])
def test_bad_dictionary_is_refused_with_the_reason(client, bad, word):
    r = put(client, bad)
    assert r.status_code == 422
    assert any(word in p for p in r.json()["detail"]["problems"]), r.json()


def test_stale_revision_is_a_conflict(client):
    r = client.put(f"{A}/domains/bank/types", json={"body": DOC, "revision": 99, "force": True})
    assert r.status_code == 409


def flow_with_roles(client, roles, nodes_patch=None):
    d = client.get(f"{A}/bots/bank-ko/flows/balance_inquiry").json()
    f = d["flow"] if "flow" in d else d
    header = {**f["header"], **({"roles": roles} if roles else {})}
    nodes = {**f["nodes"], **(nodes_patch or {})}
    return client.put(f"{A}/bots/bank-ko/flows/balance_inquiry",
                      json={"header": header, "start": f["start"], "nodes": nodes, "revision": f["revision"]})


def test_flow_roles_are_saved_exported_and_checked(client):
    put(client, DOC)
    roles = {"booker": {"type": "Person", "label": {"ko": "예약자"}},
             "visitor": {"type": "Person", "default": {"from": "booker"}}}
    bind = {"lookup": {"type": "call", "tool": "get_balance", "bind": {"account_last4": {"role": "caller", "field": "last4"}},
                       "on_ok": "say_balance", "on_error": "say_fail"}}
    r = flow_with_roles(client, roles, bind)
    assert r.status_code == 200, r.text
    text_ = files(client)["bank/ko/flows/balance_inquiry.yaml"]
    doc = yamlio.load(text_)
    assert doc["roles"] == roles and doc["nodes"]["lookup"]["bind"]["account_last4"] == {"role": "caller", "field": "last4"}
    keys = list(doc)
    assert keys.index("roles") == keys.index("buttons") + 1   # export order: roles after buttons, before captures
    uses = client.get(f"{A}/domains/bank/types").json()["usage"]["Person"]
    assert {"role": "booker", "scope": "flow", "bot": "bank-ko", "flow": "balance_inquiry"} in uses
    assert {"role": "visitor", "scope": "flow", "bot": "bank-ko", "flow": "balance_inquiry"} in uses


@pytest.mark.parametrize("roles, word", [
    ({"booker": {"type": "Nobody"}}, "not in the type dictionary"),
    ({"caller": {"type": "Person"}}, "session role"),
    ({"visitor": {"type": "Person", "default": {"from": "visitor"}}}, "another role"),
    ({"visitor": {"type": "Person", "default": {"from": "booker", "ask": "?"}}, "booker": {"type": "Person"}}, "default.from"),
    ({"result": {"type": "Person"}}, "reserved"),
])
def test_bad_flow_roles_are_refused(client, roles, word):
    put(client, DOC)
    r = flow_with_roles(client, roles)
    assert r.status_code == 422
    assert any(word in p for p in r.json()["detail"]["problems"]), r.json()


def test_removing_a_type_or_field_a_scenario_uses_needs_force(client):
    put(client, DOC)
    flow_with_roles(client, {"booker": {"type": "Person"}},
                    {"ask_account": {"type": "ask", "role": "booker", "field": "last4", "prompt": "끝 네 자리를 눌러 주세요.",
                                     "extractor": "digits", "length": 4, "next": "lookup"}})
    no_field = {**DOC, "types": {**DOC["types"], "Person": {"fields": {"name": T}}}}
    r = put(client, no_field, force=False)
    assert r.status_code == 409
    uses = r.json()["detail"]["uses"]
    assert {"bot": "bank-ko", "flow": "balance_inquiry", "node": "ask_account", "type": "Person", "field": "last4"} in uses
    no_type = {"types": {"Plan": DOC["types"]["Plan"]}}
    r = put(client, no_type, force=False)
    assert r.status_code == 409
    assert {"bot": "bank-ko", "flow": "balance_inquiry", "role": "booker", "type": "Person"} in r.json()["detail"]["uses"]
    assert put(client, no_field, force=True).status_code == 200


def test_removing_a_session_role_a_step_reads_needs_force(client):
    put(client, DOC)
    flow_with_roles(client, {}, {"lookup": {"type": "call", "tool": "get_balance", "on_ok": "say_balance", "on_error": "say_fail",
                                            "bind": {"account_last4": {"role": "caller", "field": "last4"}}}})
    r = put(client, {"types": DOC["types"], "session_roles": {}}, force=False)
    assert r.status_code == 409
    assert {"bot": "bank-ko", "flow": "balance_inquiry", "node": "lookup", "role": "caller"} in r.json()["detail"]["uses"]


def test_clearing_the_dictionary_drops_the_file(client):
    put(client, DOC)
    assert put(client, {"types": {}, "session_roles": {}}).status_code == 200
    assert client.get(f"{A}/domains/bank/types").json()["exists"] is False
    assert not any(k.endswith("types.yaml") for k in files(client))


def test_migration_moves_a_raw_types_file_into_the_setting(db_url, session):
    from studio_backend.models import Domain
    session.add(Domain(slug="m", title="m"))
    session.commit()
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.attributes["url"] = db_url
    command.downgrade(cfg, "0002")
    session.execute(text("INSERT INTO domain_file (id, domain_id, path, content, content_type, revision, created_at, "
                         "updated_at) SELECT 'f1', id, 'types.yaml', :c, 'text/yaml', 1, now(), now() FROM domain "
                         "WHERE slug = 'm'"), {"c": yamlio.dump(DOC)})
    session.commit()
    command.upgrade(cfg, "head")
    assert session.execute(text("SELECT count(*) FROM domain_file WHERE path = 'types.yaml'")).scalar() == 0
    body = session.execute(text("SELECT body FROM domain_setting WHERE kind = 'types'")).scalar()
    assert body == DOC
