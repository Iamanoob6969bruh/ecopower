import requests
import pandas as pd
import time
import os
from pathlib import Path

# ================= CONFIG =================
PLANTS = {
    "SAUNDATTI_WF":   (16.052, 74.648),
    "ACCIONA_TUP":    (14.228, 76.581),
    "NUZIVEEDU_BHM":  (14.156, 76.524),
    "HARPANA_WF":     (14.582, 76.885),
    "GADAG_CLUSTER":  (15.368, 75.632),
    "NTPC_KAR_Multi": (15.410, 76.190),
    "kspdcl_pavagada": (14.250, 77.450),
    "kpcl_shivanasamudra": (12.300, 77.170)
}

OUTPUT_CSV = "data/raw/nwp_weather.csv"

def fetch_live_forecast(lat, lon):
    """Fetch 7-day forecast from Open-Meteo"""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat, "longitude": lon,
        "hourly": "wind_speed_10m,wind_direction_10m,temperature_2m,surface_pressure,relative_humidity_2m,shortwave_radiation,cloud_cover",
        "timezone": "UTC",
        "past_days": 1,
        "forecast_days": 7
    }
    
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    
    df_hourly = pd.DataFrame({
        "timestamp": pd.to_datetime(data["hourly"]["time"]),
        "wind_speed_ms": [v/3.6 for v in data["hourly"]["wind_speed_10m"]], # km/h to m/s
        "wind_direction_deg": data["hourly"]["wind_direction_10m"],
        "temperature_c": data["hourly"]["temperature_2m"],
        "pressure_hpa": data["hourly"]["surface_pressure"],
        "humidity_pct": data["hourly"]["relative_humidity_2m"],
        "ghi_wm2": data["hourly"]["shortwave_radiation"],
        "cloud_cover_pct": data["hourly"]["cloud_cover"]
    })
    
    # Resample to 15-min
    df_hourly = df_hourly.set_index("timestamp")
    df_15m = df_hourly.resample('15min').interpolate(method='linear').reset_index()
    return df_15m

def main():
    print("🚀 Fetching live weather forecasts for 2026...")
    all_dfs = []
    
    for pid, (lat, lon) in PLANTS.items():
        print(f"📍 {pid}...")
        try:
            df = fetch_live_forecast(lat, lon)
            df["plant_id"] = pid
            all_dfs.append(df)
            time.sleep(1) # Rate limiting
        except Exception as e:
            print(f"❌ Failed for {pid}: {e}")
            
    if not all_dfs:
        print("No data fetched.")
        return
        
    new_data = pd.concat(all_dfs, ignore_index=True)
    
    # Load existing or create new
    if Path(OUTPUT_CSV).exists():
        old_df = pd.read_csv(OUTPUT_CSV)
        old_df["timestamp"] = pd.to_datetime(old_df["timestamp"])
        
        # Combine and drop duplicates (keep newest)
        combined = pd.concat([old_df, new_data], ignore_index=True)
        combined = combined.drop_duplicates(subset=["timestamp", "plant_id"], keep="last")
        combined = combined.sort_values(["plant_id", "timestamp"])
    else:
        combined = new_data
        
    combined.to_csv(OUTPUT_CSV, index=False)
    print(f"✅ NWP Updated: {combined['timestamp'].min()} to {combined['timestamp'].max()}")
    print(f"Total rows: {len(combined)}")

if __name__ == "__main__":
    main()
