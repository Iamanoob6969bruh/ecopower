import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
import pandas as pd
from sqlalchemy import delete

from src.data.database import SessionLocal, GenerationData
from src.config.plants import get_plants
from src.features.weather_fetcher import fetch_forecast_weather
from src.models.synthetic_actual import generate_solar_actual, generate_wind_actual
from src.models.predictor import predict_solar, predict_wind
from src.data.database import SessionLocal, GenerationData, get_now_ist
from src.jobs.backfill import interpolate_weather_to_15min, run_backfill

logger = logging.getLogger(__name__)

import pytz
from datetime import datetime, timedelta

def run_15min_job():
    logger.info("Running 15-minute live fetch job...")
    db = SessionLocal()
    try:
        plants = get_plants()
        now = get_now_ist()
        # Look back 24 hours and forward 24 hours to ensure no gaps at midnight
        start_of_window = now - timedelta(hours=24)
        two_hours_ahead = now + timedelta(hours=24)
        
        for plant in plants:
            plant_id = plant['id']
            try:
                # Fetch Forecast (gets today and tomorrow)
                hourly_weather = fetch_forecast_weather(
                    plant_id, plant['latitude'], plant['longitude'], forecast_days=2
                )
                
                if not hourly_weather:
                    logger.warning(f"[{plant_id}] No weather data found.")
                    continue
                    
                # Upsample
                weather_15min = interpolate_weather_to_15min(hourly_weather)
                
                # Filter to our window (Start of day to Now+24H)
                filtered_weather = {
                    ts: data for ts, data in weather_15min.items() 
                    if start_of_window <= datetime.fromisoformat(ts).replace(tzinfo=None) <= two_hours_ahead
                }
                
                if not filtered_weather:
                    logger.warning(f"[{plant_id}] Filtered weather window is empty.")
                    continue

                if plant['type'] == 'solar':
                    predicted_records = predict_solar(filtered_weather, plant)
                    actual_records = generate_solar_actual(filtered_weather, plant)
                else:
                    predicted_records = predict_wind(filtered_weather, plant)
                    actual_records = generate_wind_actual(filtered_weather, plant)
                    
                # Create a lookup for predictions and their metadata
                pred_meta = {p['timestamp']: {'kw': p['predicted_kw'], 'weather': p.get('weather'), 'reason': p.get('reason')} for p in predicted_records}
                
                db_records = []
                for ts_iso, w_data in filtered_weather.items():
                    ts = datetime.fromisoformat(ts_iso).replace(tzinfo=None)
                    
                    # Zone Logic
                    if ts < now:
                        zone = "zone2" # Today midnight to now
                    else:
                        zone = "zone3" # Now to +24H
                        
                    # Find actual value from synthetic generator if it exists (only for past)
                    actual_val = None
                    if ts <= now:
                        match = next((a for a in actual_records if a['timestamp'].replace(tzinfo=None) == ts), None)
                        if match:
                            actual_val = match['actual_kw']
                    
                    p_data = pred_meta.get(ts, {})
                    db_records.append(GenerationData(
                        plant_id=plant_id,
                        timestamp=ts,
                        actual_kw=actual_val,
                        predicted_kw=p_data.get('kw', 0.0),
                        reasons=p_data.get('reason'),
                        weather_data=p_data.get('weather'),
                        zone_label=zone
                    ))
                
                # Delete existing records in this window to simulate UPSERT
                db.execute(
                    delete(GenerationData).where(
                        GenerationData.plant_id == plant_id,
                        GenerationData.timestamp >= start_of_window,
                        GenerationData.timestamp <= two_hours_ahead,
                        GenerationData.zone_label.in_(["zone2", "zone3"])
                    )
                )
                
                db.bulk_save_objects(db_records)
                db.commit()
                logger.info(f"[{plant_id}] Updated {len(db_records)} records.")
                
                # Rate limiting to avoid 429 errors from Open-Meteo on Render
                import time
                time.sleep(2.5)
                
            except Exception as plant_err:
                logger.error(f"[{plant_id}] Failed during 15min job: {plant_err}")
                db.rollback()
            
        logger.info("15-minute job completed.")
    except Exception as e:
        logger.error(f"15-minute job failed: {e}")
        db.rollback()
    finally:
        db.close()

def run_midnight_cleanup():
    logger.info("Running Midnight Cleanup...")
    db = SessionLocal()
    try:
        # Convert all zone2/zone3 records from previous days into zone1
        now = datetime.now()
        start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        records_to_update = db.query(GenerationData).filter(
            GenerationData.timestamp < start_of_today,
            GenerationData.zone_label.in_(["zone2", "zone3"])
        ).all()
        
        for r in records_to_update:
            r.zone_label = "zone1"
            
        db.commit()
        logger.info(f"Updated {len(records_to_update)} records to zone1.")
    except Exception as e:
        logger.error(f"Midnight job failed: {e}")
        db.rollback()
    finally:
        db.close()


def start_scheduler():
    scheduler = BackgroundScheduler()
    
    # Run backfill exactly once asynchronously
    scheduler.add_job(run_backfill, 'date', run_date=datetime.now() + timedelta(seconds=5))
    
    # 15 minute intervals
    scheduler.add_job(run_15min_job, IntervalTrigger(minutes=15), next_run_time=datetime.now() + timedelta(seconds=15))
    
    # Midnight cleanup
    scheduler.add_job(run_midnight_cleanup, CronTrigger(hour=0, minute=5))
    
    scheduler.start()
    return scheduler
