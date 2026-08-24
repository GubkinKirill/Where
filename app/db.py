from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _lower(value):
    """SQLite's own lower() folds ASCII only, so «Петров» would not match «петров».
    Every ILIKE in the app compiles to lower() LIKE lower(), so replacing the
    function makes search case-insensitive in Russian too."""
    return value.lower() if isinstance(value, str) else value


@event.listens_for(Engine, "connect")
def _sqlite_pragmas(dbapi_connection, connection_record) -> None:
    """SQLite ignores foreign keys unless asked; WAL keeps readers unblocked."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()
    dbapi_connection.create_function("lower", 1, _lower, deterministic=True)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
