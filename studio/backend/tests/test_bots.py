"""새 상담봇 만들기: POST /bots (empty or copy), the language starter, and what a copy still has to translate."""

import pytest
from fastapi.testclient import TestClient

from studio_backend import bots

A = "/api/v1"


@pytest.fixture()
def client(session, tmp_path, monkeypatch):
    monkeypatch.setenv("STUDIO_EXPORT_ROOT", str(tmp_path / "exports"))
    from studio_backend.main import app
    with TestClient(app) as c:
        yield c


def new_clinic(client, lang="ko", **extra):
    body = {"domain": "clinic", "domain_title": "병원 예약", "lang": lang, "title": "병원 상담봇", **extra}
    return client.post(f"{A}/bots", json=body)


def test_every_engine_language_has_a_starter(client):
    assert client.get(f"{A}/languages").json() == list(bots.engine_langs())
    for lang in bots.engine_langs():
        for rel in ("notices.yaml", *(f"rules/{k}.yaml" for k in bots.STARTER_KINDS)):
            assert (bots.STARTERS / lang / rel).exists(), (lang, rel)


@pytest.mark.parametrize("lang", bots.engine_langs())
def test_empty_bot_in_a_new_domain_validates_and_chats(client, lang):
    r = new_clinic(client, lang, settings={"engine": {"ask": {"max_reprompts": 1}},
                                           "studio_only": {"handoff_number": "1588-0000"}})
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["slug"] == f"clinic-{lang}" and b["domain_title"] == "병원 예약" and b["title"] == "병원 상담봇"
    assert b["counts"] == {"faq": 0, "flows": 0, "tools": 0} and b["to_translate"] == 0
    s = client.get(f"{A}/bots/clinic-{lang}/settings").json()
    assert s["engine"]["ask"]["max_reprompts"] == 1 and s["engine"]["fallback"]["max_misses"] == 3
    assert s["studio_only"]["handoff_number"] == "1588-0000" and s["domain_title"] == "병원 예약"
    rep = client.post(f"{A}/bots/clinic-{lang}/validate").json()
    assert rep["ok"], rep["items"]
    # the 기본 설정 form saves on an empty bot without breaking it (the starter holds what config.yaml needs)
    s["engine"]["fallback"]["max_misses"] = 2
    assert client.put(f"{A}/bots/clinic-{lang}/settings", json={"engine": s["engine"], "revision": s["revision"]}).status_code == 200
    assert client.post(f"{A}/bots/clinic-{lang}/validate").json()["ok"]
    chat = client.post(f"{A}/bots/clinic-{lang}/chat", json={})
    assert chat.status_code == 201, chat.text
    turn = client.post(f"{A}/bots/clinic-{lang}/chat/{chat.json()['id']}/turns", json={"text": "hello"}).json()
    assert turn["reply"]   # the fallback wording of the starter
    assert client.post(f"{A}/bots/clinic-{lang}/publications", json={"note": "first"}).status_code == 201


def test_rules_for_a_new_bot(client):
    assert new_clinic(client).status_code == 201
    taken = new_clinic(client)
    assert taken.status_code == 409 and taken.json()["detail"]["reason"] == "exists"
    assert client.post(f"{A}/bots", json={"domain": "clinic", "lang": "ja"}).status_code == 422
    assert client.post(f"{A}/bots", json={"domain": "Clinic 2", "domain_title": "x", "lang": "ko"}).status_code == 422
    assert client.post(f"{A}/bots", json={"domain": "dental", "lang": "ko"}).status_code == 422          # no title
    in_repo = client.post(f"{A}/bots", json={"domain": "bank", "domain_title": "은행", "lang": "ko"})
    assert in_repo.status_code == 409 and in_repo.json()["detail"]["reason"] == "in_repo"
    assert client.post(f"{A}/bots", json={"domain": "dental", "domain_title": "치과", "lang": "ko", "start": "copy",
                                          "copy_from": "clinic-ko"}).status_code == 422             # other domain
    assert new_clinic(client, "en", start="copy", copy_from="nope").status_code == 422
    assert new_clinic(client, "en", settings={"engine": {"ask": {"max_reprompts": -1}}}).status_code == 422
    assert new_clinic(client, "en", settings={"studio_only": {"handoff_number": "call me"}}).status_code == 422
    assert client.get(f"{A}/bots/clinic-en").status_code == 404     # nothing was half-made


def test_copy_takes_structure_and_marks_texts_to_translate(client):
    assert new_clinic(client, settings={"engine": {"fallback": {"max_misses": 4}},
                                        "studio_only": {"handoff_number": "02-000-0000"}}).status_code == 201
    faq = {"id": "hours", "question": "진료 시간이 어떻게 되나요?", "answer": "평일 9시부터 6시까지예요.",
           "paraphrases": ["몇 시까지 해요", "진료 시간", "언제 문 열어요"], "asr_variants": ["진료 시가"],
           "pattern": {"all_of": [["진료", "몇 시"]]}}
    assert client.post(f"{A}/bots/clinic-ko/faq", json=faq).status_code == 201
    assert client.post(f"{A}/bots/clinic-ko/flows", json={"id": "book"}).status_code == 201
    f = client.get(f"{A}/bots/clinic-ko/flows/book").json()["flow"]
    nodes = {"hello": {"type": "say", "text": "예약을 도와드릴게요.", "next": "done"}, "done": {"type": "end"}}
    r = client.put(f"{A}/bots/clinic-ko/flows/book", json={"header": {"triggers": {"any_of": ["예약"]}}, "start": "hello",
                                                         "nodes": nodes, "revision": f["revision"]})
    assert r.status_code == 200, r.text
    client.put(f"{A}/bots/clinic-ko/flows/book/layout", json={"nodes": {"hello": {"x": 10, "y": 20}}})

    r = new_clinic(client, "en", title="Clinic bot", start="copy", copy_from="clinic-ko",
                   settings={"engine": {"ask": {"max_reprompts": 0}}})
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["copied_from"] == "clinic-ko" and b["translate"] == {"faq": ["hours"], "flows": ["book"], "notices": []}
    assert b["to_translate"] == 2 and b["counts"]["faq"] == 1 and b["counts"]["flows"] == 1
    got = client.get(f"{A}/bots/clinic-en/flows/book").json()
    assert got["flow"]["nodes"] == nodes and got["layout"]["nodes"]["hello"] == {"x": 10, "y": 20, "collapsed": False}
    s = client.get(f"{A}/bots/clinic-en/settings").json()
    assert s["engine"]["fallback"]["max_misses"] == 4 and s["engine"]["ask"]["max_reprompts"] == 0
    assert s["studio_only"]["handoff_number"] == "02-000-0000"
    assert client.post(f"{A}/bots/clinic-en/validate").json()["ok"]
    # the language words come from the English starter, not from the Korean sibling
    from studio_backend.db import session_scope
    from studio_backend.models import Bot
    from studio_backend.portable import export_bot
    with session_scope() as s2:
        files = export_bot(s2, s2.query(Bot).filter_by(slug="clinic-en").one())
    assert "yes_words" in files["clinic/en/rules/confirm.yaml"] and "yeah" in files["clinic/en/rules/confirm.yaml"]
    from studio_backend import yamlio
    assert "I didn't catch that" in yamlio.load(files["clinic/en/notices.yaml"])["wording"]["fallback.miss"]
    assert "lang: en" in files["clinic/en/faq.yaml"]

    rows = client.get(f"{A}/bots/clinic-en/faq").json()
    assert rows[0]["to_translate"] is True
    assert client.get(f"{A}/bots/clinic-en/flows").json()[0]["to_translate"] is True
    assert client.get(f"{A}/bots/clinic-ko/faq").json()[0]["to_translate"] is False
    e = rows[0]
    client.put(f"{A}/bots/clinic-en/faq/hours", json={**e, "question": "What are your hours?", "revision": e["revision"]})
    assert client.get(f"{A}/bots/clinic-en").json()["translate"]["faq"] == []
    assert client.put(f"{A}/bots/clinic-en/translation", json={"flows": ["other"]}).status_code == 422
    assert client.put(f"{A}/bots/clinic-en/translation", json={}).json() == {"faq": [], "flows": [], "notices": []}
    assert client.get(f"{A}/bots/clinic-en").json()["to_translate"] == 0


def test_copy_of_a_real_bot_validates_and_keeps_fixed_notices_to_translate(client):
    """bank-ko copied into English, with bank-en removed first: the whole engine pack loads."""
    assert client.post(f"{A}/domains/import", json={"domain": "bank"}).status_code == 201
    from studio_backend.db import session_scope
    from studio_backend.models import Bot
    with session_scope() as s:
        s.delete(s.query(Bot).filter_by(slug="bank-en").one())
        s.commit()
    r = client.post(f"{A}/bots", json={"domain": "bank", "lang": "en", "title": "Bank bot", "start": "copy",
                                       "copy_from": "bank-ko"})
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["translate"]["notices"] == ["time_deposit_early_close"] and len(b["translate"]["flows"]) == 11
    rep = client.post(f"{A}/bots/bank-en/validate").json()
    assert rep["ok"], rep["items"]


def test_delete_a_bot_and_the_domain_with_its_last_bot(client, tmp_path):
    assert new_clinic(client).status_code == 201
    assert new_clinic(client, "en", start="copy", copy_from="clinic-ko").status_code == 201
    assert client.post(f"{A}/bots/clinic-ko/publications", json={"note": "v1"}).status_code == 201
    assert (tmp_path / "exports" / "clinic-ko").is_dir()
    chat = client.post(f"{A}/bots/clinic-ko/chat", json={}).json()["id"]
    assert client.get(f"{A}/bots/clinic-ko/delete-impact").json() ==         {"faq": 0, "flows": 0, "publications": 1, "last_of_domain": False, "domain_tools": 0}

    r = client.delete(f"{A}/bots/clinic-ko")
    assert r.status_code == 200 and r.json() == {"deleted": "clinic-ko", "domain_deleted": None}
    assert client.get(f"{A}/bots/clinic-ko").status_code == 404
    assert not (tmp_path / "exports" / "clinic-ko").exists()
    assert client.post(f"{A}/bots/clinic-ko/chat/{chat}/turns", json={"text": "hi"}).status_code == 404
    # the copy keeps working; its source is gone
    assert client.get(f"{A}/bots/clinic-en").json()["copied_from"] == "clinic-ko"
    assert client.get(f"{A}/bots/clinic-en/delete-impact").json()["last_of_domain"] is True

    r = client.delete(f"{A}/bots/clinic-en")
    assert r.json() == {"deleted": "clinic-en", "domain_deleted": "clinic"}
    assert client.get(f"{A}/domains/clinic").status_code == 404
    assert new_clinic(client).status_code == 201          # the id is free again
    assert client.delete(f"{A}/bots/nope").status_code == 404


def test_deleting_an_imported_domain_lets_it_be_imported_again(client):
    assert client.post(f"{A}/domains/import", json={"domain": "bank"}).status_code == 201
    assert client.delete(f"{A}/bots/bank-en").status_code == 200
    assert client.delete(f"{A}/bots/bank-ko").json()["domain_deleted"] == "bank"
    from studio_backend.db import session_scope
    from studio_backend.models import Tool
    with session_scope() as s:
        assert s.query(Tool).count() == 0
    assert client.post(f"{A}/domains/import", json={"domain": "bank"}).status_code == 201
