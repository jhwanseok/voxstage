"""안내 문구 and 응답 규칙 (ST3): the wording and fixed notices of `notices.yaml`, and the four rule-word files.

The checks are the engine's own: a body is written to a temporary file and read by the engine's loader
(`load_registry`, `load_confirm_words`, ...), so nothing the engine refuses can be saved. Before that, field by field
checks name the key or the notice so the form can show the message under the right box. The sentence test uses the
engine's tokenizer and `Matcher`, the same code `_respond` runs for commands, corrections and confirm answers.
"""

from __future__ import annotations

import ast
import os
import re
import tempfile
from typing import Any

from voxstage import domain_pack
from voxstage.domain_pack import PLACEHOLDER_KEYS, WORDING_KEYS, RuleError
from voxstage.rules import expr
from voxstage.rules.matching import Matcher
from voxstage.rules.tokenize import for_lang

NOTICE_ID = re.compile(r"^[A-Za-z][\w\-]{0,59}$")
MAX_TEXT = 1000
MAX_WHEN = 500
STEP = 10
RESERVED = sorted(expr.RESERVED_NAMES)

# when each situation is said, in plain Korean (the form shows it next to the text)
WORDING_MEANING = {
    "fallback.miss": "말을 알아듣지 못했을 때",
    "fallback.exceed": "알아듣지 못한 횟수가 한도를 넘어 상담사로 넘길 때",
    "ask.invalid": "물어본 속성의 답이 올바르지 않을 때",
    "ask.keypad_only": "민감한 속성을 말로 답했을 때(키패드로 안내)",
    "ask.exceed": "속성 답을 여러 번 확인하지 못해 상담사로 넘길 때",
    "flow.attribute_missing": "시나리오에 필요한 속성을 구하지 못했을 때",
    "flow.no_flow": "맞는 시나리오가 없을 때",
    "confirm.declined": "확인 질문에 아니오라고 답했을 때",
    "command.cancelled": "고객이 취소했을 때",
    "command.agent": "고객이 상담사 연결을 요청했을 때",
    "date.ambiguous": "날짜가 모호할 때",
    "readback": "받은 값을 다시 읽어 줄 때",
    "correction.offer": "고객이 방금 값을 고쳤다고 보고 \"이 값이 맞나요?\"라고 물을 때",
    "verify.locked": "본인 확인에 실패해 잠겼을 때",
    "call.failed": "API 연결 호출이 실패했을 때",
    "call.unconfirmed": "API 연결 호출이 처리됐는지 알 수 없을 때",
    "call.exceed": "API 연결 호출이 계속 실패해 상담사로 넘길 때",
}

RULE_KINDS = ("confirm", "commands", "corrections", "confusions")


class WordingError(ValueError):
    """422: the body carries problems, each `{field, message}`."""

    def __init__(self, problems: list[dict]):
        super().__init__("; ".join(p["message"] for p in problems))
        self.problems = problems


def _clean_path(message: str, tmp: str, shown: str) -> str:
    return message.replace(tmp, shown).replace("\\", "/")


# --- notices.yaml ---

def stored_to_form(body: dict | None) -> dict:
    """The stored body as the form's lists: fixed notices in priority order, wording by the engine's key order."""
    body = body if isinstance(body, dict) else {}
    raw = body.get("notices") if isinstance(body.get("notices"), dict) else {}
    items = []
    for nid, n in raw.items():
        n = n if isinstance(n, dict) else {}
        prio = n.get("priority") if isinstance(n.get("priority"), int) else 10 ** 6
        items.append((prio, {"id": nid, "text": str(n.get("text") or ""), "applies_when": n.get("applies_when") or None}))
    wording = body.get("wording") if isinstance(body.get("wording"), dict) else {}
    return {"notices": [i for _, i in sorted(items, key=lambda t: t[0])],
            "wording": {k: str(wording.get(k) or "") for k in WORDING_KEYS}}


def form_to_stored(form: dict) -> dict:
    """Priorities follow the list order, 10, 20, 30."""
    notices: dict[str, Any] = {}
    for i, n in enumerate(form["notices"], start=1):
        item: dict[str, Any] = {"text": n["text"], "priority": i * STEP, "fixed": True}
        if n.get("applies_when"):
            item["applies_when"] = n["applies_when"].strip()
        notices[n["id"]] = item
    return {"notices": notices, "wording": {k: form["wording"][k] for k in WORDING_KEYS}}


def attribute_names(flows, session_roles: dict | None = None) -> list[str]:
    """Names an `applies_when` may read besides the engine's reserved ones: the attributes the bot's scenarios collect
    (ask and form steps, captures) and their roles, as `load_flow` builds them."""
    names: set[str] = set()
    for f in flows:
        header, nodes = f.header or {}, f.nodes or {}
        names |= set(header.get("captures") or {})
        names |= set(header.get("roles") or {})
        for n in nodes.values():
            if not isinstance(n, dict):
                continue
            if n.get("type") == "ask" and isinstance(n.get("slot"), str):
                names.add(n["slot"])
            if n.get("type") == "form":
                names |= {s["slot"] for s in n.get("slots") or [] if isinstance(s, dict) and isinstance(s.get("slot"), str)}
    names |= set(session_roles or {})
    return sorted(names)


def check_expression(source: str, names: list[str]) -> dict:
    """Compile an `applies_when` text with the engine. `{ok, error, names}`: the attributes the text reads."""
    if not isinstance(source, str) or not source.strip():
        return {"ok": False, "error": "조건을 입력하세요. 비워 두면 항상 말합니다.", "names": []}
    if len(source) > MAX_WHEN:
        return {"ok": False, "error": f"조건은 {MAX_WHEN}자까지 쓸 수 있습니다.", "names": []}
    try:
        compiled = expr.compile_expr(source, "applies_when", frozenset(names))
    except expr.ExprError as exc:
        return {"ok": False, "error": str(exc).removeprefix("applies_when: "), "names": []}
    used = sorted({n.id for n in ast.walk(compiled.tree) if isinstance(n, ast.Name) and n.id not in expr.FUNCTIONS})
    return {"ok": True, "error": None, "names": used}


def check_notices(form: dict, names: list[str]) -> dict:
    """Field problems first, then the engine's own loader as the last gate. Returns the stored body."""
    problems: list[dict] = []

    def bad(field: str, message: str):
        problems.append({"field": field, "message": message})

    wording = form.get("wording")
    if not isinstance(wording, dict):
        raise WordingError([{"field": "wording", "message": "상황별 문구가 없습니다."}])
    missing, extra = sorted(set(WORDING_KEYS) - set(wording)), sorted(set(wording) - set(WORDING_KEYS))
    if missing or extra:
        bad("wording", f"상황별 문구의 키는 정해져 있습니다(없음 {missing}, 모르는 키 {extra}).")
    for key in WORDING_KEYS:
        text = wording.get(key)
        if not isinstance(text, str) or not text.strip():
            bad(f"wording.{key}", "문구를 입력하세요.")
        elif len(text) > MAX_TEXT:
            bad(f"wording.{key}", f"문구는 {MAX_TEXT}자까지 쓸 수 있습니다.")
        elif key in PLACEHOLDER_KEYS and "{value}" not in text:
            bad(f"wording.{key}", "{value}가 들어가야 합니다. 값이 들어갈 자리입니다.")
        elif key not in PLACEHOLDER_KEYS and "{value}" in text:
            bad(f"wording.{key}", "이 문구에는 {value}를 쓸 수 없습니다. 값이 들어가는 문구는 다시 읽기와 값 확인뿐입니다.")
    seen: set[str] = set()
    notices = form.get("notices")
    if not isinstance(notices, list):
        raise WordingError(problems + [{"field": "notices", "message": "고정 안내 목록이 없습니다."}])
    for i, n in enumerate(notices):
        nid = n.get("id") if isinstance(n, dict) else None
        where = f"notices.{nid if isinstance(nid, str) and nid else i}"
        if not isinstance(nid, str) or not NOTICE_ID.match(nid):
            bad(f"{where}.id", "이름은 영문자로 시작하고 영문자, 숫자, _, -만 쓸 수 있습니다(60자까지).")
            continue
        if nid in seen:
            bad(f"{where}.id", "같은 이름의 고정 안내가 이미 있습니다.")
        seen.add(nid)
        text = n.get("text")
        if not isinstance(text, str) or not text.strip():
            bad(f"{where}.text", "문구를 입력하세요.")
        elif len(text) > MAX_TEXT:
            bad(f"{where}.text", f"문구는 {MAX_TEXT}자까지 쓸 수 있습니다.")
        elif "{" in text or "}" in text:
            bad(f"{where}.text", "고정 안내는 그대로 읽습니다. { } 기호는 쓸 수 없습니다.")
        when = n.get("applies_when")
        if when is not None and (not isinstance(when, str) or when.strip()):
            res = check_expression(when, names)
            if not res["ok"]:
                bad(f"{where}.applies_when", res["error"])
    if problems:
        raise WordingError(problems)
    stored = form_to_stored(form)
    with tempfile.TemporaryDirectory(prefix="studio-notices-") as root:
        path = os.path.join(root, "notices.yaml")
        _write(path, stored)
        try:
            domain_pack.load_registry(path)
        except RuleError as exc:
            raise WordingError([{"field": "", "message": _clean_path(str(exc), path, "notices.yaml")}])
    return stored


def _write(path: str, body) -> None:
    from . import yamlio
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(yamlio.dump(body))


# --- rule words ---

_LOADERS = {"confirm": domain_pack.load_confirm_words, "commands": domain_pack.load_commands,
            "corrections": domain_pack.load_correction, "confusions": domain_pack.load_confusions}


def check_rule(kind: str, body: Any) -> Any:
    """The engine's loader reads the body from a temporary file; its message is the 422 reason."""
    if kind not in _LOADERS:
        raise KeyError(kind)
    if not isinstance(body, dict):
        raise WordingError([{"field": "", "message": "내용은 항목이 있는 형태여야 합니다."}])
    with tempfile.TemporaryDirectory(prefix="studio-rules-") as root:
        path = os.path.join(root, f"{kind}.yaml")
        _write(path, body)
        try:
            return _LOADERS[kind](path)
        except RuleError as exc:
            raise WordingError([{"field": "", "message": _clean_path(str(exc), path, f"rules/{kind}.yaml")}])


def test_sentence(lang: str, text: str, bodies: dict[str, Any]) -> dict:
    """Which command, confirm answer, correction and confusion the engine finds in a sentence. `bodies` are the four
    files as the form holds them (saved or not)."""
    tok = for_lang(lang)
    loaded = {k: check_rule(k, bodies[k]) for k in RULE_KINDS}
    out: dict[str, Any] = {"lang": lang}

    commands = loaded["commands"]
    matched, trace = Matcher(commands, tok).match(text)
    out["tokens"] = list(trace["tokens"])
    out["command"] = {"matched": matched.id if matched else None, "ties": trace.get("ties", [])}

    answer = tok.analyze_answer(text)
    yes_words, no_words = loaded["confirm"]
    yes = [w for w in yes_words if tok.has(answer, w)]
    no = [w for w in no_words if tok.has(answer, w)]
    out["confirm"] = {"answer": "yes" if yes and not no else "no" if no and not yes else "unclear",
                      "yes_words": yes, "no_words": no, "tokens": list(answer.tokens)}

    correction = loaded["corrections"]
    score = Matcher((correction,), tok).score(correction, text, answer)
    out["correction"] = {"matched": score is not None, "score": score}

    confusions = loaded["confusions"]
    out["confusions"] = [{"value": int(n), "partner": int(confusions[n])} for n in re.findall(r"\d+", text)
                         if n in confusions]
    return out
