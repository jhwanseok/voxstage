"""FastAPI app: the ST1 subset of docs/studio/api.md. No authentication in v1: every request is the seeded local user."""

from __future__ import annotations

import os
import re
import zipfile
from contextlib import asynccontextmanager
from io import BytesIO
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from . import bots, chat, datatypes, diffs, portable, service, settings, siblings, slotlists, wording, yamlio
from .db import get_session, session_scope
from .models import (Bot, Domain, DomainSetting, FaqEntry, Flow, FlowLayout, FlowNodeLayout, Publication,
                     PublicationFile, Role, Tool, User, UserRole)

LOCAL_USER_EMAIL = "local@studio"
ROLES = ("editor", "publisher", "admin")


def seed(session: Session) -> User:
    for r in ROLES:
        if session.get(Role, r) is None:
            session.add(Role(name=r))
    user = session.scalar(select(User).where(User.email == LOCAL_USER_EMAIL))
    if user is None:
        user = User(email=LOCAL_USER_EMAIL, display_name="Local user")
        session.add(user)
        session.flush()
        for r in ROLES:
            session.add(UserRole(user_id=user.id, role_name=r))
    session.commit()
    return user


@asynccontextmanager
async def lifespan(app: FastAPI):
    with session_scope() as s:
        seed(s)
    yield


ROLE_RANK = {"editor": 1, "publisher": 2, "admin": 3}     # each role also may do what the lower ones may (ST2 D4)
READ_METHODS = {"GET", "HEAD", "OPTIONS"}
API = "/api/v1"


def current_user(session: Session = Depends(get_session), x_studio_user: str | None = Header(default=None)) -> User:
    """The local user, or the user named by the `X-Studio-User` header (an email). There is no login: the header is a
    guard against slips, not a security boundary (ST2 D4)."""
    if x_studio_user is None:
        return session.scalar(select(User).where(User.email == LOCAL_USER_EMAIL))
    user = session.scalar(select(User).where(User.email == x_studio_user))
    if user is None:
        raise HTTPException(401, {"message": f"unknown user {x_studio_user}"})
    if not user.is_active:
        raise HTTPException(403, {"message": f"user {x_studio_user} is not active"})
    return user


def require_role(role: str):
    def dep(user: User = Depends(current_user), session: Session = Depends(get_session)) -> User:
        have = max((ROLE_RANK.get(r, 0) for r in session.scalars(select(UserRole.role_name).where(UserRole.user_id == user.id))), default=0)
        if have < ROLE_RANK[role]:
            raise HTTPException(403, {"message": f"this needs the {role} role", "missing_role": role})
        return user
    return dep


def write_guard(request: Request, user: User = Depends(current_user), session: Session = Depends(get_session)) -> None:
    """Every change needs at least `editor`; the stronger roles are asked for by the endpoints themselves. Talking to
    a bot in the test chat changes no content."""
    if request.method not in READ_METHODS and "/chat" not in request.url.path:
        require_role("editor")(user, session)


app = FastAPI(title="voxstage studio", version="0.0.1", lifespan=lifespan, dependencies=[Depends(write_guard)])
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5710", "http://127.0.0.1:5710"],
                   allow_methods=["*"], allow_headers=["*"])


# --- helpers ---

def get_bot(session: Session, slug: str) -> Bot:
    bot = session.scalar(select(Bot).where(Bot.slug == slug))
    if bot is None:
        raise HTTPException(404, f"no bot {slug}")
    return bot


def get_domain(session: Session, slug: str) -> Domain:
    d = session.scalar(select(Domain).where(Domain.slug == slug))
    if d is None:
        raise HTTPException(404, f"no domain {slug}")
    return d


def conflict(row, current: dict):
    raise HTTPException(409, {"message": "revision conflict", "current": current})


def check_revision(row, revision: int | None, current: dict) -> None:
    if revision is not None and row.revision != revision:
        conflict(row, current)


def touch_bot(bot: Bot) -> None:
    bot.draft_revision += 1


def touch_domain(session: Session, domain: Domain) -> None:
    domain.shared_revision += 1


# --- session and users ---

@app.get(f"{API}/me")
def me(user: User = Depends(current_user), session: Session = Depends(get_session)):
    roles = session.scalars(select(UserRole.role_name).where(UserRole.user_id == user.id)).all()
    return {"id": user.id, "email": user.email, "display_name": user.display_name, "roles": sorted(roles)}


@app.get(f"{API}/roles")
def roles(session: Session = Depends(get_session)):
    return sorted(session.scalars(select(Role.name)).all())


# --- domains, bots, import ---

def bot_row(session: Session, bot: Bot) -> dict:
    return service.bot_status(bot, session.get(Domain, bot.domain_id))


@app.get(f"{API}/bots")
def list_bots(session: Session = Depends(get_session)):
    return [bot_row(session, b) for b in session.scalars(select(Bot).order_by(Bot.slug))]


@app.get(f"{API}/bots/{{b}}")
def one_bot(b: str, session: Session = Depends(get_session)):
    bot = get_bot(session, b)
    counts = {
        "faq": session.scalar(select(func.count()).select_from(FaqEntry).where(FaqEntry.bot_id == bot.id)),
        "flows": session.scalar(select(func.count()).select_from(Flow).where(Flow.bot_id == bot.id)),
        "tools": session.scalar(select(func.count()).select_from(Tool).where(Tool.domain_id == bot.domain_id)),
    }
    return {**bot_row(session, bot), "counts": counts, "translate": bots.to_translate(bot)}


@app.get(f"{API}/languages")
def languages():
    """The engine's languages: a bot in any other language would not load."""
    return list(bots.engine_langs())


class NewBotIn(BaseModel):
    domain: str
    domain_title: str | None = None
    lang: str
    title: str | None = None
    start: str = "empty"
    copy_from: str | None = None
    settings: dict[str, Any] | None = None


@app.post(f"{API}/bots", status_code=201, dependencies=[Depends(require_role("admin"))])
def create_bot(body: NewBotIn, session: Session = Depends(get_session), user: User = Depends(current_user)):
    """An empty bot (language starter only) or a copy of a sibling; the 기본 설정 values are checked as on 개요."""
    present = set(session.scalars(select(Domain.slug)))
    importable = [d for d in bots.repo_folders(service.domains_root()) if d not in present]
    extra = set(body.settings or {}) - {"engine", "studio_only"}
    if extra:
        raise HTTPException(422, f"settings: unknown keys {sorted(extra)}")
    try:
        bot = bots.create_bot(session, domain=body.domain, lang=body.lang, domain_title=body.domain_title,
                              title=body.title, start=body.start, copy_from=body.copy_from,
                              engine=(body.settings or {}).get("engine"),
                              studio_only=(body.settings or {}).get("studio_only"),
                              importable=importable, user_id=user.id)
    except bots.BotExists as exc:
        session.rollback()
        raise HTTPException(409, {"message": str(exc), "reason": exc.reason})
    except (bots.BotError, settings.SettingsError) as exc:
        session.rollback()
        raise HTTPException(422, str(exc))
    session.commit()
    return one_bot(bot.slug, session)


@app.get(f"{API}/bots/{{b}}/delete-impact")
def bot_delete_impact(b: str, session: Session = Depends(get_session)):
    return bots.delete_impact(session, get_bot(session, b))


@app.delete(f"{API}/bots/{{b}}")
def delete_bot(b: str, session: Session = Depends(get_session), user: User = Depends(require_role("admin"))):
    """The bot, its draft, layout and publications, its export directory and its test conversations; the domain
    too when this was its last bot. Cannot be undone (a repository domain can be imported again)."""
    bot = get_bot(session, b)
    out = bots.delete_bot(session, bot)
    session.commit()
    chat.end_bot(b)
    service.remove_export_dir(b)
    return out


class TranslateIn(BaseModel):
    faq: list[str] = Field(default_factory=list)
    flows: list[str] = Field(default_factory=list)
    notices: list[str] = Field(default_factory=list)


@app.put(f"{API}/bots/{{b}}/translation")
def put_translation(b: str, body: TranslateIn, session: Session = Depends(get_session)):
    """What a copied bot still holds in its source's language; only removals are possible."""
    bot = get_bot(session, b)
    try:
        bots.set_to_translate(bot, body.model_dump())
    except bots.BotError as exc:
        raise HTTPException(422, str(exc))
    session.commit()
    return bots.to_translate(bot)


@app.get(f"{API}/domains")
def list_domains(session: Session = Depends(get_session)):
    out = []
    for d in session.scalars(select(Domain).order_by(Domain.slug)):
        out.append({"slug": d.slug, "title": d.title, "shared_revision": d.shared_revision,
                    "bots": [service.bot_status(b, d) for b in sorted(d.bots, key=lambda x: x.slug)]})
    return out


@app.get(f"{API}/domains/importable")
def importable():
    root = service.domains_root()
    if not os.path.isdir(root):
        return []
    return sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)))


class ImportRequest(BaseModel):
    source: str = "repo_domains"
    domain: str
    replace: bool = False


@app.post(f"{API}/domains/import", status_code=201, dependencies=[Depends(require_role("admin"))])
def import_domain(req: ImportRequest, session: Session = Depends(get_session), user: User = Depends(current_user)):
    if req.source != "repo_domains":
        raise HTTPException(400, "only source=repo_domains is supported in ST1")
    if "/" in req.domain or "\\" in req.domain or req.domain.startswith("."):
        raise HTTPException(400, "bad domain name")
    try:
        summary = portable.import_domain(session, service.domains_root(), req.domain, req.replace, user.id)
    except FileExistsError:
        session.rollback()
        raise HTTPException(409, f"domain {req.domain} exists; send replace=true to replace the draft")
    except portable.ImportError_ as exc:
        session.rollback()
        raise HTTPException(400, str(exc))
    session.commit()
    return summary


@app.get(f"{API}/domains/{{d}}")
def one_domain(d: str, session: Session = Depends(get_session)):
    dom = get_domain(session, d)
    return {"slug": dom.slug, "title": dom.title, "shared_revision": dom.shared_revision,
            "bots": [service.bot_status(b, dom) for b in sorted(dom.bots, key=lambda x: x.slug)],
            "tool_count": session.scalar(select(func.count()).select_from(Tool).where(Tool.domain_id == dom.id))}


# --- bot defaults: engine config (exported) and studio-only values (not exported) ---

class SettingsIn(BaseModel):
    title: str | None = None
    engine: dict[str, Any] | None = None
    studio_only: dict[str, Any] | None = None
    revision: int | None = None


def _config(session: Session, bot: Bot) -> DomainSetting | None:
    return session.scalar(select(DomainSetting).where(DomainSetting.bot_id == bot.id, DomainSetting.kind == "config"))


def settings_out(session: Session, bot: Bot) -> dict:
    cfg = _config(session, bot)
    stored = bot.studio_settings or {}
    flows = session.scalars(select(Flow).where(Flow.bot_id == bot.id)).all()
    dom = session.get(Domain, bot.domain_id)
    return {"slug": bot.slug, "title": bot.title, "lang": bot.lang, "domain": dom.slug, "domain_title": dom.title,
            "revision": cfg.revision if cfg else 0, "has_config_file": cfg is not None,
            "engine": settings.engine_view(cfg.body if cfg else None),
            "studio_only": {"handoff_number": stored.get("handoff_number"), "policy": stored.get("policy") or {}},
            "policy_refs": settings.policy_refs(flows)}


@app.get(API + "/bots/{b}/settings")
def get_settings(b: str, session: Session = Depends(get_session)):
    return settings_out(session, get_bot(session, b))


@app.put(API + "/bots/{b}/settings")
def put_settings(b: str, body: SettingsIn, session: Session = Depends(get_session), user: User = Depends(current_user)):
    """Only the engine part changes the draft (and so needs validation and publishing); the name and the
    studio-only values are not exported."""
    bot = get_bot(session, b)
    cfg = _config(session, bot)
    if cfg is not None:
        check_revision(cfg, body.revision, settings_out(session, bot))
    try:
        clean = settings.check_engine(body.engine) if body.engine is not None else None
        studio = settings.check_studio_only(body.studio_only) if body.studio_only is not None else None
    except settings.SettingsError as exc:
        raise HTTPException(422, str(exc))
    if body.title is not None:
        if not body.title.strip() or len(body.title) > 200:
            raise HTTPException(422, "title: 1 to 200 characters")
        bot.title = body.title.strip()
    if studio is not None:
        bot.studio_settings = studio
    if clean is not None:
        merged = settings.merge_config(cfg.body if cfg else None, clean)
        if cfg is None:
            session.add(DomainSetting(bot_id=bot.id, kind="config", body=merged, updated_by=user.id))
            touch_bot(bot)
        elif merged != cfg.body:
            cfg.body = merged
            cfg.revision += 1
            cfg.updated_by = user.id
            touch_bot(bot)
    session.commit()
    return settings_out(session, bot)


# --- FAQ ---

class FaqIn(BaseModel):
    id: str | None = None
    question: str
    answer: str
    paraphrases: list[str] | None = None
    asr_variants: list[str] | None = None
    pattern: dict[str, Any] | None = None
    revision: int | None = None


def faq_out(e: FaqEntry) -> dict:
    return {"id": e.entry_id, "position": e.position, "question": e.question, "answer": e.answer,
            "paraphrases": e.paraphrases, "asr_variants": e.asr_variants, "pattern": e.pattern, "revision": e.revision}


def _faq(session: Session, bot: Bot, entry_id: str) -> FaqEntry:
    e = session.scalar(select(FaqEntry).where(FaqEntry.bot_id == bot.id, FaqEntry.entry_id == entry_id))
    if e is None:
        raise HTTPException(404, f"no FAQ entry {entry_id}")
    return e


def published_faq(session: Session, bot: Bot) -> dict[str, dict] | None:
    """FAQ entries of the newest publication by id (entry fields plus its pattern), or None if never published."""
    pub = session.scalar(select(Publication).where(Publication.bot_id == bot.id).order_by(Publication.number.desc()).limit(1))
    if pub is None:
        return None
    dom = session.get(Domain, bot.domain_id)
    base = f"{dom.slug}/{bot.lang}"
    faq = session.get(PublicationFile, (pub.id, f"{base}/faq.yaml"))
    pats = session.get(PublicationFile, (pub.id, f"{base}/rules/faq_patterns.yaml"))
    by_id = {e["id"]: dict(e) for e in ((yamlio.load(faq.content) or {}).get("entries") or [])} if faq else {}
    for p in ((yamlio.load(pats.content) or {}).get("entries") or []) if pats else []:
        p = dict(p)
        if p.get("id") in by_id:
            by_id[p.pop("id")]["pattern"] = p
    return by_id


def _same_as_published(e: FaqEntry, pub: dict) -> bool:
    mine = {"question": e.question, "answer": e.answer, "paraphrases": e.paraphrases, "asr_variants": e.asr_variants,
            "pattern": e.pattern}
    theirs = {k: pub.get(k) for k in mine}
    return mine == theirs


@app.get(API + "/bots/{b}/faq")
def list_faq(b: str, session: Session = Depends(get_session)):
    """`published`: "same", "changed" or "new" against the newest publication; null when nothing is published."""
    bot = get_bot(session, b)
    pub = published_faq(session, bot)
    left = set(bots.to_translate(bot)["faq"])
    out = []
    for e in session.scalars(select(FaqEntry).where(FaqEntry.bot_id == bot.id).order_by(FaqEntry.position)):
        state = None if pub is None else "new" if e.entry_id not in pub else             "same" if _same_as_published(e, pub[e.entry_id]) else "changed"
        out.append({**faq_out(e), "published": state, "to_translate": e.entry_id in left})
    return out


@app.post(API + "/bots/{b}/faq", status_code=201)
def create_faq(b: str, body: FaqIn, session: Session = Depends(get_session), user: User = Depends(current_user)):
    bot = get_bot(session, b)
    if not body.id:
        raise HTTPException(422, "id is required")
    if session.scalar(select(FaqEntry).where(FaqEntry.bot_id == bot.id, FaqEntry.entry_id == body.id)):
        raise HTTPException(409, f"FAQ entry {body.id} exists")
    pos = (session.scalar(select(func.max(FaqEntry.position)).where(FaqEntry.bot_id == bot.id)) or -1) + 1
    e = FaqEntry(bot_id=bot.id, entry_id=body.id, position=pos, question=body.question, answer=body.answer,
                 paraphrases=body.paraphrases, asr_variants=body.asr_variants, pattern=body.pattern, updated_by=user.id)
    session.add(e)
    touch_bot(bot)
    session.commit()
    return faq_out(e)


@app.put(API + "/bots/{b}/faq/order", status_code=204)
def order_faq(b: str, body: dict, session: Session = Depends(get_session)):
    bot = get_bot(session, b)
    ids = body.get("ids") or []
    rows = {e.entry_id: e for e in session.scalars(select(FaqEntry).where(FaqEntry.bot_id == bot.id))}
    if set(ids) != set(rows):
        raise HTTPException(422, "ids must list every FAQ entry exactly once")
    for i, eid in enumerate(ids):
        rows[eid].position = i
    touch_bot(bot)
    session.commit()
    return Response(status_code=204)


@app.put(API + "/bots/{b}/faq/{entry_id}")
def update_faq(b: str, entry_id: str, body: FaqIn, session: Session = Depends(get_session),
               user: User = Depends(current_user)):
    bot = get_bot(session, b)
    e = _faq(session, bot, entry_id)
    check_revision(e, body.revision, faq_out(e))
    e.question, e.answer = body.question, body.answer
    e.paraphrases, e.asr_variants, e.pattern = body.paraphrases, body.asr_variants, body.pattern
    e.revision += 1
    e.updated_by = user.id
    bots.mark_translated(bot, "faq", entry_id)
    touch_bot(bot)
    session.commit()
    return faq_out(e)


@app.delete(API + "/bots/{b}/faq/{entry_id}", status_code=204)
def delete_faq(b: str, entry_id: str, session: Session = Depends(get_session)):
    bot = get_bot(session, b)
    session.delete(_faq(session, bot, entry_id))
    bots.mark_translated(bot, "faq", entry_id)
    touch_bot(bot)
    session.commit()
    return Response(status_code=204)


# --- tools (shared by the bots of a domain) ---

class ToolIn(BaseModel):
    name: str | None = None
    body: dict[str, Any] | None = None
    revision: int | None = None


def tool_out(t: Tool) -> dict:
    return {"name": t.name, "position": t.position, "body": t.body or {}, "revision": t.revision}


def _tool(session: Session, dom: Domain, name: str) -> Tool:
    t = session.scalar(select(Tool).where(Tool.domain_id == dom.id, Tool.name == name))
    if t is None:
        raise HTTPException(404, f"no tool {name}")
    return t


def check_tool_body(name: str, body: dict) -> None:
    """Refuse what the engine's loader would refuse for this tool (types, `returns`, fake API rules against both:
    R16b, P6). `requires` and `verifies` are checked across the whole domain at validation, so they are left out."""
    from voxstage.tools import FakeApiExecutor   # read only
    own = {k: v for k, v in body.items() if k not in ("requires", "verifies")}
    try:
        FakeApiExecutor({"tools": {name: own}})
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(422, str(exc))


def affected_bots(dom: Domain) -> list[str]:
    return sorted(b.slug for b in dom.bots)


@app.get(API + "/domains/{d}/tools")
def list_tools(d: str, session: Session = Depends(get_session)):
    dom = get_domain(session, d)
    return [tool_out(t) for t in session.scalars(select(Tool).where(Tool.domain_id == dom.id).order_by(Tool.position))]


@app.post(API + "/domains/{d}/tools", status_code=201)
def create_tool(d: str, body: ToolIn, session: Session = Depends(get_session), user: User = Depends(current_user)):
    dom = get_domain(session, d)
    if not body.name:
        raise HTTPException(422, "name is required")
    if session.scalar(select(Tool).where(Tool.domain_id == dom.id, Tool.name == body.name)):
        raise HTTPException(409, f"tool {body.name} exists")
    check_tool_body(body.name, body.body or {})
    pos = (session.scalar(select(func.max(Tool.position)).where(Tool.domain_id == dom.id)) or -1) + 1
    t = Tool(domain_id=dom.id, name=body.name, position=pos, body=body.body or {}, updated_by=user.id)
    session.add(t)
    touch_domain(session, dom)
    session.commit()
    return {**tool_out(t), "affects_bots": affected_bots(dom)}


def flows_calling(session: Session, dom: Domain, tool: str) -> list[dict]:
    out = []
    for bot in dom.bots:
        for f in session.scalars(select(Flow).where(Flow.bot_id == bot.id)):
            if any(isinstance(n, dict) and n.get("type") == "call" and n.get("tool") == tool for n in f.nodes.values()):
                out.append({"bot": bot.slug, "flow": f.flow_id})
    return out


@app.put(API + "/domains/{d}/tools/{name}")
def update_tool(d: str, name: str, body: ToolIn, session: Session = Depends(get_session),
                user: User = Depends(current_user)):
    dom = get_domain(session, d)
    t = _tool(session, dom, name)
    check_revision(t, body.revision, tool_out(t))
    check_tool_body(name, body.body or {})
    t.body = body.body or {}
    t.revision += 1
    t.updated_by = user.id
    touch_domain(session, dom)
    session.commit()
    return {**tool_out(t), "affects_bots": affected_bots(dom), "used_by_flows": flows_calling(session, dom, name)}


@app.delete(API + "/domains/{d}/tools/{name}", status_code=204)
def delete_tool(d: str, name: str, force: bool = False, session: Session = Depends(get_session)):
    dom = get_domain(session, d)
    t = _tool(session, dom, name)
    users = flows_calling(session, dom, name)
    if users and not force:
        raise HTTPException(409, {"message": "flows call this tool", "flows": users})
    session.delete(t)
    touch_domain(session, dom)
    session.commit()
    return Response(status_code=204)


# --- type dictionary and session roles (types.yaml, shared by the bots of a domain; ADR 0014) ---

class TypesIn(BaseModel):
    body: dict[str, Any]
    revision: int | None = None
    force: bool = False


def _types_row(session: Session, dom: Domain) -> DomainSetting | None:
    return session.scalar(select(DomainSetting).where(DomainSetting.domain_id == dom.id, DomainSetting.kind == "types"))


def domain_flows(session: Session, dom: Domain) -> list[tuple[str, str, dict, dict]]:
    return [(bot.slug, f.flow_id, f.header or {}, f.nodes or {})
            for bot in sorted(dom.bots, key=lambda x: x.slug)
            for f in session.scalars(select(Flow).where(Flow.bot_id == bot.id).order_by(Flow.flow_id))]


def types_out(session: Session, dom: Domain) -> dict:
    row = _types_row(session, dom)
    body = (row.body if row else None) or {}
    return {"domain": dom.slug, "exists": row is not None, "revision": row.revision if row else 0,
            "body": {"types": {}, "session_roles": {}, **body}, "usage": datatypes.usage(body, domain_flows(session, dom)),
            "field_types": list(_engine_extractors()), "affects_bots": affected_bots(dom)}


def _engine_extractors() -> tuple[str, ...]:
    from voxstage.rules.flows import EXTRACTORS   # read only: the field types are the engine's extractors
    return EXTRACTORS


@app.get(API + "/domains/{d}/types")
def get_types(d: str, session: Session = Depends(get_session)):
    return types_out(session, get_domain(session, d))


@app.put(API + "/domains/{d}/types")
def put_types(d: str, body: TypesIn, session: Session = Depends(get_session), user: User = Depends(current_user)):
    dom = get_domain(session, d)
    row = _types_row(session, dom)
    if row is not None:
        check_revision(row, body.revision, types_out(session, dom))
    errs = datatypes.check_types(body.body, _engine_extractors())
    if errs:
        raise HTTPException(422, {"message": "invalid type dictionary", "problems": errs})
    broken = datatypes.broken_by(row.body if row else None, body.body, domain_flows(session, dom))
    if broken and not body.force:
        raise HTTPException(409, {"message": "scenarios use what this change removes", "uses": broken})
    doc = {k: v for k, v in body.body.items() if v not in ({}, None)}
    if not doc:
        if row is not None:
            session.delete(row)
    elif row is None:
        session.add(DomainSetting(domain_id=dom.id, kind="types", body=doc, updated_by=user.id))
    else:
        row.body, row.updated_by = doc, user.id
        row.revision += 1
    touch_domain(session, dom)
    session.commit()
    return types_out(session, dom)


# --- 안내 문구 and 응답 규칙 (ST3) ---

def _bot_setting(session: Session, bot: Bot, kind: str) -> DomainSetting | None:
    return session.scalar(select(DomainSetting).where(DomainSetting.bot_id == bot.id, DomainSetting.kind == kind))


def _bot_flows(session: Session, bot: Bot) -> list[Flow]:
    return list(session.scalars(select(Flow).where(Flow.bot_id == bot.id).order_by(Flow.flow_id)))


def _attribute_names(session: Session, bot: Bot) -> list[str]:
    dom = session.get(Domain, bot.domain_id)
    types = _types_row(session, dom)
    return wording.attribute_names(_bot_flows(session, bot), ((types.body if types else None) or {}).get("session_roles"))


def _starter_body(lang: str, rel: str):
    try:
        return bots._starter(lang, rel)
    except bots.BotError:
        return None


def notices_out(session: Session, bot: Bot) -> dict:
    row = _bot_setting(session, bot, "notices")
    starter = _starter_body(bot.lang, "notices.yaml") or {}
    form = wording.stored_to_form(row.body if row else starter)
    flows = _bot_flows(session, bot)
    used = {n["id"]: sorted(f.flow_id for f in flows
                            if any(isinstance(x, dict) and x.get("type") == "notices"
                                   and (x.get("ids") is None or n["id"] in x["ids"]) for x in (f.nodes or {}).values()))
            for n in form["notices"]}
    return {"slug": bot.slug, "lang": bot.lang, "exists": row is not None, "revision": row.revision if row else 0,
            **form, "starter_wording": wording.stored_to_form(starter)["wording"],
            "meaning": wording.WORDING_MEANING, "placeholder_keys": list(wording.PLACEHOLDER_KEYS),
            "attributes": _attribute_names(session, bot), "reserved": wording.RESERVED,
            "to_translate": bots.to_translate(bot)["notices"], "used_by": used}


class NoticeIn(BaseModel):
    id: str
    text: str
    applies_when: str | None = None


class NoticesIn(BaseModel):
    notices: list[NoticeIn]
    wording: dict[str, str]
    revision: int | None = None


class ExpressionIn(BaseModel):
    text: str


@app.get(API + "/bots/{b}/notices")
def get_notices(b: str, session: Session = Depends(get_session)):
    return notices_out(session, get_bot(session, b))


@app.put(API + "/bots/{b}/notices")
def put_notices(b: str, body: NoticesIn, session: Session = Depends(get_session), user: User = Depends(current_user)):
    bot = get_bot(session, b)
    row = _bot_setting(session, bot, "notices")
    if row is not None:
        check_revision(row, body.revision, notices_out(session, bot))
    try:
        stored = wording.check_notices(body.model_dump(exclude={"revision"}), _attribute_names(session, bot))
    except wording.WordingError as exc:
        raise HTTPException(422, {"message": "invalid notices", "problems": exc.problems})
    before = wording.stored_to_form(row.body if row else None)["notices"]
    if row is None:
        session.add(DomainSetting(bot_id=bot.id, kind="notices", body=stored, updated_by=user.id))
        touch_bot(bot)
    elif stored != row.body:
        row.body, row.updated_by = stored, user.id
        row.revision += 1
        touch_bot(bot)
    # ST3 D6, per item: a fixed notice that was changed or removed is no longer the sibling's text
    old = {n["id"]: n for n in before}
    for n in body.notices:
        if old.get(n.id, {}).get("text") != n.text:
            bots.mark_translated(bot, "notices", n.id)
    for nid in set(old) - {n.id for n in body.notices}:
        bots.mark_translated(bot, "notices", nid)
    session.commit()
    return notices_out(session, bot)


@app.post(API + "/bots/{b}/notices/check-expression")
def check_expression(b: str, body: ExpressionIn, session: Session = Depends(get_session)):
    bot = get_bot(session, b)
    return wording.check_expression(body.text, _attribute_names(session, bot))


def rules_out(session: Session, bot: Bot) -> dict:
    out: dict[str, Any] = {"slug": bot.slug, "lang": bot.lang, "kinds": {}}
    for kind in wording.RULE_KINDS:
        row = _bot_setting(session, bot, kind)
        starter = _starter_body(bot.lang, portable.BOT_SETTINGS[kind])
        out["kinds"][kind] = {"exists": row is not None, "revision": row.revision if row else 0,
                              "body": row.body if row else starter, "starter": starter}
    return out


class RuleIn(BaseModel):
    body: dict[str, Any]
    revision: int | None = None


class RuleTestIn(BaseModel):
    text: str = Field(max_length=500)
    bodies: dict[str, dict[str, Any]] | None = None


@app.get(API + "/bots/{b}/rules")
def get_rules(b: str, session: Session = Depends(get_session)):
    return rules_out(session, get_bot(session, b))


@app.put(API + "/bots/{b}/rules/{kind}")
def put_rule(b: str, kind: str, body: RuleIn, session: Session = Depends(get_session),
             user: User = Depends(current_user)):
    if kind not in wording.RULE_KINDS:
        raise HTTPException(404, f"no rule file {kind}")
    bot = get_bot(session, b)
    row = _bot_setting(session, bot, kind)
    if row is not None:
        check_revision(row, body.revision, rules_out(session, bot))
    try:
        wording.check_rule(kind, body.body)
    except wording.WordingError as exc:
        raise HTTPException(422, {"message": f"invalid {kind}", "problems": exc.problems})
    if row is None:
        session.add(DomainSetting(bot_id=bot.id, kind=kind, body=body.body, updated_by=user.id))
        touch_bot(bot)
    elif body.body != row.body:
        row.body, row.updated_by = body.body, user.id
        row.revision += 1
        touch_bot(bot)
    session.commit()
    return rules_out(session, bot)


@app.post(API + "/bots/{b}/rules/test")
def test_rules(b: str, body: RuleTestIn, session: Session = Depends(get_session)):
    """The engine's matchers on a typed sentence, with the saved rule words or the ones the form holds."""
    bot = get_bot(session, b)
    current = rules_out(session, bot)["kinds"]
    bodies = {k: (body.bodies or {}).get(k, current[k]["body"]) for k in wording.RULE_KINDS}
    try:
        return wording.test_sentence(bot.lang, body.text, bodies)
    except wording.WordingError as exc:
        raise HTTPException(422, {"message": "invalid rule words", "problems": exc.problems})


# --- slot lists of a domain (sensitive_slots.yaml, readback_slots.yaml; ST3) ---

def _list_row(session: Session, dom: Domain, kind: str) -> DomainSetting | None:
    return session.scalar(select(DomainSetting).where(DomainSetting.domain_id == dom.id, DomainSetting.kind == kind))


def _asked(session: Session, dom: Domain) -> dict[str, dict]:
    types = _types_row(session, dom)
    return slotlists.asked_attributes(domain_flows(session, dom), types.body if types else None)


def slot_lists_out(session: Session, dom: Domain) -> dict:
    sens, back = _list_row(session, dom, "sensitive_slots"), _list_row(session, dom, "readback_slots")
    asked = _asked(session, dom)
    sens_names = list((sens.body or {}).get("sensitive_slots") or []) if sens else []
    back_map = dict((back.body or {}).get("readback_slots") or {}) if back else {}
    return {"domain": dom.slug, "sensitive": {"revision": sens.revision if sens else 0, "slots": sens_names},
            "readback": {"revision": back.revision if back else 0,
                         "slots": [{"slot": k, "format": v} for k, v in back_map.items()]},
            "candidates": slotlists.candidates(asked), "formats": slotlists.formats(),
            "asked_in": {a: sorted({f"{bot}/{fid}" for bot, fid in e["flows"]}) for a, e in asked.items()},
            "affects_bots": affected_bots(dom)}


class SlotListsIn(BaseModel):
    sensitive: list[str]
    readback: list[dict[str, str]]
    sensitive_revision: int | None = None
    readback_revision: int | None = None


@app.get(API + "/domains/{d}/slot-lists")
def get_slot_lists(d: str, session: Session = Depends(get_session)):
    return slot_lists_out(session, get_domain(session, d))


@app.put(API + "/domains/{d}/slot-lists")
def put_slot_lists(d: str, body: SlotListsIn, session: Session = Depends(get_session),
                   user: User = Depends(current_user)):
    dom = get_domain(session, d)
    sens, back = _list_row(session, dom, "sensitive_slots"), _list_row(session, dom, "readback_slots")
    current = slot_lists_out(session, dom)
    if sens is not None:
        check_revision(sens, body.sensitive_revision, current)
    if back is not None:
        check_revision(back, body.readback_revision, current)
    now_back = {r["slot"]: r["format"] for r in current["readback"]["slots"]}
    try:
        clean = slotlists.check_lists(body.sensitive, body.readback,
                                      {"sensitive": current["sensitive"]["slots"], "readback": now_back},
                                      _asked(session, dom))
    except wording.WordingError as exc:
        raise HTTPException(422, {"message": "invalid slot lists", "problems": exc.problems})
    changed = False
    for kind, row, doc, same in (
            ("sensitive_slots", sens, {"sensitive_slots": clean["sensitive"]} if clean["sensitive"] else None,
             clean["sensitive"] == current["sensitive"]["slots"]),
            ("readback_slots", back, {"readback_slots": clean["readback"]} if clean["readback"] else None,
             clean["readback"] == now_back)):
        if same:
            continue
        changed = True
        if doc is None:
            session.delete(row)
        elif row is None:
            session.add(DomainSetting(domain_id=dom.id, kind=kind, body=doc, updated_by=user.id))
        else:
            row.body, row.updated_by = doc, user.id
            row.revision += 1
    if changed:
        touch_domain(session, dom)
    session.commit()
    return slot_lists_out(session, dom)


# --- flows (viewer in ST1) ---

def layout_out(session: Session, bot: Bot, flow_id: str) -> dict:
    lay = session.get(FlowLayout, (bot.id, flow_id))
    nodes = {r.node_id: {"x": r.x, "y": r.y, "collapsed": r.collapsed}
             for r in session.scalars(select(FlowNodeLayout).where(FlowNodeLayout.bot_id == bot.id,
                                                                    FlowNodeLayout.flow_id == flow_id))}
    return {"viewport": lay.viewport if lay else None, "direction": lay.direction if lay else "LR", "nodes": nodes}


def flow_items(bot: Bot, flow_id: str) -> list[dict]:
    rep = service.cached_report(bot)
    if not rep:
        return []
    return [i for i in rep["items"] if i.get("flow_id") == flow_id]


@app.get(API + "/bots/{b}/flows")
def list_flows(b: str, session: Session = Depends(get_session)):
    bot = get_bot(session, b)
    left = set(bots.to_translate(bot)["flows"])
    out = []
    for f in session.scalars(select(Flow).where(Flow.bot_id == bot.id).order_by(Flow.flow_id)):
        out.append({"id": f.flow_id, "start": f.start, "node_count": len(f.nodes), "buttons": f.header.get("buttons", []),
                    "role": f.header.get("role"), "triggers": f.header.get("triggers"),
                    "items": flow_items(bot, f.flow_id), "to_translate": f.flow_id in left})
    return out


@app.get(API + "/bots/{b}/flows/{flow_id}")
def get_flow(b: str, flow_id: str, session: Session = Depends(get_session)):
    bot = get_bot(session, b)
    f = session.scalar(select(Flow).where(Flow.bot_id == bot.id, Flow.flow_id == flow_id))
    if f is None:
        raise HTTPException(404, f"no flow {flow_id}")
    return {"flow": {"id": f.flow_id, "header": f.header, "start": f.start, "nodes": f.nodes,
                     "node_order": f.node_order, "revision": f.revision},
            "layout": layout_out(session, bot, flow_id), "graph": service.flow_graph(f),
            "items": flow_items(bot, flow_id)}


class LayoutIn(BaseModel):
    viewport: dict[str, Any] | None = None
    direction: str = "LR"
    nodes: dict[str, dict[str, Any]] = Field(default_factory=dict)


@app.put(API + "/bots/{b}/flows/{flow_id}/layout", status_code=204)
def put_layout(b: str, flow_id: str, body: LayoutIn, session: Session = Depends(get_session),
               user: User = Depends(current_user)):
    """Layout never changes a revision, a validation result or a publication (ADR 0013)."""
    bot = get_bot(session, b)
    f = session.scalar(select(Flow).where(Flow.bot_id == bot.id, Flow.flow_id == flow_id))
    if f is None:
        raise HTTPException(404, f"no flow {flow_id}")
    if body.direction not in ("LR", "TB"):
        raise HTTPException(422, "direction is LR or TB")
    lay = session.get(FlowLayout, (bot.id, flow_id))
    if lay is None:
        lay = FlowLayout(bot_id=bot.id, flow_id=flow_id)
        session.add(lay)
    lay.viewport, lay.direction, lay.saved_by = body.viewport, body.direction, user.id
    session.execute(delete(FlowNodeLayout).where(FlowNodeLayout.bot_id == bot.id, FlowNodeLayout.flow_id == flow_id))
    for node_id, p in body.nodes.items():
        if node_id in f.nodes:
            session.add(FlowNodeLayout(bot_id=bot.id, flow_id=flow_id, node_id=node_id, x=float(p.get("x", 0)),
                                       y=float(p.get("y", 0)), collapsed=bool(p.get("collapsed", False))))
    session.commit()
    return Response(status_code=204)


# --- flow editing (ST2): meaning only; positions go through /layout ---

NODE_KINDS = {"say", "ask", "form", "confirm", "call", "branch", "notices", "goto", "end"}
FLOW_HEADER_KEYS = set(portable.FLOW_HEADER_ORDER) | {"role"}
NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class FlowIn(BaseModel):
    header: dict[str, Any] | None = None
    start: str | None = None
    nodes: dict[str, dict[str, Any]]
    node_order: list[str] | None = None
    revision: int | None = None


def _flow(session: Session, bot: Bot, flow_id: str) -> Flow:
    f = session.scalar(select(Flow).where(Flow.bot_id == bot.id, Flow.flow_id == flow_id))
    if f is None:
        raise HTTPException(404, f"no flow {flow_id}")
    return f


def check_flow_shape(body: FlowIn) -> None:
    """Shape only: the engine loader checks meaning (reachability, tools, names) at validation. A draft may hold
    a dangling link while it is being edited."""
    for nid, node in body.nodes.items():
        if not NAME.match(nid):
            raise HTTPException(422, f"node id {nid!r}: letters, digits and _ only, not starting with a digit")
        if not isinstance(node, dict) or node.get("type") not in NODE_KINDS:
            raise HTTPException(422, f"node {nid}: type must be one of {sorted(NODE_KINDS)}")
    if body.start is not None and body.start not in body.nodes:
        raise HTTPException(422, f"start {body.start!r} is not a node of this flow")
    if body.header is not None and set(body.header) - FLOW_HEADER_KEYS:
        raise HTTPException(422, f"unknown flow keys {sorted(set(body.header) - FLOW_HEADER_KEYS)}")


def check_flow_roles(session: Session, bot: Bot, header: dict | None) -> None:
    if header is None or "roles" not in header:
        return
    row = _types_row(session, session.get(Domain, bot.domain_id))
    errs = datatypes.check_flow_roles(header["roles"], row.body if row else None)
    if errs:
        raise HTTPException(422, {"message": "invalid roles", "problems": errs})


@app.put(API + "/bots/{b}/flows/{flow_id}")
def update_flow(b: str, flow_id: str, body: FlowIn, session: Session = Depends(get_session),
                user: User = Depends(current_user)):
    bot = get_bot(session, b)
    f = _flow(session, bot, flow_id)
    check_revision(f, body.revision, {"revision": f.revision})
    check_flow_shape(body)
    check_flow_roles(session, bot, body.header)
    order = [n for n in (body.node_order or f.node_order) if n in body.nodes]
    order += [n for n in body.nodes if n not in order]
    if body.header is not None:
        f.header = dict(body.header)
    f.start, f.nodes, f.node_order = body.start, dict(body.nodes), order
    f.revision += 1
    f.updated_by = user.id
    portable.prune_layout(session, bot, flow_id, set(body.nodes))
    bots.mark_translated(bot, "flows", flow_id)
    touch_bot(bot)
    session.commit()
    return get_flow(b, flow_id, session)


class NewFlowIn(BaseModel):
    id: str


@app.post(API + "/bots/{b}/flows", status_code=201)
def create_flow(b: str, body: NewFlowIn, session: Session = Depends(get_session), user: User = Depends(current_user)):
    """A new flow starts as one `end` node with an empty trigger; validation says what is still missing."""
    bot = get_bot(session, b)
    if not re.fullmatch(r"[a-z][a-z0-9_]*", body.id):
        raise HTTPException(422, "id: lower-case letters, digits and _ only, starting with a letter")
    if session.scalar(select(Flow).where(Flow.bot_id == bot.id, Flow.flow_id == body.id)):
        raise HTTPException(409, f"flow {body.id} exists")
    session.add(Flow(bot_id=bot.id, flow_id=body.id, header={"triggers": {"any_of": []}}, start="done",
                     nodes={"done": {"type": "end"}}, node_order=["done"], updated_by=user.id))
    touch_bot(bot)
    session.commit()
    return get_flow(b, body.id, session)


@app.delete(API + "/bots/{b}/flows/{flow_id}", status_code=204)
def delete_flow(b: str, flow_id: str, session: Session = Depends(get_session)):
    bot = get_bot(session, b)
    session.delete(_flow(session, bot, flow_id))
    session.execute(delete(FlowNodeLayout).where(FlowNodeLayout.bot_id == bot.id, FlowNodeLayout.flow_id == flow_id))
    lay = session.get(FlowLayout, (bot.id, flow_id))
    if lay is not None:
        session.delete(lay)
    bots.mark_translated(bot, "flows", flow_id)
    touch_bot(bot)
    session.commit()
    return Response(status_code=204)


# --- 대화로 테스트: the validated draft on typed text (studio_backend/chat.py) ---

class ChatIn(BaseModel):
    setup: dict[str, Any] | None = None


class TurnIn(BaseModel):
    kind: str = "text"
    text: str


def _chat_out(s: chat.ChatSession, bot: Bot, dom: Domain) -> dict:
    return {"id": s.id, "draft_revision": s.draft_revision, "shared_revision": s.shared_revision,
            "stale": (bot.draft_revision, dom.shared_revision) != (s.draft_revision, s.shared_revision)}


@app.post(API + "/bots/{b}/chat", status_code=201)
def start_chat(b: str, body: ChatIn, session: Session = Depends(get_session)):
    """Only a draft that passed validation runs: the engine would refuse anything else at load."""
    bot = get_bot(session, b)
    dom = session.get(Domain, bot.domain_id)
    status = service.bot_status(bot, dom)
    if not status["validated"]:
        raise HTTPException(409, {"message": "validate the draft first", "reason": "not_validated"})
    if not status["valid"]:
        raise HTTPException(409, {"message": "the draft has problems", "reason": "invalid"})
    setup = dict(body.setup or {})
    policy = (bot.studio_settings or {}).get("policy") or {}
    if policy and "policy" not in setup:
        setup["policy"] = policy
    flows = {f.flow_id: f.nodes for f in session.scalars(select(Flow).where(Flow.bot_id == bot.id))}
    buttons = sorted({btn for f in session.scalars(select(Flow).where(Flow.bot_id == bot.id))
                      for btn in (f.header or {}).get("buttons") or []})
    s = chat.start(bot.slug, dom.slug, bot.lang, portable.export_bot(session, bot), flows, setup,
                   bot.draft_revision, dom.shared_revision)
    row = _types_row(session, dom)
    headers = [f.header or {} for f in session.scalars(select(Flow).where(Flow.bot_id == bot.id))]
    return {**_chat_out(s, bot, dom), "buttons": buttons, "setup": setup,
            "labels": datatypes.attribute_labels(row.body if row else None, headers, bot.lang)}


@app.post(API + "/bots/{b}/chat/{sid}/turns")
def chat_turn(b: str, sid: str, body: TurnIn, session: Session = Depends(get_session)):
    bot = get_bot(session, b)
    s = chat.get(sid, bot.slug)
    if s is None:
        raise HTTPException(404, "the test conversation ended; start again")
    if body.kind not in ("text", "digits", "button") or not body.text.strip():
        raise HTTPException(422, "kind is text, digits or button, with some text")
    if body.kind == "digits" and not re.fullmatch(r"[0-9*#]+", body.text.strip()):
        raise HTTPException(422, "digits: 0-9, * and # only")
    return {**chat.turn(s, body.kind, body.text.strip()), **_chat_out(s, bot, session.get(Domain, bot.domain_id))}


@app.delete(API + "/bots/{b}/chat/{sid}", status_code=204)
def end_chat(b: str, sid: str, session: Session = Depends(get_session)):
    bot = get_bot(session, b)
    if chat.get(sid, bot.slug) is not None:
        chat.end(sid)
    return Response(status_code=204)


# --- validation, publication ---

@app.get(API + "/bots/{b}/siblings/check")
def siblings_check(b: str, session: Session = Depends(get_session)):
    """Warnings, not errors: scenarios whose structure differs from the same-id ones of the other-language bots."""
    return siblings.check(session, get_bot(session, b))


@app.post(API + "/bots/{b}/validate")
def validate(b: str, session: Session = Depends(get_session)):
    bot = get_bot(session, b)
    rep = service.validate_bot(session, bot)
    session.commit()
    return rep


@app.get(API + "/bots/{b}/validation")
def last_validation(b: str, session: Session = Depends(get_session)):
    bot = get_bot(session, b)
    return service.refresh_policy_items(session, bot, service.cached_report(bot))


class PublishIn(BaseModel):
    note: str = ""


def _names(session: Session) -> dict[str, str]:
    return dict(session.execute(select(User.id, User.display_name)).all())


def pub_out(p: Publication, files: int | None = None, names: dict[str, str] | None = None) -> dict:
    return {"number": p.number, "note": p.note, "kind": p.kind, "published_by": p.published_by,
            "published_by_name": (names or {}).get(p.published_by),
            "published_at": p.published_at.isoformat(), "content_hash": p.content_hash,
            "shared_revision": p.shared_revision, "restored_from_number": p.restored_from_number,
            **({"file_count": files} if files is not None else {})}


@app.post(API + "/bots/{b}/publications", status_code=201)
def publish(b: str, body: PublishIn, session: Session = Depends(get_session),
            user: User = Depends(require_role("publisher"))):
    bot = get_bot(session, b)
    try:
        pub = service.publish_bot(session, bot, body.note, user.id)
    except service.ValidationFailed as exc:
        session.commit()    # keep the validation result tied to this revision
        return JSONResponse(status_code=422, content={"message": "validation failed", "report": exc.report})
    except service.NothingToPublish:
        session.rollback()
        raise HTTPException(409, "nothing to publish: the content equals the newest publication")
    return pub_out(pub, names={user.id: user.display_name})


class RollbackIn(BaseModel):
    note: str = ""
    discard_draft: bool = False


@app.post(API + "/bots/{b}/publications/{n}/rollback", status_code=201)
def rollback(b: str, n: int, body: RollbackIn, session: Session = Depends(get_session),
             user: User = Depends(require_role("publisher"))):
    """Publish the bot's own files of publication n again as a new publication and make the draft equal to it."""
    bot = get_bot(session, b)
    pub = _pub(session, bot, n)
    try:
        new = service.rollback_bot(session, bot, pub, body.note, body.discard_draft, user.id)
    except service.DraftHasChanges:
        session.rollback()
        return JSONResponse(status_code=409, content={"code": "unpublished_changes", "message":
                            "the draft has changes that are not published; rolling back replaces them"})
    except service.ValidationFailed as exc:
        session.rollback()
        return JSONResponse(status_code=422, content={"message": "validation failed", "report": exc.report})
    except service.NothingToPublish:
        session.rollback()
        return JSONResponse(status_code=409, content={"code": "same_as_newest", "message":
                            "the newest publication already has this content"})
    return pub_out(new, names={user.id: user.display_name})


@app.get(API + "/bots/{b}/publications")
def list_publications(b: str, session: Session = Depends(get_session)):
    bot = get_bot(session, b)
    counts = dict(session.execute(select(PublicationFile.publication_id, func.count())
                                  .join(Publication, Publication.id == PublicationFile.publication_id)
                                  .where(Publication.bot_id == bot.id).group_by(PublicationFile.publication_id)).all())
    names = _names(session)
    return [pub_out(p, counts.get(p.id, 0), names) for p in
            session.scalars(select(Publication).where(Publication.bot_id == bot.id).order_by(Publication.number.desc()))]


def _pub(session: Session, bot: Bot, n: int) -> Publication:
    p = session.scalar(select(Publication).where(Publication.bot_id == bot.id, Publication.number == n))
    if p is None:
        raise HTTPException(404, f"no publication {n}")
    return p


@app.get(API + "/bots/{b}/publications/{n}")
def one_publication(b: str, n: int, session: Session = Depends(get_session)):
    bot = get_bot(session, b)
    p = _pub(session, bot, n)
    files = session.scalars(select(PublicationFile).where(PublicationFile.publication_id == p.id)
                            .order_by(PublicationFile.path)).all()
    return {**pub_out(p, names=_names(session)), "files": [{"path": f.path, "size": len(f.content.encode("utf-8"))} for f in files]}


def _pub_files(session: Session, p: Publication) -> dict[str, str]:
    return {f.path: f.content for f in session.scalars(select(PublicationFile).where(PublicationFile.publication_id == p.id))}


@app.get(API + "/bots/{b}/publications/{n}/diff")
def publication_diff(b: str, n: int, against: str = "previous", session: Session = Depends(get_session)):
    """What changes going from `against` to publication n: the one before it (default), another number, or `draft`.
    With `draft` it is what a rollback to n would change in the draft."""
    bot = get_bot(session, b)
    target = _pub(session, bot, n)
    domain = session.get(Domain, bot.domain_id)
    if against == "draft":
        base, base_ref = portable.export_bot(session, bot), {"kind": "draft", "number": None}
    elif against == "previous":
        prev = session.scalar(select(Publication).where(Publication.bot_id == bot.id, Publication.number < n)
                              .order_by(Publication.number.desc()).limit(1))
        base, base_ref = (_pub_files(session, prev), {"kind": "publication", "number": prev.number}) if prev else             ({}, {"kind": "none", "number": None})
    else:
        try:
            m = int(against)
        except ValueError:
            raise HTTPException(422, "against is previous, draft or a publication number")
        base, base_ref = _pub_files(session, _pub(session, bot, m)), {"kind": "publication", "number": m}
    return {"base": base_ref, "target": {"kind": "publication", "number": n},
            **diffs.compare(base, _pub_files(session, target), domain.slug, bot.lang)}


@app.get(API + "/bots/{b}/changes")
def draft_changes(b: str, session: Session = Depends(get_session)):
    """What the draft changed since the newest publication (the publish dialog); everything is new before the first."""
    bot = get_bot(session, b)
    domain = session.get(Domain, bot.domain_id)
    latest = session.scalar(select(Publication).where(Publication.bot_id == bot.id)
                            .order_by(Publication.number.desc()).limit(1))
    base = _pub_files(session, latest) if latest else {}
    return {"base": {"kind": "publication", "number": latest.number} if latest else {"kind": "none", "number": None},
            "target": {"kind": "draft", "number": None},
            **diffs.compare(base, portable.export_bot(session, bot), domain.slug, bot.lang)}


@app.get(API + "/bots/{b}/publications/{n}/files/{path:path}")
def publication_file(b: str, n: int, path: str, session: Session = Depends(get_session)):
    bot = get_bot(session, b)
    p = _pub(session, bot, n)
    f = session.get(PublicationFile, (p.id, path))
    if f is None:
        raise HTTPException(404, f"no file {path}")
    return Response(f.content, media_type="text/plain; charset=utf-8")


@app.get(API + "/bots/{b}/publications/{n}/export.zip")
def publication_zip(b: str, n: int, session: Session = Depends(get_session)):
    bot = get_bot(session, b)
    p = _pub(session, bot, n)
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in session.scalars(select(PublicationFile).where(PublicationFile.publication_id == p.id)):
            z.writestr(f.path, f.content)
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{bot.slug}-{n}.zip"'})
