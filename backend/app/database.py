import logging
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker
from backend.app.core.config import settings

logger = logging.getLogger("dairy_erp")

# Attempt PostgreSQL connection, fall back cleanly if unavailable
engine = None
if settings.DATABASE_URL.startswith("sqlite"):
    engine = create_engine(settings.DATABASE_URL, connect_args={"check_same_thread": False})
try:
    if engine is None and "postgresql" in settings.DATABASE_URL:
        # Check quick connection
        test_engine = create_engine(
            settings.DATABASE_URL,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 3}
        )
        with test_engine.connect() as conn:
            pass
        engine = test_engine
        logger.info("Connected successfully to PostgreSQL database.")
except Exception as e:
    logger.warning(
        f"PostgreSQL connection failed ({e}). Using local high-performance SQLite database: {settings.SQLITE_FALLBACK_URL}"
    )

if engine is None:
    engine = create_engine(
        settings.SQLITE_FALLBACK_URL,
        connect_args={"check_same_thread": False}
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def add_missing_columns():
    """create_all() only creates new tables; add any new model columns to existing tables."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            present = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name not in present:
                    col_type = column.type.compile(dialect=engine.dialect)
                    conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {column.name} {col_type}'))
                    logger.info(f"Added column {table.name}.{column.name}")
