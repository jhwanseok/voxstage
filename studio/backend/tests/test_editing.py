"""Bot defaults and flow editing (studio UI pass): saves change the draft, validation still has the last word."""

import pytest
from fastapi.testclient import TestClient

from studio_backend import yamlio

A = "/api/v1"


@pytest.fixture()
def client(session, tmp_path, monkeypatch):
    monkeypatch.setenv("STUDIO_EXPORT_ROOT", str(tmp_path / "exports"))
    from studio_backend.main import app
    with TestClient(app) as c:
        assert c.post(f"{A}/domains/import", json={"domain": "bank"}).status_code == 201
        yield c


def bot(c, slug="bank-ko"):
    return c.get(f"{A}/bots/{slug}").json()


def test_settings_map_the_engine_config(client):
    s = client.get(f"{A}/bots/bank-ko/settings").json()
    assert s["lang"] == "ko" and s["domain"] == "bank" and s["has_config_file"]
    assert s["engine"]["ask"] == {"max_reprompts": 2, "on_exceed": "handoff"}
    assert s["engine"]["tools"]["timeout_ms"] == 5000
    assert s["studio_only"] == {"handoff_number": None, "policy": {}}
    assert {"key": "free_transfers_per_month", "flows": ["free_transfers"]} in s["policy_refs"]


def test_engine_change_marks_the_draft_and_is_exported(client):
    s = client.get(f"{A}/bots/bank-ko/settings").json()
    before = bot(client)["draft_revision"]
    eng = s["engine"]
    eng["ask"]["max_reprompts"] = 3
    r = client.put(f"{A}/bots/bank-ko/settings", json={"engine": eng, "revision": s["revision"]})
    assert r.status_code == 200, r.text
    assert r.json()["engine"]["ask"]["max_reprompts"] == 3
    assert bot(client)["draft_revision"] == before + 1
    rep = client.post(f"{A}/bots/bank-ko/validate").json()
    assert rep["ok"], rep["items"]
    pub = client.post(f"{A}/bots/bank-ko/publications", json={"note": "re-prompt 3"})
    assert pub.status_code == 201
    text = client.get(f"{A}/bots/bank-ko/publications/1/files/bank/ko/rules/config.yaml").text
    assert yamlio.load(text)["ask"]["max_reprompts"] == 3
    # a stale revision is refused
    assert client.put(f"{A}/bots/bank-ko/settings", json={"engine": eng, "revision": s["revision"]}).status_code == 409


def test_studio_only_values_do_not_touch_the_draft(client):
    s = client.get(f"{A}/bots/bank-ko/settings").json()
    before = bot(client)["draft_revision"]
    r = client.put(f"{A}/bots/bank-ko/settings", json={
        "title": "은행 상담봇", "revision": s["revision"],
        "studio_only": {"handoff_number": "1588-0000", "policy": {"free_transfers_per_month": "5", "empty": ""}}})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["title"] == "은행 상담봇"
    assert out["studio_only"] == {"handoff_number": "1588-0000", "policy": {"free_transfers_per_month": "5"}}
    assert bot(client)["draft_revision"] == before
    client.post(f"{A}/bots/bank-ko/validate")
    pub = client.post(f"{A}/bots/bank-ko/publications", json={}).json()
    files = client.get(f"{A}/bots/bank-ko/publications/{pub['number']}").json()["files"]
    for f in files:
        assert "1588-0000" not in client.get(f"{A}/bots/bank-ko/publications/{pub['number']}/files/{f['path']}").text


@pytest.mark.parametrize("engine,msg", [
    ({"ask": {"max_reprompts": -1}}, "ask.max_reprompts"),
    ({"fallback": {"max_misses": 0}}, "fallback.max_misses"),
    ({"tools": {"on_exceed": "transfer"}}, "tools.on_exceed"),
    ({"ask": {"wording": "x"}}, "unknown keys"),
    ({"other": {}}, "unknown sections"),
])
def test_bad_engine_values_are_refused(client, engine, msg):
    r = client.put(f"{A}/bots/bank-ko/settings", json={"engine": engine})
    assert r.status_code == 422 and msg in r.text


def test_bad_handoff_number_is_refused(client):
    r = client.put(f"{A}/bots/bank-ko/settings", json={"studio_only": {"handoff_number": "call me"}})
    assert r.status_code == 422


def test_flow_edit_add_connect_delete_and_validate(client):
    d = client.get(f"{A}/bots/bank-ko/flows/transfer").json()
    flow = d["flow"]
    nodes = dict(flow["nodes"])
    # add a say step between say_fail and done, then remove it again
    nodes["say_sorry"] = {"type": "say", "text": "불편을 드려 죄송합니다.", "next": "done"}
    nodes["say_fail"] = {**nodes["say_fail"], "next": "say_sorry"}
    r = client.put(f"{A}/bots/bank-ko/flows/transfer", json={
        "start": flow["start"], "nodes": nodes, "node_order": flow["node_order"], "revision": flow["revision"]})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["flow"]["revision"] == flow["revision"] + 1
    assert out["flow"]["node_order"][-1] == "say_sorry"
    assert {"id": "say_fail:next", "from": "say_fail", "to": "say_sorry", "label": "", "handle": "next"} in out["graph"]["edges"]
    rep = client.post(f"{A}/bots/bank-ko/validate").json()
    assert rep["ok"], rep["items"]
    # stale revision
    stale = client.put(f"{A}/bots/bank-ko/flows/transfer", json={"start": flow["start"], "nodes": nodes,
                                                                  "revision": flow["revision"]})
    assert stale.status_code == 409
    # a dangling link is a draft the engine refuses, mapped to the node
    nodes["say_fail"] = {**nodes["say_fail"], "next": "nowhere"}
    del nodes["say_sorry"]
    r = client.put(f"{A}/bots/bank-ko/flows/transfer", json={"start": flow["start"], "nodes": nodes,
                                                              "revision": out["flow"]["revision"]})
    assert r.status_code == 200
    rep = client.post(f"{A}/bots/bank-ko/validate").json()
    assert not rep["ok"]
    assert any(i["flow_id"] == "transfer" for i in rep["items"])
    assert client.post(f"{A}/bots/bank-ko/publications", json={}).status_code == 422


def test_flow_layout_rows_of_removed_nodes_are_dropped(client):
    d = client.get(f"{A}/bots/bank-ko/flows/transfer").json()
    client.put(f"{A}/bots/bank-ko/flows/transfer/layout", json={"direction": "TB",
               "nodes": {n: {"x": 1, "y": 2} for n in d["flow"]["nodes"]}})
    nodes = {k: v for k, v in d["flow"]["nodes"].items() if k != "say_fail"}
    nodes["make"] = {**nodes["make"], "on_error": "done"}
    client.put(f"{A}/bots/bank-ko/flows/transfer", json={"start": "ask_amount", "nodes": nodes,
                                                          "revision": d["flow"]["revision"]})
    lay = client.get(f"{A}/bots/bank-ko/flows/transfer").json()["layout"]
    assert "say_fail" not in lay["nodes"] and "make" in lay["nodes"] and lay["direction"] == "TB"


@pytest.mark.parametrize("body,code", [
    ({"start": "a", "nodes": {"a": {"type": "dance"}}}, 422),
    ({"start": "b", "nodes": {"a": {"type": "end"}}}, 422),
    ({"start": "a", "nodes": {"1a": {"type": "end"}}}, 422),
    ({"start": "a", "nodes": {"a": {"type": "end"}}, "header": {"colour": "red"}}, 422),
])
def test_bad_flow_shapes_are_refused(client, body, code):
    assert client.put(f"{A}/bots/bank-ko/flows/transfer", json=body).status_code == code


def test_create_and_delete_flow(client):
    r = client.post(f"{A}/bots/bank-ko/flows", json={"id": "new_one"})
    assert r.status_code == 201 and r.json()["flow"]["start"] == "done"
    assert client.post(f"{A}/bots/bank-ko/flows", json={"id": "new_one"}).status_code == 409
    assert client.post(f"{A}/bots/bank-ko/flows", json={"id": "Bad-Id"}).status_code == 422
    assert client.delete(f"{A}/bots/bank-ko/flows/new_one").status_code == 204
    assert client.get(f"{A}/bots/bank-ko/flows/new_one").status_code == 404
