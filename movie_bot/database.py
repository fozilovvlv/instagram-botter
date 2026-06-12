from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import DateTime, Integer, String, create_engine, delete, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class MovieRecord(Base):
    __tablename__ = "movies"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    message_id: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


@dataclass(frozen=True)
class Movie:
    code: str
    message_id: int
    title: str | None


class MovieRepository:
    def __init__(self, database_url: str) -> None:
        if database_url.startswith("sqlite:///"):
            path = Path(database_url.removeprefix("sqlite:///"))
            path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(database_url, pool_pre_ping=True)
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def initialize(self) -> None:
        Base.metadata.create_all(self.engine)

    def upsert(self, code: str, message_id: int, title: str | None = None) -> None:
        with self.sessions.begin() as session:
            record = session.get(MovieRecord, code)
            if record:
                record.message_id = message_id
                record.title = title
            else:
                session.add(MovieRecord(code=code, message_id=message_id, title=title))

    def get(self, code: str) -> Movie | None:
        with self.sessions() as session:
            record = session.get(MovieRecord, code)
            if not record:
                return None
            return Movie(record.code, record.message_id, record.title)

    def delete(self, code: str) -> bool:
        with self.sessions.begin() as session:
            result = session.execute(delete(MovieRecord).where(MovieRecord.code == code))
            return bool(result.rowcount)

    def count(self) -> int:
        with self.sessions() as session:
            return int(session.scalar(select(func.count()).select_from(MovieRecord)) or 0)

    def record_request(self, code: str) -> None:
        with self.sessions.begin() as session:
            record = session.get(MovieRecord, code)
            if record:
                record.request_count += 1

    def total_requests(self) -> int:
        with self.sessions() as session:
            return int(session.scalar(select(func.sum(MovieRecord.request_count))) or 0)

    def close(self) -> None:
        self.engine.dispose()
