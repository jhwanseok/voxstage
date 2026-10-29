"""Operations shared by the API: bot status, flow graph, validation cache, publication and export directory."""

from __future__ import annotations

import hashlib
import os
import pathlib
import shutil

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import bots, validation
from .models import Bot, Domain, Publication, PublicationFile
from .portable import export_bot

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


def domains_root() -> str:
    return os.environ.get("STUDIO_DOMAINS_ROOT", str(REPO_ROOT / "domains"))


def export_root() -> str:
    return os.environ.get("STUDIO_EXPORT_ROOT", str(REPO_ROOT / "studio" / "exports"))


# last validation per bot, in memory: tied to (draft_revision, shared_revision) (data-model.md)
_REPORTS: dict[str, dict] = {}


def cached_report(bot: Bot) -> dict | None:
    r = _REPORTS.get(bot.id)
    return r


def bot_status(bot: Bot, domain: Domain) -> dict:
    fresh = bot.last_validated_revision == bot.draft_revision and \
        bot.last_validated_shared_revision == domain.shared_revision
    unpublished = bot.published_draft_revision != bot.draft_revision or \
        bot.published_shared_revision != domain.shared_revision
    return {"slug": bot.slug, "domain": domain.slug, "domain_title": domain.title, "lang": bot.lang, "title": bot.title,
            "copied_from": (bot.origin or {}).get("copied_from"), "to_translate": bots.translate_count(bot),
            "draft_revision": bot.draft_revision, "shared_revision": domain.shared_revision,
            "last_published_number": bot.last_published_number,
            "has_unpublished_changes": unpublished,
            "validated": fresh, "valid": bool(fresh and bot.last_validation_ok)}


def validate_bot(session: Session, bot: Bot) -> dict:
    domain = session.get(Domain, bot.domain_id)
    files = export_bot(session, bot)
    items = validation.validate_files(files, domain.slug, bot.lang)
    rep = validation.report(items, bot.draft_revision, domain.shared_revision)
    bot.last_validated_revision = bot.draft_revision
    bot.last_validated_shared_revision = domain.shared_revision
    bot.last_validation_ok = rep["ok"]
    _REPORTS[bot.id] = rep
    return rep


def content_hash(files: dict[str, str]) -> str:
    h = hashlib.sha256()
    for path in sorted(files):
        h.update(path.encode("utf-8") + b"\0" + files[path].encode("utf-8") + b"\0")
    return h.hexdigest()


class NothingToPublish(Exception):
    pass


class ValidationFailed(Exception):
    def __init__(self, rep: dict):
        self.report = rep


def publish_bot(session: Session, bot: Bot, note: str, user_id: str | None) -> Publication:
    domain = session.get(Domain, bot.domain_id)
    rep = validate_bot(session, bot)
    if not rep["ok"]:
        raise ValidationFailed(rep)
    files = export_bot(session, bot)
    digest = content_hash(files)
    latest = session.scalar(select(Publication).where(Publication.bot_id == bot.id)
                            .order_by(Publication.number.desc()).limit(1))
    if latest is not None and latest.content_hash == digest:
        raise NothingToPublish()
    number = (session.scalar(select(func.max(Publication.number)).where(Publication.bot_id == bot.id)) or 0) + 1
    pub = Publication(bot_id=bot.id, number=number, shared_revision=domain.shared_revision, note=note,
                      content_hash=digest, validation={"warnings": [i for i in rep["items"] if i["severity"] != "error"]},
                      published_by=user_id)
    session.add(pub)
    session.flush()
    for path, text in files.items():
        session.add(PublicationFile(publication_id=pub.id, path=path, content=text))
    bot.last_published_number = number
    bot.published_draft_revision = bot.draft_revision
    bot.published_shared_revision = domain.shared_revision
    session.commit()
    write_export_dir(bot.slug, files)
    return pub


def write_export_dir(bot_slug: str, files: dict[str, str]) -> str:
    """studio/exports/<bot>/ is an engine domains_dir. Written beside the target and swapped, so a reader never sees
    half a pack."""
    root = export_root()
    os.makedirs(root, exist_ok=True)
    target = os.path.join(root, bot_slug)
    tmp = os.path.join(root, f".{bot_slug}.tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    validation.write_tree(tmp, files)
    shutil.rmtree(target, ignore_errors=True)
    os.replace(tmp, target)
    return target


# --- flow graph ---

def _edges(node_id: str, body: dict) -> list[tuple[str, str, str]]:
    """(handle, label, target) per exit, from the same table as the engine's `NodeType.edges`."""
    t = body.get("type")
    if t in ("say", "ask", "form", "notices", "goto"):
        return [("next", "", body.get("next"))] if body.get("next") else []
    if t == "confirm":
        return [h for h in (("yes", "yes", body.get("on_yes")), ("no", "no", body.get("on_no"))) if h[2]]
    if t == "call":
        return [h for h in (("ok", "ok", body.get("on_ok")), ("error", "error", body.get("on_error"))) if h[2]]
    if t == "branch":
        out = [(f"case-{i}", str(c.get("when", "")), c.get("next")) for i, c in enumerate(body.get("cases") or [])
               if isinstance(c, dict) and c.get("next")]
        if body.get("else"):
            out.append(("else", "else", body["else"]))
        return out
    return []


def flow_graph(flow) -> dict:
    nodes = [{"id": n, "type": (flow.nodes[n] or {}).get("type"), "data": flow.nodes[n]}
             for n in flow.node_order if n in flow.nodes]
    edges = []
    for n in [x["id"] for x in nodes]:
        for handle, label, target in _edges(n, flow.nodes[n] or {}):
            edges.append({"id": f"{n}:{handle}", "from": n, "to": target, "label": label, "handle": handle})
    return {"start": flow.start, "nodes": nodes, "edges": edges}


def remove_export_dir(bot_slug: str) -> None:
    """A deleted bot's `studio/exports/<bot>/` goes too, so the engine cannot load a bot the studio no longer has."""
    shutil.rmtree(os.path.join(export_root(), bot_slug), ignore_errors=True)
