"""FastAPI app: the ST1 subset of docs/studio/api.md. No authentication in v1: every request is the seeded local user."""

from __future__ import annotations

import os
import zipfile
from contextlib import asynccontextmanager
from io import BytesIO
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from . import portable, service
from .db import get_session, session_scope
from .models import (Bot, Domain, FaqEntry, Flow, FlowLayout, FlowNodeLayout, Publication, PublicationFile, Role,
                     Tool, User, UserRole)

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


app = FastAPI(title="voxstage studio", version="0.0.1", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5710", "http://127.0.0.1:5710"],
                   allow_methods=["*"], allow_headers=["*"])
API = "/api/v1"


def current_user(session: Session = Depends(get_session)) -> User:
    return session.scalar(select(User).where(User.email == LOCAL_USER_EMAIL))


def require_role(role: str):
    """One place for role checks; v1 lets the local user do everything."""
    def dep(user: User = Depends(current_user), session: Session = Depends(get_session)) -> User:
        return user
    return dep


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
    return {**bot_row(session, bot), "counts": counts}


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


@app.post(f"{API}/domains/import", status_code=201)
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


@app.get(API + "/bots/{b}/faq")
def list_faq(b: str, session: Session = Depends(get_session)):
    bot = get_bot(session, b)
    return [faq_out(e) for e in session.scalars(select(FaqEntry).where(FaqEntry.bot_id == bot.id)
                                                .order_by(FaqEntry.position))]


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
    touch_bot(bot)
    session.commit()
    return faq_out(e)


@app.delete(API + "/bots/{b}/faq/{entry_id}", status_code=204)
def delete_faq(b: str, entry_id: str, session: Session = Depends(get_session)):
    bot = get_bot(session, b)
    session.delete(_faq(session, bot, entry_id))
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
    out = []
    for f in session.scalars(select(Flow).where(Flow.bot_id == bot.id).order_by(Flow.flow_id)):
        out.append({"id": f.flow_id, "start": f.start, "node_count": len(f.nodes), "buttons": f.header.get("buttons", []),
                    "role": f.header.get("role"), "triggers": f.header.get("triggers"),
                    "items": flow_items(bot, f.flow_id)})
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


# --- validation, publication ---

@app.post(API + "/bots/{b}/validate")
def validate(b: str, session: Session = Depends(get_session)):
    bot = get_bot(session, b)
    rep = service.validate_bot(session, bot)
    session.commit()
    return rep


@app.get(API + "/bots/{b}/validation")
def last_validation(b: str, session: Session = Depends(get_session)):
    bot = get_bot(session, b)
    return service.cached_report(bot)


class PublishIn(BaseModel):
    note: str = ""


def pub_out(p: Publication, files: int | None = None) -> dict:
    return {"number": p.number, "note": p.note, "kind": p.kind, "published_by": p.published_by,
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
    return pub_out(pub)


@app.get(API + "/bots/{b}/publications")
def list_publications(b: str, session: Session = Depends(get_session)):
    bot = get_bot(session, b)
    counts = dict(session.execute(select(PublicationFile.publication_id, func.count())
                                  .join(Publication, Publication.id == PublicationFile.publication_id)
                                  .where(Publication.bot_id == bot.id).group_by(PublicationFile.publication_id)).all())
    return [pub_out(p, counts.get(p.id, 0)) for p in
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
    return {**pub_out(p), "files": [{"path": f.path, "size": len(f.content.encode("utf-8"))} for f in files]}


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
