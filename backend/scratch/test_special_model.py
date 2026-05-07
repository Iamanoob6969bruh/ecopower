import sys
import os
import pandas as pd
from datetime import datetime

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from src.models.predictor import predict_solar
from src.config.plants import get_plant_by_id

def test_special_model():
    plant = get_plant_by_id('kspdcl_pavagada')
    # Mock weather
    weather = {
        "2026-05-07T12:00:00": {
            "temperature_2m": 35.0,
            "cloud_cover": 10,
            "shortwave_radiation": 900,
            "direct_normal_irradiance": 800,
            "diffuse_radiation": 100
        }
    }
    
    print(f"Testing special model for {plant['name']}...")
    try:
        results = predict_solar(weather, plant)
        print(f"Results: {results}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_special_model()
