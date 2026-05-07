from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
import numpy as np
import lightgbm as lgb
import warnings
import httpx
from pvlib import solarposition, irradiance, atmosphere
import os

warnings.filterwarnings('ignore')

app = FastAPI(title="Solar AI Dispatch API - PGML Edition")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- SETUP & ASSETS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, 'synthetic_base_model.txt')
DATA_PATH = os.path.join(BASE_DIR, 'karnataka_training_data_realistic.csv')

bst = lgb.Booster(model_file=MODEL_PATH)
model_features = bst.feature_name()

# Dynamic SHAP Mapping
ghi_idx = model_features.index('GHI') if 'GHI' in model_features else 24
tcc_idx = model_features.index('TCC') if 'TCC' in model_features else 18
temp_idx = model_features.index('Temperature') if 'Temperature' in model_features else 13
sza_idx = model_features.index('SZA') if 'SZA' in model_features else 0

# ============================================================================
# LOGIC: PHYSICS-GUIDED FEATURE ENGINEERING
# ============================================================================
def apply_solar_physics(df: pd.DataFrame, lat: float, lon: float, tilt: float, az: float) -> pd.DataFrame:
    # 1. Sun Position
    solpos = solarposition.get_solarposition(df.index, lat, lon)
    df['SZA'] = solpos['zenith']
    df['cos_SZA'] = np.cos(np.radians(df['SZA']))
    
    # 2. Geometric POA (Tilted Irradiance) 
    # This transforms flat ground weather into panel-specific physics
    poa = irradiance.get_total_irradiance(
        surface_tilt=tilt,
        surface_azimuth=az,
        solar_zenith=solpos['apparent_zenith'],
        solar_azimuth=solpos['azimuth'],
        dni=df['DNI'],
        ghi=df['GHI'],
        dhi=df['DHI']
    )
    df['GHI'] = poa['poa_global'].fillna(0) # Use the tilted irradiance for the AI
    
    # 3. Standard Features
    df['hour_sin'] = np.sin(2 * np.pi * df.index.hour / 24)
    df['hour_cos'] = np.cos(2 * np.pi * df.index.hour / 24)
    df['AM_relative'] = atmosphere.get_relative_airmass(solpos['zenith'])
    df['GHI_lag1'] = df['GHI'].shift(1).fillna(0)
    
    # Mock operational variables
    df['rolling_gen_efficiency'] = 0.85 
    df['rolling_PR_proxy'] = 0.80
    df['Shading_Flag'] = 0
    
    for col in model_features:
        if col not in df.columns: df[col] = 0.0
            
    return df

# ============================================================================
# ENDPOINT: MULTI-TENANT LIVE AI FORECAST
# ============================================================================
class PlantRequest(BaseModel):
    latitude: float
    longitude: float
    dc_capacity_mw: float  # Panel capacity
    ac_capacity_mw: float  # Inverter cap
    tilt: float
    azimuth: float

@app.post("/api/live-prediction")
async def get_live_prediction(plant: PlantRequest):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": plant.latitude, "longitude": plant.longitude,
        "hourly": "temperature_2m,cloud_cover,shortwave_radiation,direct_normal_irradiance,diffuse_radiation",
        "timezone": "Asia/Kolkata", "forecast_days": 2
    }
    
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params)
    
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Weather API Failure")
    
    data = resp.json()
    live_df = pd.DataFrame({
        'datetime': pd.to_datetime(data['hourly']['time']).tz_localize('Asia/Kolkata'),
        'Temperature': data['hourly']['temperature_2m'],
        'TCC': np.array(data['hourly']['cloud_cover']) / 100.0,
        'GHI': data['hourly']['shortwave_radiation'],
        'DNI': data['hourly']['direct_normal_irradiance'],
        'DHI': data['hourly']['diffuse_radiation'],
    }).set_index('datetime')
    
    # Apply Physics Pipeline
    live_df = apply_solar_physics(live_df, plant.latitude, plant.longitude, plant.tilt, plant.azimuth)

   # 7. Run AI Inference & Hybrid Scaling
    BASE_MODEL_DC = 50.0  # The baseline the model was trained on
    
    # Get raw percentage/MW from the base model
    raw_preds = bst.predict(live_df[model_features])
    contribs = bst.predict(live_df[model_features], pred_contrib=True)
    
    # Apply Night Mask (Force 0 if sun is too low)
    raw_preds[live_df['SZA'] > 88] = 0.0 
    
    # PGML Scaling Logic:
    # 1. Scale the 50MW model to your 10MW DC panels
    scaled_dc_output = (raw_preds / BASE_MODEL_DC) * plant.dc_capacity_mw
    
    # 2. Mathematically enforce the 8.5MW AC Inverter limit (The Guardrail)[cite: 3]
    live_df['Live_Predicted_MW'] = np.clip(scaled_dc_output, 0, plant.ac_capacity_mw) 

    # --- DEBUG LOG --- 
    # This will show you in the terminal if the clipping is working
    max_val = live_df['Live_Predicted_MW'].max()
    print(f"DEBUG: Max Prediction is {max_val} MW (Limit: {plant.ac_capacity_mw} MW)")
    
    # Format Payload
    payload = []
    scale_factor = plant.dc_capacity_mw / BASE_MODEL_DC
    
    for ts, row in live_df.iterrows():
        idx = live_df.index.get_loc(ts)
        payload.append({
            "timestamp": ts.isoformat(),
            "pred_mw": round(row['Live_Predicted_MW'], 2), 
            "weather_ghi": round(row['GHI'], 0),
            "contrib_ghi": round(contribs[idx][ghi_idx] * scale_factor, 2),
            "contrib_clouds": round(contribs[idx][tcc_idx] * scale_factor, 2)
        })
        
    return payload