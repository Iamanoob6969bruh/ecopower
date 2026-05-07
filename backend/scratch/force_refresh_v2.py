import sys
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from src.data.database import init_db, SessionLocal, GenerationData
from src.jobs.scheduler import run_15min_job
from sqlalchemy import delete

def force_refresh():
    logger.info("Initializing database schema...")
    init_db()
    
    logger.info("Cleaning up old stale data for today/tomorrow...")
    db = SessionLocal()
    try:
        # Clear zone2 and zone3 to force fresh population
        db.execute(delete(GenerationData).where(GenerationData.zone_label.in_(["zone2", "zone3"])))
        db.commit()
        logger.info("Cleanup complete.")
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        db.rollback()
    finally:
        db.close()
        
    logger.info("Triggering 15-minute job to populate fresh predictions...")
    run_15min_job()
    logger.info("Force refresh complete. Your dashboard should now show corrected AI curves.")

if __name__ == "__main__":
    force_refresh()
