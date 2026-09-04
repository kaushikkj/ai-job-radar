from pathlib import Path
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base,sessionmaker
from .config import settings
if settings.database_url.startswith("sqlite:///"):
    Path(settings.database_url.replace("sqlite:///","",1)).parent.mkdir(parents=True,exist_ok=True)
engine=create_engine(settings.database_url,connect_args={"check_same_thread":False} if settings.database_url.startswith("sqlite") else {})
SessionLocal=sessionmaker(bind=engine,autoflush=False,autocommit=False)
Base=declarative_base()

def migrate():
    """Apply tiny SQLite-compatible additive migrations for local V2/V3 upgrades."""
    if not settings.database_url.startswith("sqlite"):
        return
    inspector = inspect(engine)
    if "jobs" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("jobs")}
    with engine.begin() as conn:
        if "posted_at_source" not in columns:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN posted_at_source VARCHAR(120) DEFAULT ''"))

def get_db():
    db=SessionLocal()
    try: yield db
    finally: db.close()
