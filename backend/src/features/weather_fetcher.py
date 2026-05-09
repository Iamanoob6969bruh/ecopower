import requests
from datetime import datetime, timedelta
import logging
from src.data.database import SessionLocal, WeatherDataCache

logger = logging.getLogger(__name__)

# Simple in-memory cache: {(plant_id, "forecast"|"historical", start_date, end_date): (timestamp, data)}
_cache = {}
CACHE_TTL = timedelta(minutes=10)

def _get_from_cache(cache_key):
    if cache_key in _cache:
        from src.data.database import get_now_ist
        cached_time, data = _cache[cache_key]
        if get_now_ist() - cached_time < CACHE_TTL:
            return data
    return None

def _save_to_cache(cache_key, data):
    from src.data.database import get_now_ist
    _cache[cache_key] = (get_now_ist(), data)

def _get_fallback_weather(plant_id: str, target_time: datetime = None):
    """Fallback to the latest known weather for this plant in DB."""
    db = SessionLocal()
    try:
        query = db.query(WeatherDataCache).filter(WeatherDataCache.plant_id == plant_id)
        if target_time:
            query = query.filter(WeatherDataCache.timestamp <= target_time)
        latest_record = query.order_by(WeatherDataCache.timestamp.desc()).first()
        if latest_record:
            return latest_record.weather_json
        return None
    finally:
        db.close()

def _save_to_db_cache(plant_id: str, weather_data: dict):
    """Save raw weather dict mapped by timestamp into WeatherDataCache for fallback."""
    db = SessionLocal()
    try:
        for timestamp_str, data in weather_data.items():
            ts = datetime.fromisoformat(timestamp_str)
            record = db.query(WeatherDataCache).filter_by(plant_id=plant_id, timestamp=ts).first()
            if not record:
                record = WeatherDataCache(plant_id=plant_id, timestamp=ts, weather_json=data)
                db.add(record)
            else:
                record.weather_json = data
        db.commit()
    except Exception as e:
        logger.error(f"Failed to save weather cache to DB: {e}")
        db.rollback()
    finally:
        db.close()

def fetch_historical_weather(plant_id: str, lat: float, lon: float, start_date: str, end_date: str):
    """Fetch from Open-Meteo Historical Archive API."""
    cache_key = (plant_id, "historical", start_date, end_date)
    cached = _get_from_cache(cache_key)
    if cached: return cached

    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "hourly": "temperature_2m,dewpoint_2m,relative_humidity_2m,surface_pressure,cloud_cover,cloud_cover_low,cloud_cover_mid,cloud_cover_high,wind_speed_10m,wind_speed_80m,wind_speed_100m,wind_speed_120m,wind_direction_10m,shortwave_radiation,direct_normal_irradiance,diffuse_radiation",
        "timezone": "Asia/Kolkata"
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        parsed_data = {}
        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        
        for i, t in enumerate(times):
            parsed_data[t] = {k: hourly[k][i] for k in hourly.keys() if k != "time"}
            
        _save_to_cache(cache_key, parsed_data)
        _save_to_db_cache(plant_id, parsed_data)
        return parsed_data
    except Exception as e:
        logger.error(f"Error fetching historical weather for {plant_id}: {e}")
        # Fallback is less meaningful for bulk historical, but let's try
        return {}

def fetch_forecast_weather(plant_id: str, lat: float, lon: float, forecast_days: int = 1, past_days: int = 0):
    """Fetch from Open-Meteo Forecast API for current and short-term forecast."""
    cache_key = (plant_id, "forecast", forecast_days, past_days)
    cached = _get_from_cache(cache_key)
    if cached: return cached

    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "forecast_days": forecast_days,
        "past_days": past_days,
        "hourly": "temperature_2m,dewpoint_2m,relative_humidity_2m,surface_pressure,cloud_cover,cloud_cover_low,cloud_cover_mid,cloud_cover_high,wind_speed_10m,wind_speed_80m,wind_speed_100m,wind_speed_120m,wind_direction_10m,shortwave_radiation,direct_normal_irradiance,diffuse_radiation",
        "timezone": "Asia/Kolkata"
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        parsed_data = {}
        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        
        for i, t in enumerate(times):
            parsed_data[t] = {k: hourly[k][i] for k in hourly.keys() if k != "time"}
            
        _save_to_cache(cache_key, parsed_data)
        _save_to_db_cache(plant_id, parsed_data)
        return parsed_data
    except Exception as e:
        logger.error(f"Error fetching forecast weather for {plant_id}: {e}")
        fallback = _get_fallback_weather(plant_id)
        if fallback:
            # Fake the current timestamp using the fallback data
            from src.data.database import get_now_ist
            now_str = get_now_ist().strftime("%Y-%m-%dT%H:00")
            return {now_str: fallback}
        return {}
