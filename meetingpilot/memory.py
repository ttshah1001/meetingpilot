"""Memory layer: persist meetings + action items in SQLite."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session

from meetingpilot.config import get_settings
from meetingpilot.models import ItemSource, OpenMemoryItem, PlannedItem, Priority


class Base(DeclarativeBase):
    pass


class MeetingRecord(Base):
    __tablename__ = "meetings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255))
    meeting_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    source_name: Mapped[str] = mapped_column(String(255))
    transcript: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    items: Mapped[list["ActionItemRecord"]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan"
    )


class ActionItemRecord(Base):
    __tablename__ = "action_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"))
    task: Mapped[str] = mapped_column(Text)
    owner: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    due_date_iso: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    priority: Mapped[str] = mapped_column(String(16), default="medium")
    source_quote: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32), default="open")
    calendar_event_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    planning_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="transcript")

    meeting: Mapped[MeetingRecord] = relationship(back_populates="items")


def get_engine(db_path: Optional[str] = None):
    path = db_path or str(get_settings().db_path)
    return create_engine(f"sqlite:///{path}", echo=False)


def init_db(db_path: Optional[str] = None) -> None:
    engine = get_engine(db_path)
    Base.metadata.create_all(engine)


def _session(db_path: Optional[str] = None) -> Session:
    init_db(db_path)
    return Session(get_engine(db_path))


def save_meeting(
    *,
    title: str,
    meeting_date: date,
    source_name: str,
    transcript: str,
    items: list[PlannedItem],
    db_path: Optional[str] = None,
) -> int:
    """Persist a processed meeting and its planned action items. Returns meeting id."""
    with _session(db_path) as session:
        meeting = MeetingRecord(
            title=title,
            meeting_date=meeting_date,
            source_name=source_name,
            transcript=transcript,
        )
        for item in items:
            meeting.items.append(
                ActionItemRecord(
                    task=item.task,
                    owner=item.owner or item.proposed_owner,
                    due_date_iso=item.due_date_iso or item.proposed_due_date_iso,
                    priority=item.priority.value,
                    source_quote=item.source_quote,
                    confidence=item.confidence,
                    status="open",
                    planning_notes=item.planning_notes,
                    source=item.source.value,
                )
            )
        session.add(meeting)
        session.commit()
        session.refresh(meeting)
        return meeting.id


def list_open_items(
    *,
    owner: Optional[str] = None,
    exclude_meeting_id: Optional[int] = None,
    db_path: Optional[str] = None,
) -> list[OpenMemoryItem]:
    with _session(db_path) as session:
        stmt = (
            select(ActionItemRecord, MeetingRecord)
            .join(MeetingRecord, ActionItemRecord.meeting_id == MeetingRecord.id)
            .where(ActionItemRecord.status == "open")
        )
        if owner:
            stmt = stmt.where(ActionItemRecord.owner == owner)
        if exclude_meeting_id is not None:
            stmt = stmt.where(ActionItemRecord.meeting_id != exclude_meeting_id)
        rows = session.execute(stmt).all()
        results: list[OpenMemoryItem] = []
        for item, meeting in rows:
            results.append(
                OpenMemoryItem(
                    id=item.id,
                    meeting_id=meeting.id,
                    meeting_title=meeting.title,
                    meeting_date=meeting.meeting_date,
                    task=item.task,
                    owner=item.owner,
                    due_date_iso=item.due_date_iso,
                    priority=Priority(item.priority),
                    status=item.status,
                )
            )
        return results


def list_open_for_owners(
    owners: list[str],
    *,
    exclude_meeting_id: Optional[int] = None,
    db_path: Optional[str] = None,
) -> list[OpenMemoryItem]:
    cleaned = [o for o in owners if o]
    if not cleaned:
        return list_open_items(exclude_meeting_id=exclude_meeting_id, db_path=db_path)
    found: list[OpenMemoryItem] = []
    seen: set[int] = set()
    for owner in cleaned:
        for row in list_open_items(
            owner=owner, exclude_meeting_id=exclude_meeting_id, db_path=db_path
        ):
            if row.id not in seen:
                seen.add(row.id)
                found.append(row)
    return found


def mark_calendar_pushed(
    item_id: int, event_id: str, *, db_path: Optional[str] = None
) -> None:
    with _session(db_path) as session:
        item = session.get(ActionItemRecord, item_id)
        if item is None:
            raise KeyError(f"No action item with id={item_id}")
        item.calendar_event_id = event_id
        item.status = "scheduled"
        session.commit()


def get_item(item_id: int, *, db_path: Optional[str] = None) -> Optional[ActionItemRecord]:
    with _session(db_path) as session:
        return session.get(ActionItemRecord, item_id)


def list_items_for_meeting(meeting_id: int, *, db_path: Optional[str] = None) -> list[ActionItemRecord]:
    with _session(db_path) as session:
        stmt = select(ActionItemRecord).where(ActionItemRecord.meeting_id == meeting_id)
        return list(session.scalars(stmt).all())


def clear_all_data(*, db_path: Optional[str] = None) -> None:
    """Delete every stored meeting and action item (used by the UI's clear-cache action)."""
    with _session(db_path) as session:
        session.query(ActionItemRecord).delete()
        session.query(MeetingRecord).delete()
        session.commit()
