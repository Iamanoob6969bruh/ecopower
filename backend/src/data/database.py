from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, JSON
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
import os

# Unify the database path for both API and Scrapers
DB_PATH = os.environ.get("DB_PATH", "sqlite:///./data/karnataka_solar.db")

engine = create_engine(
    DB_PATH,
    # timeout: wait up to 30s for the write lock instead of failing immediately;
    # the scheduler, scraper, and API all write this one SQLite file.
    connect_args={"check_same_thread": False, "timeout": 30},
)

# Enable WAL for concurrent readers/writer + a busy timeout, on every connection.
if DB_PATH.startswith("sqlite"):
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _rec):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class GenerationData(Base):
    __tablename__ = "generation_data"

    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(String, index=True)
    timestamp = Column(DateTime, index=True)
    actual_kw = Column(Float, nullable=True)
    predicted_kw = Column(Float, nullable=True)
    zone_label = Column(String)  # 'zone1', 'zone2', 'zone3'
    reasons = Column(String, nullable=True)
    weather_data = Column(JSON, nullable=True)

class WeatherDataCache(Base):
    __tablename__ = "weather_cache"

    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(String, index=True)
    timestamp = Column(DateTime, index=True)
    weather_json = Column(JSON)

def init_db():
    Base.metadata.create_all(bind=engine)

    # Manual migration for an OLD pre-existing SQLite DB missing newer columns.
    # create_all builds the full schema for fresh DBs, so this only matters for a
    # legacy file. Derive the real path from DB_PATH (previously hard-coded to a
    # non-existent "./dashboard.db", so the migration never ran).
    import sqlite3
    db_file = DB_PATH.replace("sqlite:///", "") if DB_PATH.startswith("sqlite:///") else None
    if db_file and os.path.exists(db_file):
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        
        # Check if columns exist
        cursor.execute("PRAGMA table_info(generation_data)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'reasons' not in columns:
            print("Adding 'reasons' column to generation_data table...")
            cursor.execute("ALTER TABLE generation_data ADD COLUMN reasons TEXT")
            
        if 'weather_data' not in columns:
            print("Adding 'weather_data' column to generation_data table...")
            cursor.execute("ALTER TABLE generation_data ADD COLUMN weather_data JSON")
            
        conn.commit()
        conn.close()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_now_ist():
    """Returns the current time in Asia/Kolkata as a naive datetime object."""
    import pytz
    kolkata = pytz.timezone('Asia/Kolkata')
    return datetime.now(kolkata).replace(tzinfo=None)

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
