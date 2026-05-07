import sys
import os
import pandas as pd
import numpy as np
import lightgbm as lgb
from pvlib import solarposition, irradiance, atmosphere

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from src.config.plants import get_plant_by_id

def debug_raw_model():
    plant = get_plant_by_id('kspdcl_pavagada')
    model_path = os.path.join(os.getcwd(), 'scaled lightgbm example', 'synthetic_base_model.txt')
    bst = lgb.Booster(model_file=model_path)
    model_features = bst.feature_name()
    
    # Mock weather (High irradiance noon)
    ts = pd.to_datetime("2026-05-07T12:00:00").tz_localize('Asia/Kolkata')
    lat, lon = plant['latitude'], plant['longitude']
    
    solpos = solarposition.get_solarposition([ts], lat, lon)
    ghi_raw = 950 # Clear sky noon
    dni = 850
    dhi = 100
    
    poa = irradiance.get_total_irradiance(
        surface_tilt=15, surface_azimuth=180,
        solar_zenith=solpos['apparent_zenith'], solar_azimuth=solpos['azimuth'],
        dni=[dni], ghi=[ghi_raw], dhi=[dhi]
    )
    
    row = {
        'Temperature': 35.0,
        'TCC': 0.1,
        'GHI': poa['poa_global'].iloc[0],
        'SZA': solpos['zenith'].iloc[0],
        'cos_SZA': np.cos(np.radians(solpos['zenith'].iloc[0])),
        'hour_sin': np.sin(2 * np.pi * ts.hour / 24),
        'hour_cos': np.cos(2 * np.pi * ts.hour / 24),
        'AM_relative': atmosphere.get_relative_airmass(solpos['zenith']).iloc[0],
        'GHI_lag1': 900,
        'rolling_gen_efficiency': 0.85,
        'rolling_PR_proxy': 0.80,
        'Shading_Flag': 0
    }
    
    df = pd.DataFrame([row])
    for col in model_features:
        if col not in df.columns: df[col] = 0.0
            
    raw_pred = bst.predict(df[model_features])[0]
    print(f"RAW PREDICTION (MW): {raw_pred}")
    print(f"FOR PLANT: {plant['name']} ({plant['capacity_mw']} MW)")
    
    BASE_MODEL_DC = 50.0
    plf = raw_pred / BASE_MODEL_DC
    print(f"CALCULATED PLF: {plf}")
    
    scaled = plf * plant['capacity_mw']
    print(f"SCALED OUTPUT (MW): {scaled}")

if __name__ == "__main__":
    debug_raw_model()
