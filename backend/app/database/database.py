"""Database connection and initialization."""
import logging
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

from .models import Base

logger = logging.getLogger(__name__)

# Get project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"

# Ensure data directory exists
DATA_DIR.mkdir(exist_ok=True)

# Default database path
DEFAULT_DB_PATH = DATA_DIR / "ema_bot.db"
DEFAULT_DB_URL = f"sqlite+aiosqlite:///{DEFAULT_DB_PATH}"


class Database:
    """Database manager for async SQLite."""

    def __init__(self, database_url: str = None):
        self.database_url = database_url or DEFAULT_DB_URL
        self.engine = create_async_engine(
            self.database_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=False,
        )
        self.async_session = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def init_db(self):
        """Initialize database tables."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database initialized")

    async def get_session(self) -> AsyncSession:
        """Get async database session."""
        async with self.async_session() as session:
            yield session

    async def close(self):
        """Close database connections."""
        await self.engine.dispose()
        logger.info("Database connections closed")


# Global database instance
_database: Database = None


def get_database(database_url: str = None) -> Database:
    """Get or create global database instance."""
    global _database
    if _database is None:
        _database = Database(database_url)
    return _database
