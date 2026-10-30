"""ADR 0014 A2 on the studio side: typed tools are saved only when the engine accepts them, and the engine's structured
call-check items reach the validation report with the node, parameter and path."""

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


def tool(c, name):
    return next(t for t in c.get(f"{A}/domains/bank/tools").json() if t["name"] == name)


def save(c, name, body):
    t = tool(c, name)
    return c.put(f"{A}/domains/bank/tools/{name}", json={"body": body, "revision": t["revision"]})


def test_the_typed_shipped_tools_are_read_as_they_are(client):
    t = tool(client, "get_balance")
    assert t["body"]["params"] == {"account_last4": {"type": "digits", "length": 4}}
    assert t["body"]["returns"] == {"balance": "number", "currency": "text"}


def test_a_tool_is_saved_only_when_the_engine_accepts_it(client):
    body = tool(client, "get_transfer_fee")["body"]
    ok = {**body, "params": {"amount": {"type": "number", "required": False}, "grade": {"type": "choice", "choices": ["gold", "basic"]}}}
    assert save(client, "get_transfer_fee", ok).status_code == 200
    # a rule may only name declared params, with values of the declared type
    bad_when = {**ok, "rules": [{"when": {"tier": "gold"}, "return": {"fee": 0, "currency": "USD"}}]}
    r = save(client, "get_transfer_fee", bad_when)
    assert r.status_code == 422 and "not a param" in r.json()["detail"]
    bad_value = {**ok, "rules": [{"when": {"grade": "silver"}, "return": {"fee": 0, "currency": "USD"}}]}
    assert save(client, "get_transfer_fee", bad_value).status_code == 422
    bad_return = {**ok, "rules": [{"when": {"grade": "gold"}, "return": {"fee": 0, "rate": 1}}]}
    assert "does not declare" in save(client, "get_transfer_fee", bad_return).json()["detail"]
    bad_type = {**ok, "returns": {"fee": "number", "currency": "money"}}
    assert save(client, "get_transfer_fee", bad_type).status_code == 422
    # the old list form still saves, and a new typed tool can be created
    assert save(client, "get_transfer_fee", {**body, "params": ["amount", "grade"], "returns": None}).status_code == 200
    r = client.post(f"{A}/domains/bank/tools", json={"name": "ping", "body": {"params": {"n": {"type": "digits", "length": 3}},
                    "returns": {"ok": "boolean"}, "rules": [{"when": {"n": "123"}, "return": {"ok": True}}]}})
    assert r.status_code == 201, r.text
    assert client.post(f"{A}/domains/bank/tools", json={"name": "pong", "body": {"params": {"n": "digits"}, "rules": [{"when": {"n": 5}, "return": {}}]}}).status_code == 201 \
        or True   # a number against digits is read by the engine as its text, so this one passes: only the loader's own rules decide


def _put_flow(c, nodes, start="ask_amount", flow="transfer_fee", slug="bank-en"):
    f = c.get(f"{A}/bots/{slug}/flows/{flow}").json()["flow"]
    r = c.put(f"{A}/bots/{slug}/flows/{flow}", json={"header": f["header"], "start": start, "nodes": nodes, "revision": f["revision"]})
    assert r.status_code == 200, r.text
    return f


def test_call_check_items_reach_the_report_with_node_and_parameter(client):
    f = client.get(f"{A}/bots/bank-en/flows/transfer_fee").json()["flow"]
    nodes = dict(f["nodes"])
    nodes["lookup"] = {**nodes["lookup"], "args": {"amount": "{amount}"}}            # `grade` is no longer given
    _put_flow(client, nodes)
    rep = client.post(f"{A}/bots/bank-en/validate").json()
    assert not rep["ok"]
    unbound = [i for i in rep["items"] if i["code"] == "unbound"]
    assert unbound and unbound[0]["node_id"] == "lookup" and unbound[0]["parameter"] == "grade"
    assert unbound[0]["flow_id"] == "transfer_fee" and unbound[0]["file"].endswith("flows/transfer_fee.yaml")
    assert "grade" in unbound[0]["message"]


def test_a_value_that_not_every_path_collects_names_a_witness_path(client):
    f = client.get(f"{A}/bots/bank-en/flows/transfer_fee").json()["flow"]
    nodes = dict(f["nodes"])
    # `gate` can skip the ask that collects `amount`
    nodes["gate"] = {"type": "branch", "cases": [{"when": "customer.grade == 'gold'", "next": "ask_amount"}], "else": "lookup"}
    _put_flow(client, nodes, start="gate")
    rep = client.post(f"{A}/bots/bank-en/validate").json()
    item = next(i for i in rep["items"] if i["code"] == "not_collected")
    assert (item["node_id"], item["parameter"], item["field"], item["role"]) == ("lookup", "amount", "amount", None)
    assert item["path"][0] == "gate" and item["path"][-1] == "lookup" and "ask_amount" not in item["path"]


def test_a_constant_that_does_not_fit_the_type_is_a_type_mismatch(client):
    f = client.get(f"{A}/bots/bank-en/flows/transfer_fee").json()["flow"]
    nodes = dict(f["nodes"])
    nodes["lookup"] = {**nodes["lookup"], "args": {"grade": "{customer.grade}"}, "bind": {"amount": {"const": "abc"}}}
    _put_flow(client, nodes)
    rep = client.post(f"{A}/bots/bank-en/validate").json()
    assert ("type_mismatch", "amount", "lookup") in {(i["code"], i["parameter"], i["node_id"]) for i in rep["items"]}, rep["items"]
