from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(AsyncAttrs, DeclarativeBase):
    pass


class Agent(Base):
    __tablename__ = "agents"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    tags: Mapped[str] = mapped_column(String, default="")
    enrolled_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    jobs: Mapped[list[Job]] = relationship(back_populates="agent")


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"))
    action: Mapped[str] = mapped_column(String)
    params: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String, default="queued", index=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    agent: Mapped[Agent] = relationship(back_populates="jobs")


def make_engine(path: str) -> AsyncEngine:
    url = f"sqlite+aiosqlite:///{path}"
    return create_async_engine(url, echo=False)


def make_session(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def init_db(path: str) -> async_sessionmaker[AsyncSession]:
    engine = make_engine(path)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return make_session(engine)
