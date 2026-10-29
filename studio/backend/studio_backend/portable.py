"""Import a `domains/<domain>/` tree into the draft, and export a bot back to the engine's files.

The exporter is the only code that writes the engine's format. Paths are relative to a `domains_dir`:
`<domain>/tools.yaml`, `<domain>/<lang>/faq.yaml`, ... A bot's export holds only its own language (docs/studio/data-model.md).
"""

from __future__ import annotations

import os

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import yamlio
from .models import (Bot, Domain, DomainFile, DomainSetting, FaqEntry, Flow, FlowLayout, FlowNodeLayout, Tool)

# settings files: kind -> path inside the domain directory (shared) or the language directory (per bot)
SHARED_SETTINGS = {"sensitive_slots": "sensitive_slots.yaml", "readback_slots": "readback_slots.yaml",
                   "types": "types.yaml"}   # ADR 0014: type dictionary and session roles
BOT_SETTINGS = {"config": "rules/config.yaml", "confirm": "rules/confirm.yaml", "commands": "rules/commands.yaml",
                "corrections": "rules/corrections.yaml", "confusions": "rules/confusions.yaml"}
FLOW_HEADER_ORDER = ("triggers", "buttons", "role", "roles", "captures", "interrupts", "carry", "prefill", "verification")


class ImportError_(ValueError):
    pass


def _read(path: str) -> str:
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def _language_dirs(domain_dir: str) -> list[str]:
    return sorted(d for d in os.listdir(domain_dir)
                  if os.path.isdir(os.path.join(domain_dir, d)) and os.path.exists(os.path.join(domain_dir, d, "faq.yaml")))


def _walk(root: str) -> list[str]:
    out = []
    for base, _dirs, files in os.walk(root):
        for f in files:
            out.append(os.path.relpath(os.path.join(base, f), root).replace(os.sep, "/"))
    return sorted(out)


def _bump_bot(bot: Bot) -> None:
    bot.draft_revision += 1


def import_domain(session: Session, domains_root: str, slug: str, replace: bool = False,
                  user_id: str | None = None) -> dict:
    domain_dir = os.path.join(domains_root, slug)
    if not os.path.isdir(domain_dir):
        raise ImportError_(f"no such domain directory: {slug}")
    domain = session.scalar(select(Domain).where(Domain.slug == slug))
    if domain is not None and not replace:
        raise FileExistsError(slug)
    if domain is None:
        domain = Domain(slug=slug, title=slug)
        session.add(domain)
        session.flush()
    else:   # replace the draft only: bots, layout and publications stay
        for model in (Tool, DomainSetting, DomainFile):
            session.execute(delete(model).where(model.domain_id == domain.id))
        domain.shared_revision += 1
    summary: dict = {"domain": slug, "shared": {"modelled": [], "raw": []}, "bots": []}
    claimed: set[str] = set()

    # shared assets
    tools_path = os.path.join(domain_dir, "tools.yaml")
    if os.path.exists(tools_path):
        spec = yamlio.load(_read(tools_path)) or {}
        extra_keys = set(spec) - {"tools"}
        if extra_keys:
            raise ImportError_(f"{slug}/tools.yaml: unexpected top-level keys {sorted(extra_keys)}")
        for pos, (name, body) in enumerate((spec.get("tools") or {}).items()):
            session.add(Tool(domain_id=domain.id, name=name, position=pos, body=body, updated_by=user_id))
        claimed.add("tools.yaml")
        summary["shared"]["modelled"].append("tools.yaml")
    for kind, rel in SHARED_SETTINGS.items():
        p = os.path.join(domain_dir, rel)
        if os.path.exists(p):
            session.add(DomainSetting(domain_id=domain.id, kind=kind, body=yamlio.load(_read(p)), updated_by=user_id))
            claimed.add(rel)
            summary["shared"]["modelled"].append(rel)

    langs = _language_dirs(domain_dir)
    for lang in langs:
        bot = session.scalar(select(Bot).where(Bot.domain_id == domain.id, Bot.lang == lang))
        if bot is None:
            bot = Bot(domain_id=domain.id, lang=lang, slug=f"{slug}-{lang}", title=f"{slug} ({lang})")
            session.add(bot)
            session.flush()
        else:
            for model in (FaqEntry, Flow, DomainSetting, DomainFile):
                session.execute(delete(model).where(model.bot_id == bot.id))
            _bump_bot(bot)
        info = _import_bot(session, bot, os.path.join(domain_dir, lang), user_id)
        summary["bots"].append({"slug": bot.slug, "lang": lang, **info})
        claimed.update(f"{lang}/{r}" for r in info["modelled"] + info["raw"])
    # everything else in the domain directory is kept raw at the domain level
    for rel in _walk(domain_dir):
        if rel in claimed or any(rel.startswith(f"{l}/") for l in langs):
            continue
        try:
            text = _read(os.path.join(domain_dir, rel))
        except UnicodeDecodeError:
            continue
        session.add(DomainFile(domain_id=domain.id, path=rel, content=text, updated_by=user_id))
        summary["shared"]["raw"].append(rel)
    session.flush()
    return summary


def _import_bot(session: Session, bot: Bot, lang_dir: str, user_id: str | None) -> dict:
    modelled: list[str] = []
    faq = yamlio.load(_read(os.path.join(lang_dir, "faq.yaml"))) or {}
    patterns: dict = {}
    pat_order: dict = {}
    pat_path = os.path.join(lang_dir, "rules", "faq_patterns.yaml")
    if os.path.exists(pat_path):
        for i, e in enumerate((yamlio.load(_read(pat_path)) or {}).get("entries") or []):
            e = dict(e)
            eid = e.pop("id")
            patterns[eid] = e
            pat_order[eid] = i
        modelled.append("rules/faq_patterns.yaml")
    for pos, e in enumerate(faq.get("entries") or []):
        session.add(FaqEntry(bot_id=bot.id, entry_id=e["id"], position=pos, question=e["question"], answer=e["answer"],
                             paraphrases=e.get("paraphrases"), asr_variants=e.get("asr_variants"),
                             pattern=patterns.get(e["id"]), pattern_position=pat_order.get(e["id"]),
                             updated_by=user_id))
    modelled.append("faq.yaml")
    flows_dir = os.path.join(lang_dir, "flows")
    if os.path.isdir(flows_dir):
        for name in sorted(os.listdir(flows_dir)):
            if not name.endswith(".yaml"):
                continue
            raw = yamlio.load(_read(os.path.join(flows_dir, name))) or {}
            fid = name[:-5]
            nodes = raw.get("nodes") or {}
            header = {k: v for k, v in raw.items() if k not in ("id", "start", "nodes")}
            session.add(Flow(bot_id=bot.id, flow_id=fid, header=header, start=raw.get("start"), nodes=nodes,
                             node_order=list(nodes), updated_by=user_id))
            modelled.append(f"flows/{name}")
    for kind, rel in BOT_SETTINGS.items():
        p = os.path.join(lang_dir, rel)
        if os.path.exists(p):
            session.add(DomainSetting(bot_id=bot.id, kind=kind, body=yamlio.load(_read(p)), updated_by=user_id))
            modelled.append(rel)
    raw_files: list[str] = []
    for rel in _walk(lang_dir):
        if rel in modelled:
            continue
        try:
            text = _read(os.path.join(lang_dir, rel))
        except UnicodeDecodeError:
            continue
        session.add(DomainFile(bot_id=bot.id, path=rel, content=text, updated_by=user_id))
        raw_files.append(rel)
    return {"modelled": modelled, "raw": raw_files}


# --- export ---

def _flow_doc(flow: Flow) -> dict:
    doc: dict = {"id": flow.flow_id}
    for key in FLOW_HEADER_ORDER:
        if key in flow.header:
            doc[key] = flow.header[key]
    for key in sorted(set(flow.header) - set(FLOW_HEADER_ORDER)):
        doc[key] = flow.header[key]
    if flow.start is not None:
        doc["start"] = flow.start
    order = [n for n in flow.node_order if n in flow.nodes] + [n for n in flow.nodes if n not in flow.node_order]
    doc["nodes"] = {n: flow.nodes[n] for n in order}
    return doc


def export_bot(session: Session, bot: Bot) -> dict[str, str]:
    """All files of a bot's `domains_dir`, as {relative path: text}. Draft content, not a publication."""
    domain = session.get(Domain, bot.domain_id)
    d, lang = domain.slug, bot.lang
    files: dict[str, str] = {}
    tools = session.scalars(select(Tool).where(Tool.domain_id == domain.id).order_by(Tool.position)).all()
    # always written: the loader and the fake API open it even when a new domain has no API yet
    files[f"{d}/tools.yaml"] = yamlio.dump({"tools": {t.name: t.body for t in tools}})
    for s in session.scalars(select(DomainSetting).where(DomainSetting.domain_id == domain.id)):
        files[f"{d}/{SHARED_SETTINGS[s.kind]}"] = yamlio.dump(s.body)
    for f in session.scalars(select(DomainFile).where(DomainFile.domain_id == domain.id)):
        files[f"{d}/{f.path}"] = f.content
    # language directory
    entries = session.scalars(select(FaqEntry).where(FaqEntry.bot_id == bot.id).order_by(FaqEntry.position)).all()
    faq_entries, pats = [], []
    for e in entries:
        item = {"id": e.entry_id, "question": e.question, "answer": e.answer}
        if e.paraphrases is not None:
            item["paraphrases"] = e.paraphrases
        if e.asr_variants is not None:
            item["asr_variants"] = e.asr_variants
        faq_entries.append(item)
        if e.pattern is not None:
            pats.append((e.pattern_position if e.pattern_position is not None else 10**9 + e.position,
                         {"id": e.entry_id, **e.pattern}))
    files[f"{d}/{lang}/faq.yaml"] = yamlio.dump({"lang": lang, "entries": faq_entries})
    if pats:
        files[f"{d}/{lang}/rules/faq_patterns.yaml"] = yamlio.dump({"entries": [p for _, p in sorted(pats, key=lambda x: x[0])]})
    for flow in session.scalars(select(Flow).where(Flow.bot_id == bot.id).order_by(Flow.flow_id)):
        files[f"{d}/{lang}/flows/{flow.flow_id}.yaml"] = yamlio.dump(_flow_doc(flow))
    for s in session.scalars(select(DomainSetting).where(DomainSetting.bot_id == bot.id)):
        files[f"{d}/{lang}/{BOT_SETTINGS[s.kind]}"] = yamlio.dump(s.body)
    for f in session.scalars(select(DomainFile).where(DomainFile.bot_id == bot.id)):
        files[f"{d}/{lang}/{f.path}"] = f.content
    return files


def prune_layout(session: Session, bot: Bot, flow_id: str, node_ids: set[str]) -> None:
    """Layout rows of nodes that no longer exist are dropped."""
    for row in session.scalars(select(FlowNodeLayout).where(FlowNodeLayout.bot_id == bot.id,
                                                            FlowNodeLayout.flow_id == flow_id)):
        if row.node_id not in node_ids:
            session.delete(row)
