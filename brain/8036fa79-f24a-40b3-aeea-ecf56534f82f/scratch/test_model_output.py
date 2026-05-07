import os
import pandas as pd
import numpy as np
import lightgbm as lgb

# Paths
BASE_DIR = r"c:\Users\FSOS\Desktop\ah final not\ECO_POWER"
MODEL_PATH = os.path.join(BASE_DIR, 'solar_lightgbm.txt')

def test_model():
    if not os.path.exists(MODEL_PATH):
        print(f"Model not found at {MODEL_PATH}")
        return

    bst = lgb.Booster(model_file=MODEL_PATH)
    features = bst.feature_name()
    print(f"Features: {features}")

    # Create dummy data (noon on a sunny day)
    # Based on engineering.py, typical features: cos_sza, ghi_wm2, cloud_cover_pct, temperature_c, etc.
    dummy_data = pd.DataFrame([{
        'cos_sza': 0.9,
        'ghi_wm2': 800,
        'cloud_cover_pct': 0,
        'temperature_c': 30,
        'hour_sin': 0,
        'hour_cos': -1,
        'month_sin': 1,
        'month_cos': 0,
        'doy_sin': 1,
        'doy_cos': 0,
        'block_of_day': 48,
        'is_weekend': 0,
        'plf_lag_1': 0.7,
        'plf_lag_4': 0.6,
        'plf_lag_96': 0.7,
        'plf_roll_mean_1h': 0.7,
        'plf_roll_mean_3h': 0.6,
        'plf_roll_mean_6h': 0.5,
        'plf_roll_std_1h': 0.01,
        'plf_roll_std_3h': 0.05,
        'plf_roll_std_6h': 0.1,
        'humidity_pct': 40,
        'pressure_hpa': 1010,
        'SZA': 25,
        'cos_SZA': 0.9,
        'TCC': 0,
        'GHI': 800,
        'DNI': 700,
        'DHI': 100,
        'Temperature': 30,
        'AM_relative': 1.1,
        'GHI_lag1': 750,
        'rolling_gen_efficiency': 0.85,
        'rolling_PR_proxy': 0.8,
        'Shading_Flag': 0,
        'plant_id': 0 # Categorical might need integer or string
    }])

    # Ensure all features are present
    for f in features:
        if f not in dummy_data.columns:
            dummy_data[f] = 0

    pred = bst.predict(dummy_data[features])
    print(f"Prediction: {pred[0]}")

if __name__ == "__main__":
    test_model()
