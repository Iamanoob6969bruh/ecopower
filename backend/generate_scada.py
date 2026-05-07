import pandas as pd
import numpy as np
import os

OUTPUT_CSV = "data/raw/scada_generation.csv"
os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)

PLANTS = {
    "SAUNDATTI_WF":   {"cap": 84.0,  "lat": 16.052, "lon": 74.648, "hub": 90, "type": "wind"},
    "ACCIONA_TUP":    {"cap": 56.1,  "lat": 14.228, "lon": 76.581, "hub": 85, "type": "wind"},
    "NUZIVEEDU_BHM":  {"cap": 50.4,  "lat": 14.156, "lon": 76.524, "hub": 80, "type": "wind"},
    "HARPANA_WF":     {"cap": 40.0,  "lat": 14.582, "lon": 76.885, "hub": 90, "type": "wind"},
    "GADAG_CLUSTER":  {"cap": 302.0, "lat": 15.368, "lon": 75.632, "hub": 100, "type": "wind"},
    "NTPC_KAR_Multi": {"cap": 960.0, "lat": 15.410, "lon": 76.190, "hub": 105, "type": "wind"},
    "kspdcl_pavagada": {"cap": 2050.0, "lat": 14.250, "lon": 77.450, "hub": 0, "type": "solar"},
    "kpcl_shivanasamudra": {"cap": 15.0, "lat": 12.300, "lon": 77.170, "hub": 0, "type": "solar"}
}

# Generic 2.5MW turbine power curve (v_in, v_out)
VCUTIN = 3.0
VRATED = 11.5
VCUTOFF = 25.0
PRATED = 2.5  # MW per turbine
NP250 = {84:34, 56.1:22, 50.4:20, 40:16, 302:120, 960:384}

def wind_to_power(ws_10m, hub_h):
    """Power law scaling + standard power curve"""
    alpha = 0.14
    ws_hub = ws_10m * (hub_h / 10) ** alpha
    if ws_hub < VCUTIN or ws_hub > VCUTOFF:
        return 0.0
    elif ws_hub >= VRATED:
        return PRATED
    else:
        # Cubic interpolation between cut-in and rated
        return PRATED * ((ws_hub - VCUTIN) / (VRATED - VCUTIN)) ** 3

def solar_to_power(ghi, cap):
    """Simple GHI to Power model (Eff ~15%)"""
    if ghi <= 0: return 0.0
    # Max GHI approx 1000 W/m2
    plf = min(max(ghi / 1000, 0), 1)
    return plf * cap

def main():
    weather = pd.read_csv("data/raw/nwp_weather.csv")
    weather["timestamp"] = pd.to_datetime(weather["timestamp"])
    
    records = []
    np.random.seed(42)
    
    for pid, info in PLANTS.items():
        cap = info["cap"]
        hub = info["hub"]
        n_turbines = NP250.get(int(cap), int(cap/2.5))
        
        plant_df = weather[weather["plant_id"] == pid].copy()
        plant_df = plant_df.sort_values("timestamp").reset_index(drop=True)
        
        # Availability: 97% uptime, 2 scheduled 48hr maint/year
        avail = np.ones(len(plant_df), dtype=int)
        maint_idx = np.random.choice(len(plant_df), 2, replace=False)
        for idx in maint_idx:
            avail[idx:idx+192] = 0  # 192 * 15min = 48hrs
            
        # Calculate generation
        if info["type"] == "wind":
            ws = plant_df["wind_speed_ms"].values
            power_per_t = np.array([wind_to_power(v, hub) for v in ws])
            gen_mw = (power_per_t * n_turbines * avail)
        else:
            ghi = plant_df["ghi_wm2"].fillna(0).values
            gen_mw = np.array([solar_to_power(v, cap) for v in ghi]) * avail
            
        gen_mw = np.clip(gen_mw, 0, cap)
        gen_mw = np.round(gen_mw, 2)
        
        for i in range(len(plant_df)):
            records.append({
                "timestamp": plant_df.iloc[i]["timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
                "plant_id": pid,
                "plant_type": info["type"],
                "installed_capacity_mw": cap,
                "generation_mw": gen_mw[i],
                "availability_flag": avail[i],
                "latitude": PLANTS[pid]["lat"],
                "longitude": PLANTS[pid]["lon"],
                "hub_height_m": hub
            })
                
    df = pd.DataFrame(records)
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"✅ Saved {len(df):,} rows → {OUTPUT_CSV}")
    print(f"📊 Avg Capacity Factor: {(df['generation_mw']/df['installed_capacity_mw']).mean():.2%}")

if __name__ == "__main__":
    main()
