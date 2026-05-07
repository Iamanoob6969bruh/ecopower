import sys
import os
from datetime import datetime, timedelta

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from src.data.database import SessionLocal, GenerationData
from src.config.plants import get_plants
from src.features.weather_fetcher import fetch_forecast_weather
from src.jobs.scheduler import interpolate_weather_to_15min
from src.models.predictor import predict_solar, predict_wind
from src.models.synthetic_actual import generate_solar_actual, generate_wind_actual
from sqlalchemy import delete

def refresh_data():
    print("Forcing data refresh in dashboard.db...")
    db = SessionLocal()
    try:
        plants = get_plants()
        now = datetime.now()
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        two_hours_ahead = now + timedelta(hours=24)
        
        for plant in plants:
            plant_id = plant['id']
            print(f"Processing {plant_id}...")
            hourly_weather = fetch_forecast_weather(
                plant_id, plant['latitude'], plant['longitude'], forecast_days=2
            )
            if not hourly_weather: 
                print(f"  No weather for {plant_id}")
                continue
                
            weather_15min = interpolate_weather_to_15min(hourly_weather)
            filtered_weather = {
                ts: data for ts, data in weather_15min.items() 
                if start_of_day <= datetime.fromisoformat(ts).replace(tzinfo=None) <= two_hours_ahead
            }
            
            if plant['type'] == 'solar':
                predicted_records = predict_solar(filtered_weather, plant)
                actual_records = generate_solar_actual(filtered_weather, plant)
            else:
                predicted_records = predict_wind(filtered_weather, plant)
                actual_records = generate_wind_actual(filtered_weather, plant)
                
            pred_dict = {p['timestamp']: p['predicted_kw'] for p in predicted_records}
            
            db_records = []
            for ts_iso, w_data in filtered_weather.items():
                ts = datetime.fromisoformat(ts_iso).replace(tzinfo=None)
                zone = "zone2" if ts < now else "zone3"
                actual_val = None
                if ts <= now:
                    match = next((a for a in actual_records if a['timestamp'].replace(tzinfo=None) == ts), None)
                    if match: actual_val = match['actual_kw']
                
                db_records.append(GenerationData(
                    plant_id=plant_id,
                    timestamp=ts,
                    actual_kw=actual_val,
                    predicted_kw=pred_dict.get(ts, 0.0),
                    zone_label=zone
                ))
            
            db.execute(
                delete(GenerationData).where(
                    GenerationData.plant_id == plant_id,
                    GenerationData.timestamp >= start_of_day,
                    GenerationData.timestamp <= two_hours_ahead
                )
            )
            db.bulk_save_objects(db_records)
            db.commit()
            print(f"  Updated {len(db_records)} records for {plant_id}")
            
        print("Refresh complete.")
    except Exception as e:
        print(f"Failed: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    refresh_data()
