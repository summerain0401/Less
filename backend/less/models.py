from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from less.db import Base


class Brief(Base):
    __tablename__ = "briefs"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    published_at: Mapped[str | None] = mapped_column(String(40))
    what_happened: Mapped[str] = mapped_column(Text)
    why_it_matters: Mapped[str] = mapped_column(Text)
    our_take: Mapped[str | None] = mapped_column(Text)
    important: Mapped[bool] = mapped_column(Boolean)
    useful: Mapped[bool] = mapped_column(Boolean)
    confidence: Mapped[str] = mapped_column(String(10))
    uncertainty: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(32), index=True)
    updated_at: Mapped[str | None] = mapped_column(String(32))

    source_links: Mapped[list["BriefSource"]] = relationship(
        back_populates="brief", cascade="all, delete-orphan", order_by="BriefSource.position"
    )
    topic_links: Mapped[list["BriefTopic"]] = relationship(
        back_populates="brief", cascade="all, delete-orphan", order_by="BriefTopic.position"
    )


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(Text, unique=True)
    type: Mapped[str] = mapped_column(String(40))
    published_at: Mapped[str | None] = mapped_column(String(40))

    brief_links: Mapped[list["BriefSource"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )


class BriefSource(Base):
    __tablename__ = "brief_sources"

    brief_id: Mapped[str] = mapped_column(
        ForeignKey("briefs.id", ondelete="CASCADE"), primary_key=True
    )
    source_id: Mapped[str] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int]
    primary: Mapped[bool] = mapped_column(Boolean)

    brief: Mapped[Brief] = relationship(back_populates="source_links")
    source: Mapped[Source] = relationship(back_populates="brief_links")


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)

    brief_links: Mapped[list["BriefTopic"]] = relationship(
        back_populates="topic", cascade="all, delete-orphan"
    )


class BriefTopic(Base):
    __tablename__ = "brief_topics"

    brief_id: Mapped[str] = mapped_column(
        ForeignKey("briefs.id", ondelete="CASCADE"), primary_key=True
    )
    topic_id: Mapped[str] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int]

    brief: Mapped[Brief] = relationship(back_populates="topic_links")
    topic: Mapped[Topic] = relationship(back_populates="brief_links")


class DigestRun(Base):
    __tablename__ = "digest_runs"

    day: Mapped[str] = mapped_column(String(10), primary_key=True)
    slot: Mapped[str] = mapped_column(String(10), primary_key=True)
    status: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[str] = mapped_column(String(40))
    finished_at: Mapped[str | None] = mapped_column(String(40))
    brief_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    email_sent_at: Mapped[str | None] = mapped_column(String(40))
    error: Mapped[str | None] = mapped_column(Text)
