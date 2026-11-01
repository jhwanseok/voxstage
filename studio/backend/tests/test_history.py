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


# --- rollback and retention (D1, D5) ---

def export_dir(tmp_path):
    root = tmp_path / "exports" / BOT
    return {str(p.relative_to(root)).replace(chr(92), "/"): p.read_bytes().decode("utf-8").replace(chr(13) + chr(10), chr(10))
            for p in sorted(root.rglob("*")) if p.is_file()}


def pub_files(c, n):
    out = {}
    for f in c.get(f"{A}/bots/{BOT}/publications/{n}").json()["files"]:
        out[f["path"]] = c.get(f"{A}/bots/{BOT}/publications/{n}/files/{f['path']}").text
    return out


def test_rollback_makes_a_new_publication_and_a_draft_equal_to_the_old_one(client, tmp_path):
    two_versions(client)
    first = pub_files(client, 1)
    r = client.post(f"{A}/bots/{BOT}/publications/1/rollback", json={"note": "undo"})
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["number"] == 3 and out["kind"] == "rollback" and out["restored_from_number"] == 1 and out["note"] == "undo"
    assert pub_files(client, 3) == first                     # same files as publication 1 (shared files unchanged since)
    assert export_dir(tmp_path) == {k: v.replace(chr(13) + chr(10), chr(10)) for k, v in first.items()}
    b = client.get(f"{A}/bots/{BOT}").json()
    assert b["last_published_number"] == 3 and not b["has_unpublished_changes"] and b["valid"]
    assert client.get(f"{A}/bots/{BOT}/changes").json()["summary"]["empty"]
    flow = client.get(f"{A}/bots/{BOT}/flows/transfer").json()["flow"]
    assert "say_sorry" not in flow["nodes"]
    assert [p["number"] for p in client.get(f"{A}/bots/{BOT}/publications").json()] == [3, 2, 1]
    # rolling back to what is already the newest content is refused
    assert client.post(f"{A}/bots/{BOT}/publications/3/rollback", json={}).status_code == 409


def test_rollback_needs_the_owner_to_say_what_happens_to_unpublished_changes(client):
    two_versions(client)
    edit_faq(client, answer="초안에만 있는 문장")
    r = client.post(f"{A}/bots/{BOT}/publications/1/rollback", json={})
    assert r.status_code == 409 and r.json()["code"] == "unpublished_changes"
    assert "초안에만 있는 문장" in client.get(f"{A}/bots/{BOT}/faq").json()[0]["answer"]      # nothing changed
    ok = client.post(f"{A}/bots/{BOT}/publications/1/rollback", json={"discard_draft": True})
    assert ok.status_code == 201
    assert "초안에만 있는 문장" not in client.get(f"{A}/bots/{BOT}/faq").json()[0]["answer"]


def test_rollback_leaves_shared_files_and_other_languages_alone(client):
    publish(client)
    other_before = client.get(f"{A}/bots/bank-en/faq").json()
    tool = client.get(f"{A}/domains/bank/tools").json()[0]
    assert client.put(f"{A}/domains/bank/tools/{tool['name']}",
                      json={"body": {**tool["body"], "retry": 0}, "revision": tool["revision"]}).status_code == 200
    edit_faq(client, answer="두 번째")
    publish(client)
    r = client.post(f"{A}/bots/{BOT}/publications/1/rollback", json={})
    assert r.status_code == 201, r.text
    assert next(t for t in client.get(f"{A}/domains/bank/tools").json() if t["name"] == tool["name"])["body"]["retry"] == 0
    assert "retry: 0" in client.get(f"{A}/bots/{BOT}/publications/3/files/bank/tools.yaml").text    # D1: shared as of now
    assert "retry: 1" in client.get(f"{A}/bots/{BOT}/publications/1/files/bank/tools.yaml").text
    assert client.get(f"{A}/bots/bank-en/faq").json() == other_before


def test_rollback_that_no_longer_validates_changes_nothing(client, tmp_path):
    publish(client)
    # the shared types lose a type that publication 1's flows rely on: the old files no longer load
    d = client.get(f"{A}/bots/{BOT}/flows/transfer").json()["flow"]
    nodes = {k: dict(v) for k, v in d["nodes"].items()}
    nodes["say_x"] = {"type": "say", "text": "x", "next": "done"}
    nodes["say_fail"] = {**nodes["say_fail"], "next": "say_x"}
    client.put(f"{A}/bots/{BOT}/flows/transfer", json={"start": d["start"], "nodes": nodes, "revision": d["revision"]})
    publish(client)
    tool = next(t for t in client.get(f"{A}/domains/bank/tools").json() if t["name"] == "get_transfer_fee")
    assert client.delete(f"{A}/domains/bank/tools/{tool['name']}?force=true").status_code == 204
    before = (pub_files(client, 2), client.get(f"{A}/bots/{BOT}").json()["draft_revision"])
    r = client.post(f"{A}/bots/{BOT}/publications/1/rollback", json={"discard_draft": True})
    assert r.status_code == 422 and r.json()["report"]["ok"] is False
    assert (pub_files(client, 2), client.get(f"{A}/bots/{BOT}").json()["draft_revision"]) == before
    assert [p["number"] for p in client.get(f"{A}/bots/{BOT}/publications").json()] == [2, 1]


def test_only_the_newest_five_publications_are_kept_and_numbers_never_repeat(client):
    for i in range(7):
        edit_faq(client, answer=f"답변 {i}")
        assert publish(client) == i + 1
    nums = [p["number"] for p in client.get(f"{A}/bots/{BOT}/publications").json()]
    assert nums == [7, 6, 5, 4, 3]
    assert client.get(f"{A}/bots/{BOT}/publications/2").status_code == 404
    # a rollback also counts, and it may point at a publication that is gone afterwards
    assert client.post(f"{A}/bots/{BOT}/publications/3/rollback", json={}).status_code == 201
    pubs = client.get(f"{A}/bots/{BOT}/publications").json()
    assert [p["number"] for p in pubs] == [8, 7, 6, 5, 4] and pubs[0]["restored_from_number"] == 3
    # the oldest one kept has nothing before it to compare with
    assert client.get(f"{A}/bots/{BOT}/publications/4/diff").json()["base"]["kind"] == "none"


# --- sibling check (D3) ---

def test_the_imported_pair_has_no_structural_differences(client):
    r = client.get(f"{A}/bots/{BOT}/siblings/check").json()
    assert r["siblings"] == [{"bot": "bank-en", "lang": "en", "compared": r["siblings"][0]["compared"], "warnings": []}]
    assert r["siblings"][0]["compared"] >= 5 and r["warning_count"] == 0


def test_sibling_check_names_the_first_difference_and_ignores_wording(client):
    # wording and constants differ by language: not a warning
    edit_flow(client, lambda n: n["say_fail"].update(text="완전히 다른 문장입니다."))
    assert client.get(f"{A}/bots/{BOT}/siblings/check").json()["warning_count"] == 0
    # a new step and a rewired step are
    def change(nodes):
        nodes["say_sorry"] = {"type": "say", "text": "죄송합니다.", "next": "done"}
        nodes["say_fail"] = {**nodes["say_fail"], "next": "say_sorry"}
    edit_flow(client, change)
    w = client.get(f"{A}/bots/{BOT}/siblings/check").json()["siblings"][0]["warnings"]
    assert w == [{"flow": "transfer", "kind": "structure_differs",
                  "difference": {"kind": "exit", "step": "say_fail", "exit": "next", "here": "say_sorry", "there": "done"}}]
    # the other side: from the English bot the new step is the one it does not have
    en = client.get(f"{A}/bots/bank-en/siblings/check").json()["siblings"][0]["warnings"]
    assert en[0]["difference"] == {"kind": "exit", "step": "say_fail", "exit": "next", "here": "done", "there": "say_sorry"}


def test_sibling_check_lists_scenarios_that_exist_in_one_language_only(client):
    assert client.post(f"{A}/bots/{BOT}/flows", json={"id": "only_korean"}).status_code == 201
    assert client.delete(f"{A}/bots/bank-en/flows/transfer").status_code == 204
    w = {x["flow"]: x["kind"] for x in client.get(f"{A}/bots/{BOT}/siblings/check").json()["siblings"][0]["warnings"]}
    assert w == {"only_korean": "only_here", "transfer": "only_here"}
    w = {x["flow"]: x["kind"] for x in client.get(f"{A}/bots/bank-en/siblings/check").json()["siblings"][0]["warnings"]}
    assert w == {"only_korean": "only_there", "transfer": "only_there"}
    # a warning never blocks a publication
    assert client.post(f"{A}/bots/{BOT}/publications", json={}).status_code in (201, 422)


# --- roles (D4) ---

def make_user(session, email, *roles, active=True):
    from studio_backend.models import User, UserRole
    u = User(email=email, display_name=email.split("@")[0], is_active=active)
    session.add(u)
    session.flush()
    for r in roles:
        session.add(UserRole(user_id=u.id, role_name=r))
    session.commit()
    return u


def as_user(email):
    return {"X-Studio-User": email}


def test_the_local_user_does_everything_and_the_history_names_the_author(client):
    me = client.get(f"{A}/me").json()
    assert me["roles"] == ["admin", "editor", "publisher"]
    publish(client)
    assert client.get(f"{A}/bots/{BOT}/publications").json()[0]["published_by_name"] == "Local user"
    assert client.get(f"{A}/bots/{BOT}/publications/1").json()["published_by_name"] == "Local user"


def test_an_editor_edits_but_cannot_publish_roll_back_or_delete(client, session):
    make_user(session, "ed@x", "editor")
    h = as_user("ed@x")
    publish(client)
    e = client.get(f"{A}/bots/{BOT}/faq").json()[0]
    ok = client.put(f"{A}/bots/{BOT}/faq/{e['id']}", json={**e, "revision": None, "answer": "편집자가 고침"}, headers=h)
    assert ok.status_code == 200
    r = client.post(f"{A}/bots/{BOT}/publications", json={}, headers=h)
    assert r.status_code == 403 and r.json()["detail"]["missing_role"] == "publisher"
    assert client.post(f"{A}/bots/{BOT}/publications/1/rollback", json={"discard_draft": True}, headers=h).status_code == 403
    assert client.delete(f"{A}/bots/{BOT}", headers=h).status_code == 403
    assert client.post(f"{A}/domains/import", json={"domain": "shop"}, headers=h).status_code == 403
    assert client.get(f"{A}/bots/{BOT}/publications", headers=h).status_code == 200       # reading needs no role
    assert client.get(f"{A}/bots/{BOT}/faq").json()[0]["answer"] == "편집자가 고침"        # and the draft did change


def test_a_publisher_publishes_and_rolls_back_but_cannot_delete(client, session):
    make_user(session, "pub@x", "publisher")
    h = as_user("pub@x")
    publish(client)
    edit_faq(client, answer="두 번째")
    r = client.post(f"{A}/bots/{BOT}/publications", json={"note": "by publisher"}, headers=h)
    assert r.status_code == 201 and r.json()["published_by_name"] == "pub"
    back = client.post(f"{A}/bots/{BOT}/publications/1/rollback", json={}, headers=h)
    assert back.status_code == 201
    assert client.delete(f"{A}/bots/{BOT}", headers=h).status_code == 403
    assert client.get(f"{A}/bots/{BOT}/publications").json()[0]["published_by_name"] == "pub"


def test_a_user_without_roles_cannot_change_anything_and_unknown_users_are_refused(client, session):
    make_user(session, "reader@x")
    make_user(session, "gone@x", "admin", active=False)
    e = client.get(f"{A}/bots/{BOT}/faq").json()[0]
    assert client.put(f"{A}/bots/{BOT}/faq/{e['id']}", json={**e, "revision": None}, headers=as_user("reader@x")).status_code == 403
    assert client.get(f"{A}/bots/{BOT}/faq", headers=as_user("reader@x")).status_code == 200
    assert client.get(f"{A}/me", headers=as_user("nobody@x")).status_code == 401
    assert client.get(f"{A}/me", headers=as_user("gone@x")).status_code == 403
    # the test chat changes no content, so it needs no role
    assert client.post(f"{A}/bots/{BOT}/chat", json={}, headers=as_user("reader@x")).status_code != 403
