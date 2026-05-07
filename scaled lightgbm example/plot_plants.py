import os
import sys
import pandas as pd
import numpy as np
import lightgbm as lgb
import httpx
import asyncio
import matplotlib.pyplot as plt
from pvlib import solarposition, irradiance, atmosphere

# Add project root to sys.path to import PLANTS
# Project root is c:\Users\FSOS\Desktop\ah final not\ECO_POWER
PROJECT_ROOT = r"c:\Users\FSOS\Desktop\ah final not\ECO_POWER"
sys.path.append(os.path.join(PROJECT_ROOT, 'backend', 'src'))

try:
    from config.plants import PLANTS
except ImportError:
    print("Failed to import PLANTS. Check sys.path.")
    sys.exit(1)

# --- SETUP & ASSETS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, 'synthetic_base_model.txt')
bst = lgb.Booster(model_file=MODEL_PATH)
model_features = bst.feature_name()

def apply_solar_physics(df: pd.DataFrame, lat: float, lon: float, tilt: float, az: float) -> pd.DataFrame:
    solpos = solarposition.get_solarposition(df.index, lat, lon)
    df['SZA'] = solpos['zenith']
    df['cos_SZA'] = np.cos(np.radians(df['SZA']))
    
    poa = irradiance.get_total_irradiance(
        surface_tilt=tilt,
        surface_azimuth=az,
        solar_zenith=solpos['apparent_zenith'],
        solar_azimuth=solpos['azimuth'],
        dni=df['DNI'],
        ghi=df['GHI'],
        dhi=df['DHI']
    )
    df['GHI'] = poa['poa_global'].fillna(0)
    
    df['hour_sin'] = np.sin(2 * np.pi * df.index.hour / 24)
    df['hour_cos'] = np.cos(2 * np.pi * df.index.hour / 24)
    df['AM_relative'] = atmosphere.get_relative_airmass(solpos['zenith'])
    df['GHI_lag1'] = df['GHI'].shift(1).fillna(0)
    
    df['rolling_gen_efficiency'] = 0.85 
    df['rolling_PR_proxy'] = 0.80
    df['Shading_Flag'] = 0
    
    for col in model_features:
        if col not in df.columns: df[col] = 0.0
            
    return df

async def get_prediction(plant):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": plant['latitude'], "longitude": plant['longitude'],
        "hourly": "temperature_2m,cloud_cover,shortwave_radiation,direct_normal_irradiance,diffuse_radiation",
        "timezone": "Asia/Kolkata", "forecast_days": 2
    }
    
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params)
    
    if resp.status_code != 200:
        print(f"Error fetching data for {plant['name']}")
        return None
    
    data = resp.json()
    live_df = pd.DataFrame({
        'datetime': pd.to_datetime(data['hourly']['time']).tz_localize('Asia/Kolkata'),
        'Temperature': data['hourly']['temperature_2m'],
        'TCC': np.array(data['hourly']['cloud_cover']) / 100.0,
        'GHI': data['hourly']['shortwave_radiation'],
        'DNI': data['hourly']['direct_normal_irradiance'],
        'DHI': data['hourly']['diffuse_radiation'],
    }).set_index('datetime')
    
    live_df = apply_solar_physics(live_df, plant['latitude'], plant['longitude'], plant['tilt'], plant['azimuth'])
    
    BASE_MODEL_DC = 50.0
    raw_preds = bst.predict(live_df[model_features])
    raw_preds[live_df['SZA'] > 88] = 0.0 
    
    scaled_dc_output = (raw_preds / BASE_MODEL_DC) * plant['dc_capacity_mw']
    live_df['Live_Predicted_MW'] = np.clip(scaled_dc_output, 0, plant['ac_capacity_mw']) 
    
    return live_df

async def main():
    # Filter for solar plants only
    solar_plants = [p for p in PLANTS if p['type'] == 'solar']
    
    # We will save to a local 'plots' folder first
    output_dir = os.path.join(BASE_DIR, 'plots')
    os.makedirs(output_dir, exist_ok=True)
    
    for plant in solar_plants:
        print(f"Processing {plant['name']}...")
        df = await get_prediction(plant)
        if df is not None:
            plt.figure(figsize=(12, 6))
            plt.plot(df.index, df['Live_Predicted_MW'], label='Predicted MW', color='#f39c12', linewidth=2)
            plt.fill_between(df.index, df['Live_Predicted_MW'], alpha=0.3, color='#f39c12')
            
            plt.title(f"Solar Generation Forecast: {plant['name']}")
            plt.suptitle(f"Coords: ({plant['latitude']}, {plant['longitude']}) | Capacity: {plant['ac_capacity_mw']}MW AC / {plant['dc_capacity_mw']}MW DC", fontsize=10)
            
            plt.xlabel("Time (Asia/Kolkata)")
            plt.ylabel("Generation (MW)")
            plt.grid(True, linestyle='--', alpha=0.6)
            plt.legend()
            plt.xticks(rotation=45)
            plt.tight_layout(rect=[0, 0.03, 1, 0.95])
            
            filename = f"{plant['id']}_forecast.png"
            plt.savefig(os.path.join(output_dir, filename), dpi=100)
            plt.close()
            print(f"Saved plot to {os.path.join(output_dir, filename)}")

if __name__ == "__main__":
    asyncio.run(main())
