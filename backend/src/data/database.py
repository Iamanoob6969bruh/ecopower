from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, JSON
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
import os

DB_PATH = os.environ.get("DB_PATH", "sqlite:///./dashboard.db")

engine = create_engine(DB_PATH, connect_args={"check_same_thread": False})
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
    
    # Manual migration for SQLite as it doesn't support ALTER TABLE ... ADD COLUMN easily with Base.metadata.create_all
    import sqlite3
    db_file = "./dashboard.db"
    if os.path.exists(db_file):
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
    """Returns the current datetime in Asia/Kolkata (naive)."""
    import pytz
    kolkata = pytz.timezone('Asia/Kolkata')
    return datetime.now(kolkata).replace(tzinfo=None)

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
