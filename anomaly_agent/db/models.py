"""The database tables, written as Python classes (SQLAlchemy ORM).

users    - one row per registered person (the password is stored only as a bcrypt hash)
analyses - one row per analysis a user chose to save; every row belongs to exactly one user
"""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow():
    """Current time in UTC, without a time-zone tag (the same everywhere, SQLite and PostgreSQL)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    analyses: Mapped[list["Analysis"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    alert_rules: Mapped[list["AlertRule"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    alert_events: Mapped[list["AlertEvent"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    ai_calls: Mapped[list["AiCall"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    source_name: Mapped[str] = mapped_column(String(255))
    period: Mapped[str] = mapped_column(String(20))
    row_count: Mapped[int] = mapped_column(Integer)
    anomaly_count: Mapped[int] = mapped_column(Integer)
    high_count: Mapped[int] = mapped_column(Integer)
    anomalies_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    user: Mapped[User] = relationship(back_populates="analyses")


class AlertRule(Base):
    """One alert rule written by a user: "tell me when <metric> has a <severity> anomaly ..."."""

    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    metric: Mapped[str | None] = mapped_column(String(100), nullable=True)  # None = any metric
    min_severity: Mapped[str] = mapped_column(String(6))
    min_votes: Mapped[int] = mapped_column(Integer, default=1)
    direction: Mapped[str] = mapped_column(String(4), default="any")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    user: Mapped[User] = relationship(back_populates="alert_rules")


class AlertEvent(Base):
    """One alert that a rule produced. The same alert is never stored twice (see the unique constraint)."""

    __tablename__ = "alert_events"
    __table_args__ = (
        UniqueConstraint("user_id", "rule_id", "source_name", "period_key", "metric", name="one_alert_each"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # The alert stays in the history even after its rule is deleted, so rule_id may become empty.
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("alert_rules.id", ondelete="SET NULL"), nullable=True)
    rule_name: Mapped[str] = mapped_column(String(60))
    source_name: Mapped[str] = mapped_column(String(255))
    period_key: Mapped[str] = mapped_column(String(10))   # 2026-10-01, used to compare
    period_label: Mapped[str] = mapped_column(String(20))  # Oct 2026, shown to people
    metric: Mapped[str] = mapped_column(String(100))
    severity: Mapped[str] = mapped_column(String(6))
    direction: Mapped[str] = mapped_column(String(4))
    votes: Mapped[int] = mapped_column(Integer)
    methods_run: Mapped[int] = mapped_column(Integer)
    actual: Mapped[float] = mapped_column(Float)
    expected: Mapped[float | None] = mapped_column(Float, nullable=True)
    message: Mapped[str] = mapped_column(Text)
    emailed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    user: Mapped[User] = relationship(back_populates="alert_events")


class AiCall(Base):
    """One request the user made to Gemini. Counting these per hour gives the rate limit."""

    __tablename__ = "ai_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10))  # "question" or "insight"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    user: Mapped[User] = relationship(back_populates="ai_calls")
