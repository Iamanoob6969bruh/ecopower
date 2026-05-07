import requests
import pandas as pd
import time
import os
from tqdm import tqdm

# ================= CONFIG =================
PLANTS = {
    "SAUNDATTI_WF":   (16.052, 74.648),
    "ACCIONA_TUP":    (14.228, 76.581),
    "NUZIVEEDU_BHM":  (14.156, 76.524),
    "HARPANA_WF":     (14.582, 76.885),
    "GADAG_CLUSTER":  (15.368, 75.632),
    "NTPC_KAR_Multi": (15.410, 76.190),

}

START_YEAR = 2023
END_YEAR   = 2023  # Cover 1 year for speed
OUTPUT_CSV = "data/raw/nwp_weather.csv"
os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)

def fetch_month(lat, lon, year, month):
    """Fetch hourly data for a single month and interpolate to 15-min"""
    url = "https://archive-api.open-meteo.com/v1/archive"
    start = f"{year}-{month:02d}-01"
    if month == 12:
        end = f"{year+1}-01-01"
    else:
        end = f"{year}-{month+1:02d}-01"
        
    params = {
        "latitude": lat, "longitude": lon,
        "start_date": start, "end_date": end,
        "hourly": "wind_speed_10m,wind_direction_10m,temperature_2m,surface_pressure,relative_humidity_2m,shortwave_radiation,cloud_cover",
        "timezone": "UTC"
    }
    
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=30)
            r.raise_for_status()
            data = r.json()
            
            # Convert hourly response to dataframe
            df_hourly = pd.DataFrame({
                "timestamp": pd.to_datetime(data["hourly"]["time"]),
                "wind_speed_ms": data["hourly"]["wind_speed_10m"],
                "wind_direction_deg": data["hourly"]["wind_direction_10m"],
                "temperature_c": data["hourly"]["temperature_2m"],
                "pressure_hpa": data["hourly"]["surface_pressure"],
                "humidity_pct": data["hourly"]["relative_humidity_2m"],
                "ghi_wm2": data["hourly"]["shortwave_radiation"],
                "cloud_cover_pct": data["hourly"]["cloud_cover"]
            })
            
            # Resample to 15-min and interpolate
            df_hourly = df_hourly.set_index("timestamp")
            df_15m = df_hourly.resample('15min').interpolate(method='linear').reset_index()
            return df_15m
            
        except Exception as e:
            if attempt == 2: raise
            time.sleep(2 ** attempt)

def process_and_save():
    all_dfs = []
    months = [(y, m) for y in range(START_YEAR, END_YEAR + 1) for m in range(1, 13)]
    
    print(f"🌍 Fetching 2 years of weather for {len(PLANTS)} plants, {len(months)} months...")
    
    for pid, (lat, lon) in PLANTS.items():
        for year, month in tqdm(months, desc=f"📍 {pid}"):
            df_15m = fetch_month(lat, lon, year, month)
            df_15m["plant_id"] = pid
            
            # Reorder
            df_15m = df_15m[["timestamp", "plant_id", "wind_speed_ms", "wind_direction_deg", "temperature_c", "pressure_hpa", "humidity_pct", "ghi_wm2", "cloud_cover_pct"]]
            df_15m = df_15m.dropna(subset=["wind_speed_ms"])
            all_dfs.append(df_15m)
            
            time.sleep(0.3)  # Respect rate limits
            
    df = pd.concat(all_dfs, ignore_index=True)
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"✅ Saved {len(df):,} rows → {OUTPUT_CSV}")
    print(f"📅 {df['timestamp'].min()} to {df['timestamp'].max()}")

if __name__ == "__main__":
    process_and_save()
