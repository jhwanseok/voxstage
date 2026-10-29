"""대화로 테스트: a validated draft answers typed turns through the engine, with what happened in each turn."""

import pytest
from fastapi.testclient import TestClient

A = "/api/v1"


@pytest.fixture()
def client(session, tmp_path, monkeypatch):
    monkeypatch.setenv("STUDIO_EXPORT_ROOT", str(tmp_path / "exports"))
    from studio_backend.main import app
    with TestClient(app) as c:
        assert c.post(f"{A}/domains/import", json={"domain": "bank"}).status_code == 201
        yield c


def say(c, sid, text, kind="text"):
    r = c.post(f"{A}/bots/bank-ko/chat/{sid}/turns", json={"kind": kind, "text": text})
    assert r.status_code == 200, r.text
    return r.json()


def test_only_a_validated_draft_runs(client):
    r = client.post(f"{A}/bots/bank-ko/chat", json={})
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "not_validated"
    assert client.post(f"{A}/bots/bank-ko/validate").json()["ok"]
    assert client.post(f"{A}/bots/bank-ko/chat", json={}).status_code == 201


def test_the_visitor_defaults_to_the_booker_turn_by_turn(client):
    """The engine's own case C14-002, typed: the roles, the default step and the bound call show in the turns."""
    client.post(f"{A}/bots/bank-ko/validate")
    sid = client.post(f"{A}/bots/bank-ko/chat", json={}).json()["id"]
    t1 = say(client, sid, "영업점 방문 예약을 하고 싶어요")
    assert t1["after"] == {"flow": "book_visit", "node": "ask_first"} and "휴대폰" in t1["reply"]
    t2 = say(client, sid, "5580", kind="digits")
    assert t2["changed"] == ["booker.phone_last4"] and t2["attributes"]["booker.phone_last4"] == "5580"
    assert t2["after"]["node"] == "same_person"
    t3 = say(client, sid, "네")
    assert t3["attributes"]["visitor.phone_last4"] == "5580"
    [call] = t3["calls"]
    assert call["tool"] == "book_visit" and call["ok"] and call["args"] == {"booker_phone": "5580", "visitor_phone": "5580"}
    assert call["data"] == {"reference": "BV1001"}
    assert call["step"]["node"] == "call" and call["step"]["bind"]["visitor_phone"] == {"role": "visitor", "field": "phone_last4"}
    assert "BV1001" in t3["reply"] and t3["stale"] is False


def test_reasks_and_restart(client):
    client.post(f"{A}/bots/bank-ko/validate")
    sid = client.post(f"{A}/bots/bank-ko/chat", json={}).json()["id"]
    say(client, sid, "영업점 방문 예약을 하고 싶어요")
    t = say(client, sid, "잘 모르겠어요")
    assert t["meta"].get("ask_misses") == 1 and t["after"]["node"] == "ask_first"
    assert client.delete(f"{A}/bots/bank-ko/chat/{sid}").status_code == 204
    assert client.post(f"{A}/bots/bank-ko/chat/{sid}/turns", json={"text": "네"}).status_code == 404


def test_a_draft_change_marks_the_session_stale(client):
    client.post(f"{A}/bots/bank-ko/validate")
    sid = client.post(f"{A}/bots/bank-ko/chat", json={}).json()["id"]
    s = client.get(f"{A}/bots/bank-ko/settings").json()
    client.put(f"{A}/bots/bank-ko/settings", json={"title": "다른 이름", "revision": s["revision"]})
    eng = s["engine"]
    eng["ask"]["max_reprompts"] = 3
    client.put(f"{A}/bots/bank-ko/settings", json={"engine": eng, "revision": s["revision"]})
    assert say(client, sid, "안녕하세요")["stale"] is True


def test_bad_input_is_refused(client):
    client.post(f"{A}/bots/bank-ko/validate")
    sid = client.post(f"{A}/bots/bank-ko/chat", json={}).json()["id"]
    assert client.post(f"{A}/bots/bank-ko/chat/{sid}/turns", json={"kind": "digits", "text": "12a"}).status_code == 422
    assert client.post(f"{A}/bots/bank-ko/chat/{sid}/turns", json={"kind": "text", "text": "  "}).status_code == 422
    assert client.post(f"{A}/bots/bank-en/chat/{sid}/turns", json={"text": "hi"}).status_code == 404   # another bot's id
