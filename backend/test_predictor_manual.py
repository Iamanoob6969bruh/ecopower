import os
import sys
# Add current directory to path so we can import src
sys.path.append(os.getcwd())

from src.models.predictor import get_model, predict_solar
from src.config.plants import get_plants

def test_predictor():
    try:
        print("Testing model load...")
        bst, features = get_model()
        print(f"Model loaded. Features: {features}")
        
        plant = get_plants()[0]
        weather = {
            "2026-05-06T12:00": {
                "temperature_2m": 30.0,
                "cloud_cover": 0,
                "shortwave_radiation": 800.0
            }
        }
        print(f"Testing prediction for {plant['id']}...")
        results = predict_solar(weather, plant)
        print(f"Results: {results}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_predictor()
