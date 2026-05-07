import os
import sys
import pandas as pd
import numpy as np
import lightgbm as lgb
from datetime import datetime

# Add project root to path
PROJECT_ROOT = r"c:\Users\FSOS\Desktop\ah final not\ECO_POWER"
sys.path.append(os.path.join(PROJECT_ROOT, 'backend'))

from src.models.physics import apply_solar_physics

# Paths
MODEL_PATH = os.path.join(PROJECT_ROOT, 'solar_lightgbm.txt')
BASE_MODEL_DC = 50.0

def test_fixed_model():
    if not os.path.exists(MODEL_PATH):
        print(f"Model not found at {MODEL_PATH}")
        return

    bst = lgb.Booster(model_file=MODEL_PATH)
    features = bst.feature_name()

    # Create dummy data (noon on a sunny day)
    # Simulate what predictor.py now sends to apply_solar_physics
    now = datetime(2026, 5, 7, 12, 0)
    timestamps = [now.replace(hour=h) for h in range(8, 17)] # 8 AM to 4 PM
    
    records = []
    for ts in timestamps:
        records.append({
            'datetime': ts,
            'Temperature': 30,
            'Dew_Point': 15,
            'Relative_Humidity': 40,
            'Pressure': 1010,
            'TCC': 0.1,
            'Low_Cloud': 0.05,
            'Mid_Cloud': 0.05,
            'High_Cloud': 0.0,
            'Wind_Speed': 5,
            'GHI': 800 if 10 <= ts.hour <= 14 else 400,
            'DNI': 900 if 10 <= ts.hour <= 14 else 500,
            'DHI': 100
        })
    
    df = pd.DataFrame(records).set_index('datetime')
    
    # Run the overhauled physics module
    plant = {'latitude': 15.66, 'longitude': 76.01, 'tilt': 15.0, 'azimuth': 180.0}
    df = apply_solar_physics(df, plant['latitude'], plant['longitude'], plant['tilt'], plant['azimuth'], model_features=features)

    # Inference
    raw_preds = bst.predict(df[features])
    
    print("\n--- Test Results (Noon sunny day) ---")
    noon_idx = 4 # 12:00
    noon_pred = raw_preds[noon_idx]
    print(f"Raw Prediction (MW for 50MW plant): {noon_pred:.2f}")
    
    # Scaling logic check for Shivanasamudra (18 MW DC)
    dc_cap_mw = 18.0
    scaled_dc_output = (noon_pred / BASE_MODEL_DC) * dc_cap_mw
    print(f"Scaled Prediction for 18MW plant: {scaled_dc_output:.2f} MW")
    
    # PLF check
    plf = noon_pred / 50.0
    print(f"Calculated PLF: {plf:.2%}")

if __name__ == "__main__":
    test_fixed_model()
