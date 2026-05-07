import os
import sys
import pandas as pd
from sqlalchemy import select

# Add project root to path
PROJECT_ROOT = r"c:\Users\FSOS\Desktop\ah final not\ECO_POWER"
sys.path.append(os.path.join(PROJECT_ROOT, 'backend'))

from src.data.database import SessionLocal, GenerationData

def check_data():
    db = SessionLocal()
    try:
        # Get latest 5 records for the flagship plant
        records = db.query(GenerationData).filter(
            GenerationData.plant_id == "kpcl_shivanasamudra"
        ).order_by(GenerationData.timestamp.desc()).limit(10).all()
        
        print(f"{'Timestamp':<25} | {'Actual (kW)':<15} | {'Predicted (kW)':<15}")
        print("-" * 60)
        for r in records:
            print(f"{str(r.timestamp):<25} | {str(r.actual_kw):<15} | {str(r.predicted_kw):<15}")
            
    finally:
        db.close()

if __name__ == "__main__":
    check_data()
