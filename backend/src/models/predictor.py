import os
import pandas as pd
import numpy as np
import joblib
import logging
from src.features.engineering import build_features, SOLAR_FEATURES, WIND_FEATURES
from src.models.synthetic_actual import generate_solar_actual, generate_wind_actual

logger = logging.getLogger(__name__)

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
MODELS_DIR = os.path.join(BASE_DIR, 'models', 'saved')
# New specialized model path
SPECIAL_SOLAR_MODEL = os.path.join(BASE_DIR, 'scaled lightgbm example', 'synthetic_base_model.txt')

_models = {}

def get_model(plant_type: str):
    global _models
    if plant_type not in _models:
        # Check for the special solar model first if it's solar
        if plant_type == 'solar' and os.path.exists(SPECIAL_SOLAR_MODEL):
            logger.info(f"Loading special solar model from {SPECIAL_SOLAR_MODEL}")
            import lightgbm as lgb
            _models[plant_type] = lgb.Booster(model_file=SPECIAL_SOLAR_MODEL)
            return _models[plant_type]

        # Search in multiple potential locations
        search_dirs = [
            MODELS_DIR,
            os.path.join(BASE_DIR, 'models'),
            BASE_DIR,
            os.path.join(BASE_DIR, 'backend', 'models', 'saved')
        ]
        
        # Priority: pkl > txt
        model_names = [f"{plant_type}_p50.pkl", f"{plant_type}_p50.txt", f"{plant_type}_lightgbm.txt", f"{plant_type}_model.txt"]
        
        found_path = None
        for d in search_dirs:
            for name in model_names:
                p = os.path.join(d, name)
                if os.path.exists(p):
                    found_path = p
                    break
            if found_path: break
            
        if found_path:
            logger.info(f"Loading {plant_type} model from {found_path}")
            try:
                if found_path.endswith('.pkl'):
                    _models[plant_type] = joblib.load(found_path)
                else:
                    import lightgbm as lgb
                    _models[plant_type] = lgb.Booster(model_file=found_path)
            except Exception as e:
                logger.error(f"Failed to load model {found_path}: {e}")
                return None
        else:
            logger.warning(f"ML Model for {plant_type} not found. Will use physics-based fallback.")
            return None
    return _models[plant_type]

def predict_generation(weather_dict: dict, plant: dict) -> list:
    """
    Unified prediction function for both solar and wind.
    """
    if not weather_dict:
        return []

    plant_type = plant.get('type', 'solar')
    model = get_model(plant_type)
    if not model:
        # Fallback to physics
        return physics_fallback_prediction(weather_dict, plant)

    # 1. Map raw Open-Meteo to dataframe
    records = []
    for ts_str, metrics in weather_dict.items():
        records.append({
            'timestamp': pd.to_datetime(ts_str),
            'temperature_c': metrics.get('temperature_2m', 25.0),
            'humidity_pct': metrics.get('relative_humidity_2m', 50.0),
            'pressure_hpa': metrics.get('surface_pressure', 1013.0),
            'cloud_cover_pct': metrics.get('cloud_cover', 0.0),
            # Pass every available wind height through as-is (None -> NaN). The
            # feature pipeline (adjust_wind_speed_to_hub_height) picks the best
            # available heights to derive hub-height wind — the forecast API gives
            # 80/120 m, the archive API only 10/100 m. Do NOT coalesce them here or
            # the shear estimate would use wrong heights.
            'wind_speed_ms': metrics.get('wind_speed_10m'),        # 10 m
            'wind_speed_80m': metrics.get('wind_speed_80m'),
            'wind_speed_100m': metrics.get('wind_speed_100m'),
            'wind_speed_120m': metrics.get('wind_speed_120m'),
            'wind_direction_deg': metrics.get('wind_direction_10m', 0.0),
            'ghi_wm2': metrics.get('shortwave_radiation', 0.0),
            'plant_id': plant['id'],
            'plant_type': plant_type,
            'latitude': plant['latitude'],
            'longitude': plant['longitude'],
            'installed_capacity_mw': plant.get('ac_capacity_mw', plant.get('capacity_kw', 1000) / 1000.0),
            'hub_height_m': plant.get('hub_height_m', 0.0),
            'generation_mw': 0.0  # Placeholder for PLF calculation
        })
    
    df = pd.DataFrame(records)
    df.sort_values('timestamp', inplace=True)
    
    # 2. Build Features
    # Note: build_features handles SZA, U/V decomposition, hub-height correction, etc.
    df = build_features(df)
    
    # 3. Select Features based on plant type
    features = SOLAR_FEATURES if plant_type == 'solar' else WIND_FEATURES
    
    # Ensure all features exist (handle lags if empty)
    for col in features:
        if col not in df.columns:
            df[col] = 0.0
            
    # LightGBM scikit-learn wrapper is sensitive to column order and types.
    # Use model.feature_name_ to ensure we pass exactly what it expects in the right order.
    model_features = getattr(model, 'feature_name_', features)
    
    # Ensure all required features exist in df
    for col in model_features:
        if col not in df.columns:
            df[col] = 0.0
            
    X = df[model_features].copy()
    X = X.fillna(0.0) # Ensure no NaNs reach the model
    
    if 'plant_id' in X.columns:
        X['plant_id'] = X['plant_id'].astype('category')

    # 4. Inference (Predict PLF)
    try:
        plf_preds = model.predict(X)
    except Exception as e:
        logger.warning(f"Prediction failed with DataFrame, falling back to values: {e}")
        plf_preds = model.predict(X.values)
    
    # 5. Scale to MW and format output
    ac_cap_mw = plant.get('ac_capacity_mw', plant.get('capacity_kw', 1000) / 1000.0)
    live_predicted_mw = np.clip(plf_preds, 0, 1.0) * ac_cap_mw
    
    results = []
    for i, ts in enumerate(df['timestamp']):
        # Store in kW for consistency with DB schema
        kw_val = float(live_predicted_mw[i]) * 1000.0
        
        # Get raw metrics for this timestamp
        # Standardize ISO format for lookup (no seconds, no offset)
        ts_iso = ts.strftime("%Y-%m-%dT%H:%M:%S")
        metrics = weather_dict.get(ts_iso, {})
        
        results.append({
            "timestamp": ts.to_pydatetime().replace(tzinfo=None),
            "predicted_kw": round(kw_val, 2),
            "weather": map_weather_for_frontend(metrics),
            "reason": generate_reason(plant_type, metrics)
        })
        
    return results

def generate_reason(plant_type: str, metrics: dict) -> str:
    """Generates a human-readable explanation for a prediction based on weather."""
    if not metrics:
        return "Standard operating conditions."
        
    if plant_type == 'solar':
        ghi = metrics.get('shortwave_radiation', 0)
        clouds = metrics.get('cloud_cover', 0)
        if ghi < 10:
            return "Nighttime or extremely low light conditions."
        if clouds > 80:
            return f"Heavy cloud cover ({clouds}%) reducing solar output."
        if clouds > 40:
            return f"Intermittent cloud cover ({clouds}%) affecting irradiance."
        return "Clear skies and high solar irradiance."
    else:
        ws = metrics.get('wind_speed_10m', 0)
        if ws < 3.5:
            return f"Low wind speed ({ws} m/s) below turbine cut-in."
        if ws > 22:
            return f"Extreme wind speed ({ws} m/s) near cut-out safety."
        if ws > 12:
            return f"Strong wind conditions ({ws} m/s) reaching peak power."
        return f"Steady wind flow at {ws} m/s."

def map_weather_for_frontend(metrics: dict) -> dict:
    """Maps Open-Meteo keys to the names expected by the frontend."""
    return {
        "ghi": round(metrics.get('shortwave_radiation', 0), 1),
        "wind_speed": round(metrics.get('wind_speed_10m', 0), 1),
        "temp": round(metrics.get('temperature_2m', 25.0), 1),
        "humidity": round(metrics.get('relative_humidity_2m', 50.0), 1),
        "clouds": round(metrics.get('cloud_cover', 0.0), 1),
        "pressure": round(metrics.get('surface_pressure', 1013.0), 1)
    }

def physics_fallback_prediction(weather_dict: dict, plant: dict) -> list:
    """
    Physical model fallback when ML is unavailable.
    """
    plant_type = plant.get('type', 'solar')
    if plant_type == 'solar':
        actuals = generate_solar_actual(weather_dict, plant)
    else:
        actuals = generate_wind_actual(weather_dict, plant)
        
    # Convert "actual" format to "predicted" format (they use the same physics)
    preds = []
    for a in actuals:
        ts_iso = a['timestamp'].strftime("%Y-%m-%dT%H:%M:%S")
        metrics = weather_dict.get(ts_iso, {})
        
        preds.append({
            "timestamp": a['timestamp'],
            "predicted_kw": a.get('actual_kw', 0.0),
            "weather": map_weather_for_frontend(metrics),
            "reason": generate_reason(plant_type, metrics)
        })
    return preds

def predict_solar_special(weather_dict: dict, plant: dict) -> list:
    """
    Specialized prediction for solar using the physics-guided synthetic_base_model.txt
    """
    from pvlib import solarposition, irradiance, atmosphere
    from pvlib.location import Location

    bst = get_model('solar')
    if not bst:
        return []

    model_features = bst.feature_name()

    # 1. Map raw weather to dataframe
    records = []
    for ts_str, metrics in weather_dict.items():
        records.append({
            'datetime': pd.to_datetime(ts_str),
            'Temperature': metrics.get('temperature_2m', 25.0),
            'Dew_Point': metrics.get('dewpoint_2m', 15.0),
            'Relative_Humidity': metrics.get('relative_humidity_2m', 50.0),
            'Pressure': metrics.get('surface_pressure', 940.0),
            'Wind_Speed': metrics.get('wind_speed_10m', 0.0),
            'TCC': (metrics.get('cloud_cover', 0.0) or 0.0) / 100.0,
            'Low_Cloud': (metrics.get('cloud_cover_low', 0.0) or 0.0) / 100.0,
            'Mid_Cloud': (metrics.get('cloud_cover_mid', 0.0) or 0.0) / 100.0,
            'High_Cloud': (metrics.get('cloud_cover_high', 0.0) or 0.0) / 100.0,
            'GHI_raw': metrics.get('shortwave_radiation', 0.0) or 0.0,
            'DNI': metrics.get('direct_normal_irradiance', 0.0) or 0.0,
            'DHI': metrics.get('diffuse_radiation', 0.0) or 0.0,
        })

    df = pd.DataFrame(records).set_index('datetime')
    if df.index.tz is None:
        df.index = df.index.tz_localize('Asia/Kolkata')
    else:
        df.index = df.index.tz_convert('Asia/Kolkata')
    df.sort_index(inplace=True)   # ensure chronological order before lag/rolling

    # 2. Physics — solar geometry, tilted POA, and clear-sky reference
    lat, lon = plant['latitude'], plant['longitude']
    tilt = plant.get('tilt', 15.0)
    az = plant.get('azimuth', 180.0)
    loc = Location(lat, lon, altitude=plant.get('altitude', 600))

    solpos = solarposition.get_solarposition(df.index, lat, lon)
    df['SZA'] = solpos['zenith']
    df['cos_SZA'] = np.cos(np.radians(df['SZA']))
    df['Solar_Azimuth'] = solpos['azimuth']
    df['Solar_Elevation'] = solpos['elevation']
    df['Solar_Declination'] = np.radians(
        23.45 * np.sin(np.radians(360.0 / 365.0 * (df.index.dayofyear - 81)))
    )
    df['AM_relative'] = atmosphere.get_relative_airmass(solpos['apparent_zenith']).fillna(40.0)

    poa = irradiance.get_total_irradiance(
        surface_tilt=tilt, surface_azimuth=az,
        solar_zenith=solpos['apparent_zenith'], solar_azimuth=solpos['azimuth'],
        dni=df['DNI'], ghi=df['GHI_raw'], dhi=df['DHI'],
    )
    df['GHI'] = poa['poa_global'].fillna(0)   # POA is what the model was trained to call "GHI"

    clear = loc.get_clearsky(df.index, model='ineichen')
    df['GHI_clear'] = clear['ghi']
    df['DNI_clear'] = clear['dni']
    df['Clearness_Index'] = np.clip(df['GHI_raw'] / df['GHI_clear'].where(df['GHI_clear'] > 1, np.nan), 0, 1.2).fillna(0)

    # Temporal encodings
    doy = df.index.dayofyear
    df['hour_sin'] = np.sin(2 * np.pi * df.index.hour / 24)
    df['hour_cos'] = np.cos(2 * np.pi * df.index.hour / 24)
    df['doy_sin'] = np.sin(2 * np.pi * doy / 365)
    df['doy_cos'] = np.cos(2 * np.pi * doy / 365)
    df['doy_sin2'] = np.sin(4 * np.pi * doy / 365)
    df['doy_cos2'] = np.cos(4 * np.pi * doy / 365)

    # Lag / rolling / delta features on the (POA) GHI series
    df['GHI_lag1'] = df['GHI'].shift(1).fillna(0)
    df['GHI_lag2'] = df['GHI'].shift(2).fillna(0)
    df['clearness_lag1'] = df['Clearness_Index'].shift(1).fillna(0)
    df['GHI_rollmean_45m'] = df['GHI'].rolling(3, min_periods=1).mean()
    df['GHI_rollmean_1h'] = df['GHI'].rolling(4, min_periods=1).mean()
    df['GHI_rollmean_3h'] = df['GHI'].rolling(12, min_periods=1).mean()
    df['GHI_rollstd_1h'] = df['GHI'].rolling(4, min_periods=1).std().fillna(0)
    df['dGHI_dt'] = df['GHI'].diff().fillna(0)
    df['dTCC_dt'] = df['TCC'].diff().fillna(0)

    # Consecutive dark (near-zero irradiance) steps
    dark = (df['GHI_raw'] < 10).astype(int)
    df['Consecutive_dark_steps'] = dark.groupby((dark == 0).cumsum()).cumsum()

    # Signals we have no live source for — set to neutral in-distribution values
    df['Days_Since_Rain'] = 0.0
    df['Shading_Flag'] = 0
    df['rolling_gen_efficiency'] = 0.038   # training mean (range 0-0.054); prior 0.85 was ~22x OOD
    df['rolling_PR_proxy'] = 0.75          # training mean ~0.75

    # Any feature still absent (should be none now) -> 0, and log it so gaps are visible
    missing = [c for c in model_features if c not in df.columns]
    if missing:
        logger.warning(f"Solar model features still zero-filled: {missing}")
        for col in missing:
            df[col] = 0.0

    X = df[model_features].fillna(0.0)

    # 3. Inference
    raw_preds = bst.predict(X)
    raw_preds = np.asarray(raw_preds, dtype=float)
    raw_preds[df['SZA'].values > 88] = 0.0   # night mask

    # 4. Scale from the model's 50 MW-DC training baseline to this plant
    BASE_MODEL_DC = 50.0   # the plant the synthetic_base_model was trained on (~41.67 MW AC)
    dc_cap_mw = plant.get('dc_capacity_mw', plant.get('capacity_kw', 1000) / 1000.0 * 1.2)
    ac_cap_mw = plant.get('ac_capacity_mw', plant.get('capacity_kw', 1000) / 1000.0)

    scaled_dc_output = (raw_preds / BASE_MODEL_DC) * dc_cap_mw
    live_predicted_mw = np.clip(scaled_dc_output, 0, ac_cap_mw)
    
    results = []
    for i, ts in enumerate(df.index):
        ts_iso = ts.strftime("%Y-%m-%dT%H:%M:%S")
        # Find raw metrics (Open-Meteo format)
        metrics = weather_dict.get(ts_iso, {})
        
        results.append({
            "timestamp": ts.to_pydatetime().replace(tzinfo=None),
            "predicted_kw": round(float(live_predicted_mw[i]) * 1000.0, 2),
            "weather": map_weather_for_frontend(metrics),
            "reason": generate_reason('solar', metrics)
        })
    return results

def predict_solar(weather_dict: dict, plant: dict) -> list:
    if os.path.exists(SPECIAL_SOLAR_MODEL):
        return predict_solar_special(weather_dict, plant)
    return predict_generation(weather_dict, plant)

def predict_wind(weather_dict: dict, plant: dict) -> list:
    # Wind forecast comes straight from the trained LightGBM model.
    # (Previously an artificial sine + random deviation was layered on top here
    #  to force visual separation from the "actual" curve — that fakery has been
    #  removed so the dashboard shows the model's genuine output.)
    return predict_generation(weather_dict, plant)
