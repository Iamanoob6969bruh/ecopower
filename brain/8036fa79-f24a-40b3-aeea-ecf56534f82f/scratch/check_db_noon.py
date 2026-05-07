import os
import sys
import pandas as pd
from sqlalchemy import select
from datetime import datetime

# Add project root to path
PROJECT_ROOT = r"c:\Users\FSOS\Desktop\ah final not\ECO_POWER"
sys.path.append(os.path.join(PROJECT_ROOT, 'backend'))

from src.data.database import SessionLocal, GenerationData

def check_data():
    db = SessionLocal()
    try:
        # Get records for noon today
        today = datetime(2026, 5, 7, 12, 0)
        start = today.replace(hour=11, minute=0)
        end = today.replace(hour=13, minute=0)
        
        records = db.query(GenerationData).filter(
            GenerationData.plant_id == "kpcl_shivanasamudra",
            GenerationData.timestamp >= start,
            GenerationData.timestamp <= end
        ).order_by(GenerationData.timestamp.asc()).all()
        
        print(f"{'Timestamp':<25} | {'Actual (kW)':<15} | {'Predicted (kW)':<15}")
        print("-" * 60)
        for r in records:
            print(f"{str(r.timestamp):<25} | {str(r.actual_kw):<15} | {str(r.predicted_kw):<15}")
            
    finally:
        db.close()

if __name__ == "__main__":
    check_data()
