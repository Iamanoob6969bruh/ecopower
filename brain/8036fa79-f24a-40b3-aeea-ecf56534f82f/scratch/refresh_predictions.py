import os
import sys
import logging
from datetime import datetime, timedelta
import pandas as pd
from sqlalchemy import delete

# Add project root to path
PROJECT_ROOT = r"c:\Users\FSOS\Desktop\ah final not\ECO_POWER"
sys.path.append(os.path.join(PROJECT_ROOT, 'backend'))

from src.data.database import SessionLocal, GenerationData
from src.config.plants import get_plants
from src.features.weather_fetcher import fetch_forecast_weather
from src.models.predictor import predict_solar
from src.models.synthetic_actual import generate_solar_actual
from src.jobs.backfill import interpolate_weather_to_15min

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def refresh_today_data():
    logger.info("Starting manual refresh of today's predictions...")
    db = SessionLocal()
    try:
        plants = get_plants()
        now = datetime.now()
        start_refresh = now - timedelta(hours=24)
        end_refresh = now + timedelta(hours=24)
        
        for plant in plants:
            plant_id = plant['id']
            if plant['type'] != 'solar': continue
            
            logger.info(f"Refreshing {plant_id}...")
            
            # 1. Fetch Weather for the last 2 days + today
            # We use forecast API with past_days=2 which is more reliable for near past
            from src.features.weather_fetcher import fetch_forecast_weather
            
            weather_data = fetch_forecast_weather(
                plant_id, plant['latitude'], plant['longitude'], 
                forecast_days=2, past_days=2
            )
            
            if not weather_data:
                logger.warning(f"No weather for {plant_id}")
                continue
                
            # 2. Upsample
            weather_15min = interpolate_weather_to_15min(weather_data)
            
            # 3. Predict & Generate Actual
            predicted_records = predict_solar(weather_15min, plant)
            actual_records = generate_solar_actual(weather_15min, plant)
            
            pred_dict = {p['timestamp']: p['predicted_kw'] for p in predicted_records}
            
            db_records = []
            for act in actual_records:
                ts = act['timestamp'].replace(tzinfo=None) if act['timestamp'].tzinfo else act['timestamp']
                
                # Zone Logic
                if ts < now:
                    zone = "zone2"
                else:
                    zone = "zone3"
                    
                actual_val = act['actual_kw'] if ts <= now else None
                
                db_records.append(GenerationData(
                    plant_id=plant_id,
                    timestamp=ts,
                    actual_kw=actual_val,
                    predicted_kw=pred_dict.get(ts, 0.0),
                    zone_label=zone
                ))
            
            # 4. Clean up existing records for the range
            db.execute(
                delete(GenerationData).where(
                    GenerationData.plant_id == plant_id,
                    GenerationData.timestamp >= start_refresh,
                    GenerationData.timestamp < end_refresh
                )
            )
            
            # 5. Insert new records
            db.bulk_save_objects(db_records)
            db.commit()
            logger.info(f"Successfully refreshed {len(db_records)} records for {plant_id}")
            
        logger.info("Refresh complete.")
    except Exception as e:
        logger.error(f"Refresh failed: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    refresh_today_data()
