"""Validation through the engine's own loader (ADR 0012): export to a temporary directory, then load it as the engine does.

The studio only reads the engine here (`DomainPack.load`, `load_flows`, `FakeApiExecutor`). The loader raises text
errors that name a file and often a node; they are mapped to report items and the full message is kept.
"""

from __future__ import annotations

import os
import re
import tempfile

from voxstage.domain_pack import DomainPack
from voxstage.rules.flows import load_flows
from voxstage.tools import FakeApiExecutor


def write_tree(root: str, files: dict[str, str]) -> None:
    for rel, text in files.items():
        path = os.path.join(root, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)


_NODE = re.compile(r"node ([\w.\-\[\]]+?)(?::|\s|$)")
_NODE_PATH = re.compile(r"[\\/]([\w\-]+)\.yaml")


def _item(exc: Exception, root: str, domain: str, lang: str, default_file: str) -> dict:
    message = str(exc)
    shown = message.replace(root + os.sep, "").replace(root, "").replace("\\", "/")
    file = default_file
    m = re.search(r"((?:[\w\-]+/)+[\w\-]+\.yaml)", shown)
    if m:
        file = m.group(1)
    flow_id = node_id = None
    fm = re.search(r"/flows/([\w\-]+)\.yaml", file)
    if fm:
        flow_id = fm.group(1)
    nm = _NODE.search(shown)
    if nm and flow_id:
        node_id = nm.group(1).split(".")[0]
    return {"severity": "error", "source": "engine", "code": type(exc).__name__, "file": file, "lang": lang,
            "flow_id": flow_id, "node_id": node_id, "field": None, "message": shown}


def validate_files(files: dict[str, str], domain: str, lang: str) -> list[dict]:
    """Report items for one bot's exported files; an empty list means the engine loads them."""
    items: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="studio-validate-") as root:
        write_tree(root, files)
        tools_path = os.path.join(root, domain, "tools.yaml")
        if os.path.exists(tools_path):
            try:
                FakeApiExecutor.from_yaml(tools_path)
            except Exception as exc:   # ValueError from the tool spec check, or YAML errors
                items.append(_item(exc, root, domain, lang, f"{domain}/tools.yaml"))
                return items
        try:
            pack = DomainPack.load(root, domain, lang)
        except Exception as exc:
            items.append(_item(exc, root, domain, lang, f"{domain}/{lang}"))
            return items
        flows_dir = os.path.join(pack.base_dir, "flows")
        if os.path.isdir(flows_dir):
            try:
                load_flows(flows_dir, pack.tools_path, pack.sensitive_slots, pack.notices)
            except Exception as exc:
                items.append(_item(exc, root, domain, lang, f"{domain}/{lang}/flows"))
    return items


def report(items: list[dict], draft_revision: int, shared_revision: int) -> dict:
    return {"draft_revision": draft_revision, "shared_revision": shared_revision,
            "ok": not any(i["severity"] == "error" for i in items), "items": items}
