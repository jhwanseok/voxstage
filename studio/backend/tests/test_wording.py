"""ST3: 안내 문구 (wording and fixed notices), 응답 규칙 (rule words), slot lists, the policy warning, translation tracking."""

import pathlib

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from studio_backend import yamlio
from tests.conftest import BACKEND, DOMAINS

A = "/api/v1"


@pytest.fixture()
def client(session, tmp_path, monkeypatch):
    monkeypatch.setenv("STUDIO_EXPORT_ROOT", str(tmp_path / "exports"))
    from studio_backend.main import app
    with TestClient(app) as c:
        assert c.post(f"{A}/domains/import", json={"domain": "bank"}).status_code == 201
        yield c


def notices(c, slug="bank-ko"):
    return c.get(f"{A}/bots/{slug}/notices").json()


def save(c, n, slug="bank-ko", **over):
    body = {"notices": n["notices"], "wording": n["wording"], "revision": n["revision"], **over}
    return c.put(f"{A}/bots/{slug}/notices", json=body)


def problems(r):
    assert r.status_code == 422, r.text
    return {p["field"]: p["message"] for p in r.json()["detail"]["problems"]}


# --- notices.yaml as a modelled setting ---

def test_notices_is_a_setting_and_the_export_equals_the_source(client):
    n = notices(client)
    assert n["exists"] and [x["id"] for x in n["notices"]] == ["time_deposit_early_close"]
    assert set(n["wording"]) == set(n["meaning"]) and len(n["wording"]) == 17
    assert n["placeholder_keys"] == ["readback", "correction.offer"]
    pub = client.post(f"{A}/bots/bank-ko/publications", json={"note": "x"})
    assert pub.status_code == 201, pub.text
    exported = client.get(f"{A}/bots/bank-ko/publications/1/files/bank/ko/notices.yaml").text
    source = pathlib.Path(DOMAINS / "bank" / "ko" / "notices.yaml").read_text(encoding="utf-8")
    assert yamlio.load(exported) == yamlio.load(source)


def test_migration_moves_a_raw_notices_file_into_the_setting(db_url, session):
    from studio_backend.models import Bot, Domain
    d = Domain(slug="m", title="m")
    session.add(d)
    session.flush()
    session.add(Bot(domain_id=d.id, lang="ko", slug="m-ko", title="m"))
    session.commit()
    doc = {"notices": {}, "wording": {"readback": "{value}요."}}
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.attributes["url"] = db_url
    command.downgrade(cfg, "0004")
    session.execute(text("INSERT INTO domain_file (id, bot_id, path, content, content_type, revision, created_at, "
                         "updated_at) SELECT 'f1', id, 'notices.yaml', :c, 'text/yaml', 1, now(), now() FROM bot "
                         "WHERE slug = 'm-ko'"), {"c": yamlio.dump(doc)})
    session.commit()
    command.upgrade(cfg, "head")
    assert session.execute(text("SELECT count(*) FROM domain_file WHERE path = 'notices.yaml'")).scalar() == 0
    assert session.execute(text("SELECT body FROM domain_setting WHERE kind = 'notices'")).scalar() == doc


# --- wording and fixed notices ---

def test_wording_text_is_saved_published_and_spoken(client):
    n = notices(client)
    n["wording"]["fallback.miss"] = "다시 한 번만 말씀해 주세요."
    r = save(client, n)
    assert r.status_code == 200, r.text
    assert r.json()["wording"]["fallback.miss"] == "다시 한 번만 말씀해 주세요." and r.json()["revision"] == n["revision"] + 1
    assert client.post(f"{A}/bots/bank-ko/publications", json={"note": "wording"}).status_code == 201
    text_ = client.get(f"{A}/bots/bank-ko/publications/1/files/bank/ko/notices.yaml").text
    assert yamlio.load(text_)["wording"]["fallback.miss"] == "다시 한 번만 말씀해 주세요."
    chat = client.post(f"{A}/bots/bank-ko/chat", json={}).json()
    turn = client.post(f"{A}/bots/bank-ko/chat/{chat['id']}/turns", json={"text": "ㅋㅋㅋㅋ"}).json()
    assert turn["reply"] == "다시 한 번만 말씀해 주세요."


def test_wording_checks(client):
    n = notices(client)
    n["wording"]["readback"] = "읽어 드릴게요"
    n["wording"]["fallback.miss"] = "{value}를 못 알아들었어요."
    n["wording"]["ask.invalid"] = "  "
    p = problems(save(client, n))
    assert "{value}" in p["wording.readback"] and "쓸 수 없습니다" in p["wording.fallback.miss"]
    assert p["wording.ask.invalid"]
    n = notices(client)
    del n["wording"]["call.exceed"]
    assert "wording" in problems(save(client, n))
    n = notices(client)
    n["wording"]["new.key"] = "x"
    assert "wording" in problems(save(client, n))


def test_fixed_notice_checks_and_renumbering(client):
    n = notices(client)
    add = [{"id": "fees", "text": "수수료가 있을 수 있습니다.", "applies_when": "amount > 100"}]
    r = save(client, n, notices=[*add, *n["notices"]])
    assert r.status_code == 200, r.text
    got = r.json()["notices"]
    assert [x["id"] for x in got] == ["fees", "time_deposit_early_close"] and got[0]["applies_when"] == "amount > 100"
    for bad, field in (({"id": "x y", "text": "t"}, "notices.x y.id"),
                       ({"id": "a1", "text": "{x}"}, "notices.a1.text"),
                       ({"id": "a1", "text": ""}, "notices.a1.text"),
                       ({"id": "a1", "text": "t", "applies_when": "nothere > 1"}, "notices.a1.applies_when"),
                       ({"id": "a1", "text": "t", "applies_when": "__import__('os')"}, "notices.a1.applies_when")):
        n2 = notices(client)
        assert field in problems(save(client, n2, notices=[*n2["notices"], bad])), bad
    n2 = notices(client)
    dup = {"id": "fees", "text": "again"}
    assert "notices.fees.id" in problems(save(client, n2, notices=[*n2["notices"], dup]))
    # a stale revision is refused
    assert save(client, n, revision=1).status_code == 409


def test_a_saved_notice_is_exported_in_order_and_validates(client):
    n = notices(client)
    add = [{"id": "fees", "text": "수수료가 있을 수 있습니다.", "applies_when": "customer.age > 10"}]
    assert save(client, n, notices=[*n["notices"], *add]).status_code == 200
    assert client.post(f"{A}/bots/bank-ko/validate").json()["ok"]
    assert client.post(f"{A}/bots/bank-ko/publications", json={"note": "n"}).status_code == 201
    doc = yamlio.load(client.get(f"{A}/bots/bank-ko/publications/1/files/bank/ko/notices.yaml").text)
    assert doc["notices"]["time_deposit_early_close"]["priority"] == 10 and doc["notices"]["fees"]["priority"] == 20
    assert doc["notices"]["fees"]["fixed"] is True and doc["notices"]["fees"]["applies_when"] == "customer.age > 10"


def test_check_expression(client):
    ok = client.post(f"{A}/bots/bank-ko/notices/check-expression", json={"text": "customer.tier == 'gold' and len(pin) > 1"}).json()
    assert ok["ok"] and ok["names"] == ["customer", "pin"]
    bad = client.post(f"{A}/bots/bank-ko/notices/check-expression", json={"text": "amount >"}).json()
    assert not bad["ok"] and "syntax" in bad["error"]
    unknown = client.post(f"{A}/bots/bank-ko/notices/check-expression", json={"text": "zzz == 1"}).json()
    assert not unknown["ok"] and "zzz" in unknown["error"]
    assert "amount" in notices(client)["attributes"] and "customer" in notices(client)["reserved"]


def test_translation_tracking_per_item(client):
    from studio_backend.db import session_scope
    from studio_backend.models import Bot
    with session_scope() as sess:
        sess.delete(sess.query(Bot).filter_by(slug="bank-en").one())
        sess.commit()
    assert client.post(f"{A}/bots", json={"domain": "bank", "lang": "en", "start": "copy", "copy_from": "bank-ko"}).status_code == 201
    n = notices(client, "bank-en")
    assert n["to_translate"] == ["time_deposit_early_close"]
    n["wording"]["fallback.miss"] = "Sorry, could you say that once more?"      # wording is the starter's: nothing to clear
    assert save(client, n, "bank-en").json()["to_translate"] == ["time_deposit_early_close"]
    n = notices(client, "bank-en")
    n["notices"][0]["text"] = "Closing this deposit early may lower your rate."
    r = save(client, n, "bank-en")
    assert r.status_code == 200 and r.json()["to_translate"] == []
    assert client.get(f"{A}/bots/bank-en").json()["translate"]["notices"] == []


# --- rule words ---

def rules(c, slug="bank-ko"):
    return c.get(f"{A}/bots/{slug}/rules").json()["kinds"]


def test_rule_files_are_read_and_saved(client):
    k = rules(client)
    assert set(k) == {"confirm", "commands", "corrections", "confusions"} and k["confirm"]["exists"]
    body = {"yes_words": ["네", "예"], "no_words": ["아니요"]}
    r = client.put(f"{A}/bots/bank-ko/rules/confirm", json={"body": body, "revision": k["confirm"]["revision"]})
    assert r.status_code == 200 and r.json()["kinds"]["confirm"]["body"] == body
    assert client.post(f"{A}/bots/bank-ko/validate").json()["ok"]
    assert client.put(f"{A}/bots/bank-ko/rules/confirm", json={"body": body, "revision": k["confirm"]["revision"]}).status_code == 409
    assert client.put(f"{A}/bots/bank-ko/rules/nope", json={"body": {}}).status_code == 404


@pytest.mark.parametrize("kind,body,needle", [
    ("confirm", {"yes_words": ["네"], "no_words": ["네"]}, "both lists"),
    ("confirm", {"yes_words": [], "no_words": ["아니"]}, "empty"),
    ("commands", {"cancel": {"any_of": ["취소"]}, "back": {"any_of": ["뒤"]}}, "needs exactly"),
    ("commands", {"cancel": {"any_of": []}, "back": {"any_of": ["뒤"]}, "agent": {"any_of": ["상담"]}}, "needs all_of"),
    ("corrections", {"correction": {"any_of": ["아니"], "bogus": 1}}, "unknown keys"),
    ("confusions", {"pairs": [[13, 13]]}, "two different"),
    ("confusions", {"pairs": [[13, 30], [30, 40]]}, "two pairs"),
])
def test_rule_files_refuse_what_the_loader_refuses(client, kind, body, needle):
    r = client.put(f"{A}/bots/bank-ko/rules/{kind}", json={"body": body})
    assert r.status_code == 422 and needle in r.json()["detail"]["problems"][0]["message"], r.text
    assert "\\" not in r.json()["detail"]["problems"][0]["message"].split("rules")[0]


def test_sentence_test_uses_the_engine_matchers(client):
    def t(sentence, **extra):
        r = client.post(f"{A}/bots/bank-ko/rules/test", json={"text": sentence, **extra})
        assert r.status_code == 200, r.text
        return r.json()
    assert t("이거 취소해 주세요")["command"]["matched"] == "cancel"
    assert t("상담원 연결해 줘")["command"]["matched"] == "agent"
    assert t("영업시간 알려 줘")["command"]["matched"] is None
    assert t("네 진행해 주세요")["confirm"]["answer"] == "yes"
    assert t("아니요")["confirm"]["answer"] == "no" and t("아니요")["correction"]["matched"]
    assert t("글쎄요")["confirm"]["answer"] == "unclear"
    assert t("13")["confusions"] == [{"value": 13, "partner": 30}]
    unsaved = {"commands": {"cancel": {"any_of": ["영업"]}, "back": {"any_of": ["뒤"]}, "agent": {"any_of": ["상담"]}}}
    assert t("영업시간", bodies=unsaved)["command"]["matched"] == "cancel"
    assert client.post(f"{A}/bots/bank-ko/rules/test",
                       json={"text": "x", "bodies": {"confirm": {"yes_words": ["a"]}}}).status_code == 422


# --- slot lists ---

def lists(c, d="bank"):
    return c.get(f"{A}/domains/{d}/slot-lists").json()


def put_lists(c, sensitive, readback, cur=None, d="bank"):
    cur = cur or lists(c, d)
    return c.put(f"{A}/domains/{d}/slot-lists", json={"sensitive": sensitive, "readback": readback,
                                                      "sensitive_revision": cur["sensitive"]["revision"],
                                                      "readback_revision": cur["readback"]["revision"]})


def test_slot_lists_read(client):
    s = lists(client)
    assert s["sensitive"]["slots"] == ["birth_date", "phone_number", "pin"]
    assert s["readback"]["slots"] == [{"slot": "amount", "format": "money('USD')"}]
    assert "pin" in s["candidates"]["sensitive"] and "amount" not in s["candidates"]["sensitive"]
    assert "amount" in s["candidates"]["readback"]
    assert {f["call"] for f in s["formats"]} == {"count", "date", "money('KRW')", "money('USD')"}


def test_slot_lists_save_bump_the_shared_revision_and_validate(client):
    s = lists(client)
    before = client.get(f"{A}/bots/bank-ko").json()["shared_revision"]
    r = put_lists(client, [*s["sensitive"]["slots"], "account_last4"], [{"slot": "amount", "format": "money('KRW')"}], s)
    assert r.status_code == 200, r.text
    assert r.json()["readback"]["slots"] == [{"slot": "amount", "format": "money('KRW')"}]
    assert client.get(f"{A}/bots/bank-ko").json()["shared_revision"] == before + 1
    assert client.post(f"{A}/bots/bank-ko/validate").json()["ok"]
    assert put_lists(client, [], [], s).status_code == 409      # stale revision
    gone = put_lists(client, [], [])
    assert gone.status_code == 200 and gone.json()["sensitive"]["slots"] == [] and gone.json()["readback"]["slots"] == []


def test_slot_lists_refuse_what_the_engine_refuses(client):
    s = lists(client)
    asked_text = next(a for a, e in client.get(f"{A}/domains/bank/slot-lists").json()["asked_in"].items()
                      if a not in s["candidates"]["sensitive"])
    r = put_lists(client, [asked_text], [], s)
    assert r.status_code == 422 and "digits" in r.json()["detail"]["problems"][0]["message"] or "숫자" in r.text
    assert put_lists(client, ["never_asked"], [], s).status_code == 422
    assert put_lists(client, [], [{"slot": "amount", "format": "money('EUR')"}], s).status_code == 422
    assert put_lists(client, [], [{"slot": "amount", "format": "nope"}], s).status_code == 422
    assert put_lists(client, [], [{"slot": "amount", "format": "count"}, {"slot": "amount", "format": "date"}], s).status_code == 422


# --- policy warning ---

def test_policy_warning(client):
    rep = client.post(f"{A}/bots/bank-ko/validate").json()
    miss = [i for i in rep["items"] if i["code"] == "policy_value_missing"]
    assert miss and miss[0]["severity"] == "warning" and miss[0]["policy_key"] == "free_transfers_per_month" and rep["ok"]
    s = client.get(f"{A}/bots/bank-ko/settings").json()
    r = client.put(f"{A}/bots/bank-ko/settings", json={"studio_only": {"policy": {"free_transfers_per_month": "5"}},
                                                       "revision": s["revision"]})
    assert r.status_code == 200
    again = client.get(f"{A}/bots/bank-ko/validation").json()
    assert not [i for i in again["items"] if i["code"] == "policy_value_missing"]
    exported = client.post(f"{A}/bots/bank-ko/publications", json={"note": "p"})
    assert exported.status_code == 201
    paths = [f["path"] for f in client.get(f"{A}/bots/bank-ko/publications/1").json()["files"]]
    assert not any(p.endswith(("policy.yaml", "settings.yaml")) for p in paths)     # the values are the studio's own, never exported
