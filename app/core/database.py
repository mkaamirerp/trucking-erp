from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings
from app.core.db_url import to_async_pg_url

# Canonical async engine (DO NOT change elsewhere)
engine = create_async_engine(
    to_async_pg_url(settings.database_url),
    pool_pre_ping=True,
)

# Canonical async session factory
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

Base = declarative_base()

# Canonical DB dependency for FastAPI
async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
