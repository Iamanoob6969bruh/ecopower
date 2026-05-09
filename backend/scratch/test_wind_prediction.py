
import sys
import os
import pytz
from datetime import datetime, timedelta

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from src.config.plants import get_plants
from src.features.weather_fetcher import fetch_forecast_weather
from src.models.predictor import predict_wind

def test_wind_prediction():
    kolkata = pytz.timezone('Asia/Kolkata')
    now = datetime.now(kolkata)
    print(f"Current time (IST): {now}")
    
    plants = [p for p in get_plants() if p['type'] == 'wind']
    if not plants:
        print("No wind plants found!")
        return

    plant = plants[0]
    print(f"Testing for plant: {plant['id']}")
    
    weather = fetch_forecast_weather(
        plant['id'], plant['latitude'], plant['longitude'], forecast_days=1
    )
    
    if not weather:
        print("Failed to fetch weather!")
        return
        
    print(f"Fetched weather for {len(weather)} hours.")
    
    predictions = predict_wind(weather, plant)
    print(f"Generated {len(predictions)} predictions.")
    
    if predictions:
        print("Sample prediction:")
        print(predictions[0])
        
        sum_pred = sum(p['predicted_kw'] for p in predictions)
        print(f"Total predicted kW: {sum_pred}")
        
        if sum_pred == 0:
            print("WARNING: Total predicted kW is 0!")
    else:
        print("No predictions generated!")

if __name__ == "__main__":
    test_wind_prediction()
