"""New and deleted bots. New ones are empty (language starter only) or a copy of a sibling of the same domain in another language.

Design: `studio/frontend/src/mock/DESIGN-NOTES.md`, "새 상담봇 만들기". Every new bot gets the language starter
(`starters/<lang>/`: situation wording and the confirm, command, correction and confusion words), because the engine's
loader needs those files once `rules/config.yaml` exists and they are about the language, not the business. A copy
takes the sibling's FAQ, flows, layout, config numbers and fixed notices, and remembers in `bot.origin` what is still
written in the sibling's language.
"""

from __future__ import annotations

import os
import pathlib
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import settings, yamlio
from .models import (Bot, Domain, DomainFile, DomainSetting, FaqEntry, Flow, FlowLayout, FlowNodeLayout, Publication,
                     Tool)
from .portable import BOT_SETTINGS

STARTERS = pathlib.Path(__file__).resolve().parent / "starters"
DOMAIN_ID = re.compile(r"^[a-z][a-z0-9-]{1,39}$")
STARTER_KINDS = ("confirm", "commands", "corrections", "confusions")
TRANSLATE_KINDS = ("faq", "flows", "notices")


class BotError(ValueError):
    """422: the request cannot make a bot."""


class BotExists(Exception):
    """409 with a reason: `exists` (domain and language taken) or `in_repo` (a not-imported folder of domains/)."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


def engine_langs() -> tuple[str, ...]:
    from voxstage.dataset import LANGS   # read only: the FAQ loader refuses any other language
    return tuple(LANGS)


def _starter(lang: str, rel: str):
    path = STARTERS / lang / rel
    if not path.exists():
        raise BotError(f"no language starter for {lang}: {rel}")
    return yamlio.load(path.read_text(encoding="utf-8"))


def _config(engine: dict | None, base: dict | None) -> dict:
    """The form's values over the source config (or the engine defaults), checked as 개요 checks them."""
    view = settings.engine_view(base)
    for section, values in (engine or {}).items():
        if not isinstance(values, dict) or section not in view:
            raise settings.SettingsError(f"unknown section {section}")
        view[section].update(values)
    return settings.merge_config(base, settings.check_engine(view))


def create_bot(session: Session, *, domain: str, lang: str, domain_title: str | None = None, title: str | None = None,
               start: str = "empty", copy_from: str | None = None, engine: dict | None = None,
               studio_only: dict | None = None, importable: list[str] = (), user_id: str | None = None) -> Bot:
    if lang not in engine_langs():
        raise BotError(f"lang must be one of {list(engine_langs())}")
    if start not in ("empty", "copy"):
        raise BotError("start is empty or copy")
    dom = session.scalar(select(Domain).where(Domain.slug == domain))
    if dom is None:
        if not DOMAIN_ID.match(domain):
            raise BotError("domain id: 2 to 40 lower-case letters, digits and -, starting with a letter")
        if domain in importable:
            raise BotExists("in_repo", f"domains/{domain} exists in the repository; import it instead")
        if not (domain_title or "").strip() or len(domain_title) > 200:
            raise BotError("domain_title: 1 to 200 characters for a new domain")
        if start == "copy":
            raise BotError("a new domain has no bot to copy from")
    elif session.scalar(select(Bot).where(Bot.domain_id == dom.id, Bot.lang == lang)) is not None:
        raise BotExists("exists", f"{domain} already has a {lang} bot")
    slug = f"{domain}-{lang}"
    if session.scalar(select(Bot).where(Bot.slug == slug)) is not None:
        raise BotExists("exists", f"bot {slug} exists")
    src = None
    if start == "copy":
        src = session.scalar(select(Bot).where(Bot.slug == copy_from)) if copy_from else None
        if src is None or src.domain_id != dom.id or src.lang == lang:
            raise BotError("copy_from must be a bot of the same domain in another language")
    if title is not None and (not title.strip() or len(title) > 200):
        raise BotError("title: 1 to 200 characters")

    src_cfg = _setting(session, src, "config") if src else None
    config = _config(engine, src_cfg.body if src_cfg else None)
    stored = dict(src.studio_settings or {}) if src else {}
    stored.update({k: v for k, v in (studio_only or {}).items()})
    studio = settings.check_studio_only(stored)

    if dom is None:
        dom = Domain(slug=domain, title=domain_title.strip())
        session.add(dom)
        session.flush()
    bot = Bot(domain_id=dom.id, lang=lang, slug=slug, title=(title or f"{dom.title} ({lang})").strip(),
              studio_settings=studio)
    session.add(bot)
    session.flush()

    session.add(DomainSetting(bot_id=bot.id, kind="config", body=config, updated_by=user_id))
    for kind in STARTER_KINDS:
        session.add(DomainSetting(bot_id=bot.id, kind=kind, body=_starter(lang, BOT_SETTINGS[kind]),
                                  updated_by=user_id))
    starter = _starter(lang, "notices.yaml")
    notices = _fixed_notices(session, src) if src else {}
    session.add(DomainFile(bot_id=bot.id, path="notices.yaml", updated_by=user_id,
                           content=yamlio.dump({"notices": notices, "wording": starter["wording"]})))
    if src:
        bot.origin = {"copied_from": src.slug, "to_translate": _copy_content(session, src, bot, user_id)}
        bot.origin["to_translate"]["notices"] = list(notices)
    session.flush()
    return bot


def _setting(session: Session, bot: Bot, kind: str) -> DomainSetting | None:
    return session.scalar(select(DomainSetting).where(DomainSetting.bot_id == bot.id, DomainSetting.kind == kind))


def _fixed_notices(session: Session, src: Bot) -> dict:
    row = session.scalar(select(DomainFile).where(DomainFile.bot_id == src.id, DomainFile.path == "notices.yaml"))
    doc = yamlio.load(row.content) if row else None
    return dict(doc.get("notices") or {}) if isinstance(doc, dict) else {}


def _copy_content(session: Session, src: Bot, bot: Bot, user_id: str | None) -> dict:
    """FAQ entries, flows and their layout, same ids; returns what is now to translate."""
    faq, flows = [], []
    for e in session.scalars(select(FaqEntry).where(FaqEntry.bot_id == src.id).order_by(FaqEntry.position)):
        session.add(FaqEntry(bot_id=bot.id, entry_id=e.entry_id, position=e.position, question=e.question,
                             answer=e.answer, paraphrases=e.paraphrases, asr_variants=e.asr_variants,
                             pattern=e.pattern, pattern_position=e.pattern_position, updated_by=user_id))
        faq.append(e.entry_id)
    for f in session.scalars(select(Flow).where(Flow.bot_id == src.id).order_by(Flow.flow_id)):
        session.add(Flow(bot_id=bot.id, flow_id=f.flow_id, header=dict(f.header or {}), start=f.start,
                         nodes=dict(f.nodes or {}), node_order=list(f.node_order or []), updated_by=user_id))
        flows.append(f.flow_id)
    for lay in session.scalars(select(FlowLayout).where(FlowLayout.bot_id == src.id)):
        session.add(FlowLayout(bot_id=bot.id, flow_id=lay.flow_id, viewport=lay.viewport, direction=lay.direction,
                               saved_by=user_id))
    for n in session.scalars(select(FlowNodeLayout).where(FlowNodeLayout.bot_id == src.id)):
        session.add(FlowNodeLayout(bot_id=bot.id, flow_id=n.flow_id, node_id=n.node_id, x=n.x, y=n.y,
                                   collapsed=n.collapsed))
    return {"faq": faq, "flows": flows}


# --- what a copy still holds in the sibling's language ---

def to_translate(bot: Bot) -> dict[str, list[str]]:
    left = (bot.origin or {}).get("to_translate") or {}
    return {k: list(left.get(k) or []) for k in TRANSLATE_KINDS}


def translate_count(bot: Bot) -> int:
    return sum(len(v) for v in to_translate(bot).values())


def mark_translated(bot: Bot, kind: str, item_id: str) -> None:
    """Saving or deleting an entry or a flow takes it off the list."""
    left = to_translate(bot)
    if item_id in left[kind]:
        left[kind].remove(item_id)
        bot.origin = {**(bot.origin or {}), "to_translate": left}   # a new dict, so the JSON column is written


def set_to_translate(bot: Bot, left: dict) -> None:
    current = to_translate(bot)
    clean = {}
    for k in TRANSLATE_KINDS:
        ids = left.get(k) or []
        if not isinstance(ids, list) or not set(ids) <= set(current[k]):
            raise BotError(f"{k}: only items still to translate can stay on the list")
        clean[k] = [i for i in current[k] if i in ids]
    bot.origin = {**(bot.origin or {}), "to_translate": clean}


def repo_folders(root: str) -> list[str]:
    return sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))) if os.path.isdir(root) else []


# --- delete ---

def delete_impact(session: Session, bot: Bot) -> dict:
    """What a delete removes, for the confirm dialog: the bot's content and history, and the domain when it is the
    domain's last bot (its API 연결 and 속성 종류 go with it)."""
    dom = session.get(Domain, bot.domain_id)
    last = len(dom.bots) == 1
    count = lambda model, col, v: session.query(model).filter(col == v).count()
    return {"faq": count(FaqEntry, FaqEntry.bot_id, bot.id), "flows": count(Flow, Flow.bot_id, bot.id),
            "publications": count(Publication, Publication.bot_id, bot.id), "last_of_domain": last,
            "domain_tools": count(Tool, Tool.domain_id, dom.id) if last else 0}


def delete_bot(session: Session, bot: Bot) -> dict:
    """Content, layout and publications go by the foreign keys' `on delete cascade`; the domain goes with its last bot."""
    dom = session.get(Domain, bot.domain_id)
    out = {"deleted": bot.slug, "domain_deleted": None}
    session.delete(bot)
    session.flush()
    session.refresh(dom)
    if not dom.bots:
        out["domain_deleted"] = dom.slug
        session.delete(dom)
    session.flush()
    return out
