
import pandas as pd
import json
from src.models.predict import predict_plant, load_models
from src.features.engineering import build_features

def run_local_test():
    # 1. Create sample weather data (NWP)
    # Note: In a real scenario, you'd also need some SCADA history for the lag features
    # But build_features will handle missing columns by filling with defaults/NaNs
    weather_data = {
        "timestamp": ["2023-01-01 12:00:00"],
        "plant_id": ["SAUNDATTI_WF"],
        "plant_type": ["wind"],
        "wind_speed_ms": [8.5],
        "wind_direction_deg": [190.0],
        "temperature_c": [28.0],
        "pressure_hpa": [1012.0],
        "humidity_pct": [45.0],
        "ghi_wm2": [0.0],
        "cloud_cover_pct": [10.0]
    }
    
    # 2. Create sample SCADA data (minimal for features)
    scada_data = {
        "timestamp": ["2023-01-01 12:00:00"],
        "plant_id": ["SAUNDATTI_WF"],
        "plant_type": ["wind"],
        "installed_capacity_mw": [84.0],
        "generation_mw": [0.0], # Not used for prediction, only for evaluation
        "availability_flag": [1],
        "latitude": [16.052],
        "longitude": [74.648],
        "hub_height_m": [90]
    }

    nwp_df = pd.DataFrame(weather_data)
    scada_df = pd.DataFrame(scada_data)
    
    nwp_df["timestamp"] = pd.to_datetime(nwp_df["timestamp"])
    scada_df["timestamp"] = pd.to_datetime(scada_df["timestamp"])

    # 3. Build features (matches the training pipeline)
    print("Building features...")
    merged = pd.merge(scada_df, nwp_df, on=["timestamp", "plant_id", "plant_type"], how="inner")
    feature_df = build_features(merged)

    # 4. Load models and predict
    print("Loading models...")
    models = load_models("wind")
    
    print("Running prediction...")
    prediction = predict_plant(
        feature_df=feature_df,
        plant_id="SAUNDATTI_WF",
        plant_type="wind",
        installed_capacity_mw=84.0,
        models=models
    )

    print("\n=== Prediction Results ===")
    print(prediction[["timestamp", "p10_mw", "p50_mw", "p90_mw", "confidence_flag"]].to_string(index=False))
    print("==========================")

if __name__ == "__main__":
    run_local_test()
