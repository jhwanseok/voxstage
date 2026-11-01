"""ST2: comparing publications (diff by meaning and as text). Rollback, retention and roles follow in this file."""

import pytest
from fastapi.testclient import TestClient

A = "/api/v1"
BOT = "bank-ko"


@pytest.fixture()
def client(session, tmp_path, monkeypatch):
    monkeypatch.setenv("STUDIO_EXPORT_ROOT", str(tmp_path / "exports"))
    from studio_backend.main import app
    with TestClient(app) as c:
        assert c.post(f"{A}/domains/import", json={"domain": "bank"}).status_code == 201
        yield c


def publish(c, note=""):
    r = c.post(f"{A}/bots/{BOT}/publications", json={"note": note})
    assert r.status_code == 201, r.text
    return r.json()["number"]


def edit_faq(c, **fields):
    e = c.get(f"{A}/bots/{BOT}/faq").json()[0]
    r = c.put(f"{A}/bots/{BOT}/faq/{e['id']}", json={**e, "revision": None, **fields})
    assert r.status_code == 200, r.text
    return e


def edit_flow(c, change):
    d = c.get(f"{A}/bots/{BOT}/flows/transfer").json()["flow"]
    nodes = {k: dict(v) for k, v in d["nodes"].items()}
    change(nodes)
    r = c.put(f"{A}/bots/{BOT}/flows/transfer", json={"start": d["start"], "nodes": nodes,
                                                      "node_order": d["node_order"], "revision": d["revision"]})
    assert r.status_code == 200, r.text


def two_versions(c):
    """Publication 1 as imported, publication 2 with a changed answer, a new step, a rewired step and a new setting."""
    publish(c, "first")
    e = edit_faq(c, answer="바뀐 답변입니다.")

    def change(nodes):
        nodes["say_sorry"] = {"type": "say", "text": "불편을 드려 죄송합니다.", "next": "done"}
        nodes["say_fail"] = {**nodes["say_fail"], "next": "say_sorry"}
    edit_flow(c, change)
    s = c.get(f"{A}/bots/{BOT}/settings").json()
    eng = s["engine"]
    eng["ask"]["max_reprompts"] = 3
    assert c.put(f"{A}/bots/{BOT}/settings", json={"engine": eng, "revision": s["revision"]}).status_code == 200
    publish(c, "second")
    return e


def test_diff_against_the_previous_publication_names_what_changed(client):
    e = two_versions(client)
    d = client.get(f"{A}/bots/{BOT}/publications/2/diff").json()
    assert d["base"] == {"kind": "publication", "number": 1} and d["target"] == {"kind": "publication", "number": 2}
    changed = {f["path"]: f for f in d["files"]}
    assert set(changed) == {"bank/ko/faq.yaml", "bank/ko/flows/transfer.yaml", "bank/ko/rules/config.yaml"}
    assert all(f["status"] == "changed" for f in changed.values())
    assert "+      answer: 바뀐 답변입니다." in changed["bank/ko/faq.yaml"]["unified"] or "바뀐 답변입니다." in changed["bank/ko/faq.yaml"]["unified"]
    assert changed["bank/ko/faq.yaml"]["unified"].startswith("--- a/bank/ko/faq.yaml\n+++ b/bank/ko/faq.yaml")
    s = d["summary"]
    assert s["faq"]["changed"] == [{"id": e["id"], "question": e["question"], "fields": ["answer"]}]
    assert s["faq"]["added"] == s["faq"]["removed"] == []
    flow = s["flows"]["changed"][0]
    assert flow["id"] == "transfer"
    assert flow["steps_added"] == [{"id": "say_sorry", "type": "say"}]
    assert flow["rewired"] == [{"step": "say_fail", "handle": "next", "before": "done", "after": "say_sorry"}]
    assert flow["steps_changed"] == [] and flow["steps_removed"] == []
    assert [x["kind"] for x in s["settings"]] == ["config"] and s["settings"][0]["keys"] == ["ask"]
    assert s["tools"] == {"added": [], "removed": [], "changed": []} and not s["empty"]


def test_the_first_publication_has_nothing_before_it_and_numbers_pick_the_base(client):
    two_versions(client)
    first = client.get(f"{A}/bots/{BOT}/publications/1/diff").json()
    assert first["base"]["kind"] == "none"
    assert {f["status"] for f in first["files"]} == {"added"} and len(first["files"]) > 5
    back = client.get(f"{A}/bots/{BOT}/publications/1/diff?against=2").json()      # from 2 to 1: the undo
    assert back["base"] == {"kind": "publication", "number": 2}
    assert back["summary"]["flows"]["changed"][0]["steps_removed"] == [{"id": "say_sorry", "type": "say"}]
    assert client.get(f"{A}/bots/{BOT}/publications/1/diff?against=9").status_code == 404
    assert client.get(f"{A}/bots/{BOT}/publications/1/diff?against=oops").status_code == 422


def test_diff_against_the_draft_is_what_a_rollback_would_change(client):
    two_versions(client)
    same = client.get(f"{A}/bots/{BOT}/publications/2/diff?against=draft").json()
    assert same["base"]["kind"] == "draft" and same["files"] == [] and same["summary"]["empty"]
    edit_faq(client, answer="초안에서 또 바꿈")
    d = client.get(f"{A}/bots/{BOT}/publications/2/diff?against=draft").json()
    assert [f["path"] for f in d["files"]] == ["bank/ko/faq.yaml"]
    assert d["summary"]["faq"]["changed"][0]["fields"] == ["answer"]


def test_changes_since_the_newest_publication_for_the_publish_dialog(client):
    first = client.get(f"{A}/bots/{BOT}/changes").json()
    assert first["base"]["kind"] == "none" and first["summary"]["faq"]["added"]      # never published: all new
    publish(client)
    assert client.get(f"{A}/bots/{BOT}/changes").json()["summary"]["empty"]
    edit_faq(client, question="바뀐 질문")
    c = client.get(f"{A}/bots/{BOT}/changes").json()
    assert c["base"] == {"kind": "publication", "number": 1} and c["target"]["kind"] == "draft"
    assert c["summary"]["faq"]["changed"][0]["fields"] == ["question"]


def test_summary_names_added_and_removed_faq_entries_and_tools(client):
    publish(client)
    e = client.get(f"{A}/bots/{BOT}/faq").json()[0]
    assert client.delete(f"{A}/bots/{BOT}/faq/{e['id']}").status_code == 204
    r = client.post(f"{A}/bots/{BOT}/faq", json={"id": "brand_new", "question": "새 질문", "answer": "새 답",
                                                 "paraphrases": None, "asr_variants": None, "pattern": None})
    assert r.status_code == 201, r.text
    tool = client.get(f"{A}/domains/bank/tools").json()[0]
    body = {**tool["body"], "retry": 0}
    r = client.put(f"{A}/domains/bank/tools/{tool['name']}", json={"body": body, "revision": tool["revision"]})
    assert r.status_code == 200, r.text
    s = client.get(f"{A}/bots/{BOT}/changes").json()["summary"]
    assert [x["id"] for x in s["faq"]["added"]] == ["brand_new"]
    assert [x["id"] for x in s["faq"]["removed"]] == [e["id"]]
    assert s["tools"]["changed"] == [{"name": tool["name"], "fields": ["retry"]}]
