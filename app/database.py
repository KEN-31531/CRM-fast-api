from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from pathlib import Path
import os

# 預設使用 PostgreSQL
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://ken@localhost:5432/crm"
)

engine = create_async_engine(DATABASE_URL, echo=False)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        yield session


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
