"""Tables of docs/studio/data-model.md that ST1 needs. Meaning and layout live in separate tables (ADR 0013)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (JSON, Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

Json = JSON().with_variant(JSONB(), "postgresql")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Stamped:
    """created_at, updated_at, updated_by and the revision used for optimistic concurrency."""
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    updated_by: Mapped[str | None] = mapped_column(String(36), nullable=True)


# --- identity and access (slots, not enforced in v1) ---

class User(Base):
    __tablename__ = "user"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    display_name: Mapped[str] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Role(Base):
    __tablename__ = "role"
    name: Mapped[str] = mapped_column(String(40), primary_key=True)


class UserRole(Base):
    __tablename__ = "user_role"
    user_id: Mapped[str] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), primary_key=True)
    role_name: Mapped[str] = mapped_column(ForeignKey("role.name", ondelete="CASCADE"), primary_key=True)


# --- domains and bots ---

class Domain(Base):
    __tablename__ = "domain"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    shared_revision: Mapped[int] = mapped_column(Integer, default=1)
    bots: Mapped[list["Bot"]] = relationship(back_populates="domain", cascade="all, delete-orphan")


class Bot(Base):
    __tablename__ = "bot"
    __table_args__ = (UniqueConstraint("domain_id", "lang"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    domain_id: Mapped[str] = mapped_column(ForeignKey("domain.id", ondelete="CASCADE"))
    lang: Mapped[str] = mapped_column(String(8))
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    draft_revision: Mapped[int] = mapped_column(Integer, default=1)
    last_validated_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_validated_shared_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_validation_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_published_number: Mapped[int] = mapped_column(Integer, default=0)
    # draft_revision / shared_revision at the last publication, to tell "unpublished changes"
    published_draft_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    published_shared_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    domain: Mapped[Domain] = relationship(back_populates="bots")


# --- content (draft) ---

class FaqEntry(Stamped, Base):
    __tablename__ = "faq_entry"
    __table_args__ = (UniqueConstraint("bot_id", "entry_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    bot_id: Mapped[str] = mapped_column(ForeignKey("bot.id", ondelete="CASCADE"))
    entry_id: Mapped[str] = mapped_column(String(200))
    position: Mapped[int] = mapped_column(Integer)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    paraphrases: Mapped[list | None] = mapped_column(Json, nullable=True)
    asr_variants: Mapped[list | None] = mapped_column(Json, nullable=True)
    pattern: Mapped[dict | None] = mapped_column(Json, nullable=True)
    pattern_position: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Tool(Stamped, Base):
    __tablename__ = "tool"
    __table_args__ = (UniqueConstraint("domain_id", "name"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    domain_id: Mapped[str] = mapped_column(ForeignKey("domain.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    position: Mapped[int] = mapped_column(Integer)
    body: Mapped[dict | None] = mapped_column(Json, nullable=True)


class Flow(Stamped, Base):
    __tablename__ = "flow"
    __table_args__ = (UniqueConstraint("bot_id", "flow_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    bot_id: Mapped[str] = mapped_column(ForeignKey("bot.id", ondelete="CASCADE"))
    flow_id: Mapped[str] = mapped_column(String(200))
    header: Mapped[dict] = mapped_column(Json, default=dict)
    start: Mapped[str | None] = mapped_column(String(200), nullable=True)
    nodes: Mapped[dict] = mapped_column(Json, default=dict)
    node_order: Mapped[list] = mapped_column(Json, default=list)


class DomainSetting(Stamped, Base):
    """Parsed YAML of a settings file. Shared kinds hang on the domain, the others on a bot."""
    __tablename__ = "domain_setting"
    __table_args__ = (CheckConstraint("(domain_id IS NULL) <> (bot_id IS NULL)"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    domain_id: Mapped[str | None] = mapped_column(ForeignKey("domain.id", ondelete="CASCADE"), nullable=True)
    bot_id: Mapped[str | None] = mapped_column(ForeignKey("bot.id", ondelete="CASCADE"), nullable=True)
    kind: Mapped[str] = mapped_column(String(60))
    body: Mapped[dict | list | None] = mapped_column(Json, nullable=True)


class DomainFile(Stamped, Base):
    """A file the studio does not model yet: stored as text, exported unchanged."""
    __tablename__ = "domain_file"
    __table_args__ = (CheckConstraint("(domain_id IS NULL) <> (bot_id IS NULL)"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    domain_id: Mapped[str | None] = mapped_column(ForeignKey("domain.id", ondelete="CASCADE"), nullable=True)
    bot_id: Mapped[str | None] = mapped_column(ForeignKey("bot.id", ondelete="CASCADE"), nullable=True)
    path: Mapped[str] = mapped_column(String(400))
    content: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(String(60), default="text/yaml")


# --- layout (never exported, never versioned) ---

class FlowLayout(Base):
    __tablename__ = "flow_layout"
    bot_id: Mapped[str] = mapped_column(ForeignKey("bot.id", ondelete="CASCADE"), primary_key=True)
    flow_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    viewport: Mapped[dict | None] = mapped_column(Json, nullable=True)
    direction: Mapped[str] = mapped_column(String(2), default="LR")
    saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    saved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)


class FlowNodeLayout(Base):
    __tablename__ = "flow_node_layout"
    bot_id: Mapped[str] = mapped_column(ForeignKey("bot.id", ondelete="CASCADE"), primary_key=True)
    flow_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    node_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    x: Mapped[float] = mapped_column(Float)
    y: Mapped[float] = mapped_column(Float)
    collapsed: Mapped[bool] = mapped_column(Boolean, default=False)


# --- publications ---

class Publication(Base):
    __tablename__ = "publication"
    __table_args__ = (UniqueConstraint("bot_id", "number"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    bot_id: Mapped[str] = mapped_column(ForeignKey("bot.id", ondelete="CASCADE"))
    number: Mapped[int] = mapped_column(Integer)
    shared_revision: Mapped[int] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(20), default="publish")
    restored_from_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    validation: Mapped[dict | None] = mapped_column(Json, nullable=True)
    published_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PublicationFile(Base):
    __tablename__ = "publication_file"
    publication_id: Mapped[str] = mapped_column(ForeignKey("publication.id", ondelete="CASCADE"), primary_key=True)
    path: Mapped[str] = mapped_column(String(400), primary_key=True)
    content: Mapped[str] = mapped_column(Text)
