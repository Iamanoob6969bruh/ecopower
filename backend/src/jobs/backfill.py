import logging
from datetime import datetime, timedelta
import pandas as pd
from sqlalchemy.orm import Session
from src.data.database import SessionLocal, GenerationData, get_now_ist
from src.features.weather_fetcher import fetch_historical_weather
from src.config.plants import get_plants
from src.models.synthetic_actual import generate_solar_actual, generate_wind_actual
from src.models.predictor import predict_solar, predict_wind

logger = logging.getLogger(__name__)

def interpolate_weather_to_15min(hourly_weather_dict: dict) -> dict:
    if not hourly_weather_dict:
        return {}
        
    df = pd.DataFrame.from_dict(hourly_weather_dict, orient='index')
    df.index = pd.to_datetime(df.index)
    df.sort_index(inplace=True)
    
    # Ensure all columns are numeric
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')
        
    # Resample to 15min and interpolate linearly
    df_15min = df.resample('15min').interpolate(method='linear').ffill().bfill()
    
    # Format back to dict
    res_dict = {}
    for ts, row in df_15min.iterrows():
        # Force naive standard ISO format
        res_dict[ts.replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%S")] = row.to_dict()
    return res_dict

def run_backfill(db: Session = None):
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        plants = get_plants()
        start_date_str = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        
        for plant in plants:
            plant_id = plant['id']
            try:
                # Check if we already have sufficient data
                existing = db.query(GenerationData).filter(
                    GenerationData.plant_id == plant_id,
                    GenerationData.zone_label == "zone1"
                ).count()
                
                # If we have at least 1 week of 15min records (4*24*7 = 672), we skip
                if existing > 100:
                    logger.info(f"[{plant_id}] Backfill already exists ({existing} records). Skipping.")
                    continue
                    
                logger.info(f"[{plant_id}] Starting backfill from {start_date_str} to {yesterday_str}...")
                
                # Fetch Hourly Weather
                hourly_weather = fetch_historical_weather(
                    plant_id, plant['latitude'], plant['longitude'], 
                    start_date=start_date_str, end_date=yesterday_str
                )
                
                if not hourly_weather:
                    logger.error(f"[{plant_id}] Failed to fetch historical weather.")
                    continue
                    
                # Upsample to 15min
                weather_15min = interpolate_weather_to_15min(hourly_weather)
                
                # Run Predictor & Synthetic Actual
                if plant['type'] == 'solar':
                    predicted_records = predict_solar(weather_15min, plant)
                    actual_records = generate_solar_actual(weather_15min, plant)
                else:
                    predicted_records = predict_wind(weather_15min, plant)
                    actual_records = generate_wind_actual(weather_15min, plant)
                
                # Combine into DB models
                db_records = []
                
                # Index predictions by timestamp for fast lookup
                pred_meta = {p['timestamp']: {'kw': p['predicted_kw'], 'weather': p.get('weather'), 'reason': p.get('reason')} for p in predicted_records}
                
                for act in actual_records:
                    ts = act['timestamp'].replace(tzinfo=None) if act['timestamp'].tzinfo else act['timestamp']
                    p_data = pred_meta.get(ts, {})
                    
                    db_records.append(GenerationData(
                        plant_id=plant_id,
                        timestamp=ts,
                        actual_kw=act['actual_kw'],
                        predicted_kw=p_data.get('kw', 0.0),
                        reasons=p_data.get('reason'),
                        weather_data=p_data.get('weather'),
                        zone_label="zone1"
                    ))
                
                # Bulk Insert
                if db_records:
                    # Chunked insert
                    chunk_size = 5000
                    for i in range(0, len(db_records), chunk_size):
                        db.bulk_save_objects(db_records[i:i+chunk_size])
                        db.commit()
                    logger.info(f"[{plant_id}] Backfilled {len(db_records)} records.")
                
                # Rate limiting for Open-Meteo on Render
                import time
                time.sleep(2.5)
                
            except Exception as plant_err:
                logger.error(f"[{plant_id}] Backfill step failed: {plant_err}")
                db.rollback()

    except Exception as e:
        logger.error(f"Backfill failed: {e}")
        db.rollback()
    finally:
        if close_db:
            db.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_backfill()
