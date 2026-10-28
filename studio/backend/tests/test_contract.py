"""The contract of ADR 0012/0013: import `domains/`, export every bot, compare parsed content with the source, and let
the engine's own loader accept the export."""

import os

import yaml
from sqlalchemy import select

from studio_backend.models import Bot
from studio_backend.portable import export_bot, import_domain
from studio_backend.validation import validate_files

from conftest import DOMAINS


def _source_files(domain: str, lang: str) -> dict[str, str]:
    """Files of the source tree that belong to one bot: the domain-level files and that language directory."""
    out = {}
    base = DOMAINS / domain
    for p in sorted(base.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(base).as_posix()
        first = rel.split("/")[0]
        if "/" in rel and first != lang and (base / first).is_dir() and (base / first / "faq.yaml").exists():
            continue    # another language's file
        out[f"{domain}/{rel}"] = p.read_text(encoding="utf-8")
    return out


def _parsed(path: str, text: str):
    return yaml.safe_load(text) if path.endswith((".yaml", ".yml")) else text


def test_import_gives_domains_and_bots(session):
    for d in ("bank", "shop", "telecom"):
        import_domain(session, str(DOMAINS), d)
    session.commit()
    bots = session.scalars(select(Bot).order_by(Bot.slug)).all()
    assert [b.slug for b in bots] == ["bank-en", "bank-ko", "shop-en", "shop-ko", "telecom-en", "telecom-ko"]


def test_round_trip_is_parsed_equal_and_loads(session):
    for d in ("bank", "shop", "telecom"):
        import_domain(session, str(DOMAINS), d)
    session.commit()
    for bot in session.scalars(select(Bot)).all():
        domain = bot.domain.slug
        exported = export_bot(session, bot)
        source = _source_files(domain, bot.lang)
        assert set(exported) == set(source), (bot.slug, set(exported) ^ set(source))
        for path, text in source.items():
            assert _parsed(path, exported[path]) == _parsed(path, text), (bot.slug, path)
        assert validate_files(exported, domain, bot.lang) == [], bot.slug


def test_validation_reports_engine_errors_with_flow_and_node(session):
    import_domain(session, str(DOMAINS), "bank")
    session.commit()
    bot = session.scalar(select(Bot).where(Bot.slug == "bank-en"))
    files = export_bot(session, bot)
    files["bank/en/flows/transfer.yaml"] = files["bank/en/flows/transfer.yaml"].replace("next: ask_to", "next: nowhere", 1)
    items = validate_files(files, "bank", "en")
    assert len(items) == 1
    assert items[0]["flow_id"] == "transfer" and items[0]["node_id"] == "ask_amount"
    assert "nowhere" in items[0]["message"]
    files = export_bot(session, bot)
    files["bank/tools.yaml"] = files["bank/tools.yaml"].replace("retry: 1", "retry: 5", 1)
    items = validate_files(files, "bank", "en")
    assert items and items[0]["file"] == "bank/tools.yaml"
