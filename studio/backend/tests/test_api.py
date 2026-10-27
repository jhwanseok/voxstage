import pytest
from fastapi.testclient import TestClient

from voxstage.domain_pack import DomainPack
from voxstage.rules.flows import load_flows

from conftest import DOMAINS

A = "/api/v1"


@pytest.fixture()
def client(session, tmp_path, monkeypatch):
    monkeypatch.setenv("STUDIO_EXPORT_ROOT", str(tmp_path / "exports"))
    from studio_backend.main import app
    with TestClient(app) as c:
        r = c.post(f"{A}/domains/import", json={"domain": "bank"})
        assert r.status_code == 201, r.text
        yield c


def test_import_twice_conflicts_and_replace_works(client):
    assert client.post(f"{A}/domains/import", json={"domain": "bank"}).status_code == 409
    assert client.post(f"{A}/domains/import", json={"domain": "bank", "replace": True}).status_code == 201
    bots = client.get(f"{A}/bots").json()
    assert [b["slug"] for b in bots] == ["bank-en", "bank-ko"]
    assert client.get(f"{A}/domains/importable").json() == ["bank", "shop", "telecom"]
    assert client.get(f"{A}/me").json()["roles"] == ["admin", "editor", "publisher"]


def test_faq_edit_revision_conflict_and_validation_publish(client):
    faq = client.get(f"{A}/bots/bank-en/faq").json()
    e = faq[0]
    assert e["pattern"] and e["paraphrases"]
    r = client.put(f"{A}/bots/bank-en/faq/{e['id']}", json={**e, "answer": "Changed answer.", "revision": e["revision"]})
    assert r.status_code == 200 and r.json()["revision"] == e["revision"] + 1
    stale = client.put(f"{A}/bots/bank-en/faq/{e['id']}", json={**e, "revision": e["revision"]})
    assert stale.status_code == 409
    # a half-written entry can be saved, but validation and publish refuse it
    bad = client.put(f"{A}/bots/bank-en/faq/{e['id']}", json={**e, "revision": None, "paraphrases": ["only one"]})
    assert bad.status_code == 200
    rep = client.post(f"{A}/bots/bank-en/validate").json()
    assert not rep["ok"] and rep["items"][0]["source"] == "engine"
    assert client.get(f"{A}/bots/bank-en").json()["valid"] is False
    pub = client.post(f"{A}/bots/bank-en/publications", json={"note": "x"})
    assert pub.status_code == 422 and pub.json()["report"]["ok"] is False
    # fix it, publish, and the export directory is a domains_dir the engine loads
    ok = client.put(f"{A}/bots/bank-en/faq/{e['id']}", json={**e, "revision": None, "answer": "Changed answer."})
    assert ok.status_code == 200
    pub = client.post(f"{A}/bots/bank-en/publications", json={"note": "first"})
    assert pub.status_code == 201 and pub.json()["number"] == 1
    status = client.get(f"{A}/bots/bank-en").json()
    assert status["valid"] and not status["has_unpublished_changes"]
    from studio_backend.service import export_root
    root = f"{export_root()}/bank-en"
    pack = DomainPack.load(root, "bank", "en")
    assert pack.answers[e["id"]] == "Changed answer."
    load_flows(f"{pack.base_dir}/flows", pack.tools_path, pack.sensitive_slots, pack.notices)
    assert client.post(f"{A}/bots/bank-en/publications", json={"note": "again"}).status_code == 409
    hist = client.get(f"{A}/bots/bank-en/publications").json()
    assert [h["number"] for h in hist] == [1] and hist[0]["file_count"] > 10
    f = client.get(f"{A}/bots/bank-en/publications/1/files/bank/en/faq.yaml")
    assert "Changed answer." in f.text
    assert client.get(f"{A}/bots/bank-en/publications/1/export.zip").status_code == 200


def test_shared_tool_change_affects_both_bots(client):
    tools = client.get(f"{A}/domains/bank/tools").json()
    t = next(x for x in tools if x["name"] == "get_transfer_fee")
    r = client.put(f"{A}/domains/bank/tools/get_transfer_fee", json={"body": t["body"], "revision": t["revision"]})
    assert r.status_code == 200 and r.json()["affects_bots"] == ["bank-en", "bank-ko"]
    assert {x["flow"] for x in r.json()["used_by_flows"]} == {"transfer_fee"}
    assert client.delete(f"{A}/domains/bank/tools/get_transfer_fee").status_code == 409
    client.post(f"{A}/bots/bank-en/validate")
    client.post(f"{A}/bots/bank-ko/validate")
    assert all(b["valid"] for b in client.get(f"{A}/bots").json())
    client.put(f"{A}/domains/bank/tools/get_transfer_fee", json={"body": t["body"]})
    assert not any(b["validated"] for b in client.get(f"{A}/bots").json())    # shared change makes both stale


def test_flow_graph_has_edge_labels_and_layout_is_not_content(client):
    flows = client.get(f"{A}/bots/bank-en/flows").json()
    assert {"transfer", "identity_check"} <= {f["id"] for f in flows}
    g = client.get(f"{A}/bots/bank-en/flows/transfer").json()
    labels = {(e["from"], e["label"], e["to"]) for e in g["graph"]["edges"]}
    assert ("confirm", "yes", "make") in labels and ("confirm", "no", "done") in labels
    assert ("make", "ok", "say_done") in labels and ("make", "error", "say_fail") in labels
    before = client.get(f"{A}/bots/bank-en").json()["draft_revision"]
    r = client.put(f"{A}/bots/bank-en/flows/transfer/layout",
                   json={"viewport": {"x": 1, "y": 2, "zoom": 1}, "direction": "LR",
                         "nodes": {"ask_amount": {"x": 10, "y": 20}, "ghost": {"x": 0, "y": 0}}})
    assert r.status_code == 204
    after = client.get(f"{A}/bots/bank-en/flows/transfer").json()
    assert after["layout"]["nodes"] == {"ask_amount": {"x": 10.0, "y": 20.0, "collapsed": False}}
    assert client.get(f"{A}/bots/bank-en").json()["draft_revision"] == before


def test_every_flow_of_every_domain_has_a_consistent_graph(client):
    for d in ("shop", "telecom"):
        assert client.post(f"{A}/domains/import", json={"domain": d}).status_code == 201
    kinds = set()
    for bot in client.get(f"{A}/bots").json():
        for f in client.get(f"{A}/bots/{bot['slug']}/flows").json():
            g = client.get(f"{A}/bots/{bot['slug']}/flows/{f['id']}").json()["graph"]
            ids = {n["id"] for n in g["nodes"]}
            assert g["start"] in ids
            for e in g["edges"]:
                assert e["from"] in ids and e["to"] in ids, (bot["slug"], f["id"], e)
            kinds |= {n["type"] for n in g["nodes"]}
    assert {"say", "ask", "form", "confirm", "call", "branch", "notices", "end"} <= kinds
