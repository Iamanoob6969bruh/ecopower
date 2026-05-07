import pandas as pd
from pathlib import Path

# -------------------------------------------------------------------
# CONFIGURATION: Column Mapping Dictionary
# Updated to match your master_data.csv column names exactly.
# -------------------------------------------------------------------
COLUMN_MAPPING = {
    # Time and ID (Shared)
    'timestamp': 'timestamp',
    'plant_id': 'plant_id',
    
    # SCADA generation mappings
    'capacity_mw': 'installed_capacity_mw',
    'power_output_mw': 'generation_mw', 
    'latitude': 'latitude',
    'longitude': 'longitude',
    'hub_height_m': 'hub_height_m',
    
    # NWP Weather mappings
    'temperature_c': 'temperature_c',
    'wind_speed_80m': 'wind_speed_80m',
    'wind_speed_120m': 'wind_speed_120m',
    'wind_direction_deg': 'wind_direction_deg',
    'humidity_pct': 'humidity_pct',
}

def split_energy_data():
    root_dir = Path(__file__).resolve().parents[1]
    input_path = root_dir / 'master_data.csv'
    output_dir = root_dir / 'data' / 'raw'
    
    print(f"Loading {input_path}...")
    
    try:
        df = pd.read_csv(input_path)
    except FileNotFoundError:
        print(f"Error: 'master_data.csv' not found.")
        return

    # 1. Rename columns
    df = df.rename(columns=COLUMN_MAPPING)

    # 2. Add missing required columns
    if 'plant_type' not in df.columns:
        df['plant_type'] = 'wind'
        
    if 'availability_flag' not in df.columns:
        df['availability_flag'] = 1
        
    # IMPORTANT: The model needs a column called 'wind_speed_ms' for its internal math.
    # We will use 'wind_speed_80m' as our standard speed if 'wind_speed_ms' is missing.
    if 'wind_speed_ms' not in df.columns and 'wind_speed_80m' in df.columns:
        print("-> Using wind_speed_80m as the primary wind_speed_ms factor")
        df['wind_speed_ms'] = df['wind_speed_80m']

    # 3. Standardize timestamp
    df['timestamp'] = pd.to_datetime(df['timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S')

    # 4. Define Target Columns
    # CRITICAL: generation_mw must ONLY be in the SCADA file to avoid merge conflicts
    scada_cols = [
        'timestamp', 'plant_id', 'plant_type', 'installed_capacity_mw', 
        'generation_mw', 'availability_flag', 'latitude', 'longitude', 'hub_height_m'
    ]
    
    nwp_cols = [
        'timestamp', 'plant_id', 'temperature_c', 'wind_speed_ms', 
        'wind_speed_80m', 'wind_speed_120m', 'wind_direction_deg', 'humidity_pct'
    ]

    # Filter only existing columns
    final_scada = [c for c in scada_cols if c in df.columns]
    final_nwp = [c for c in nwp_cols if c in df.columns]

    # 5. Save
    scada_path = output_dir / 'scada_generation.csv'
    nwp_path = output_dir / 'nwp_weather.csv'
    
    df[final_scada].to_csv(scada_path, index=False)
    df[final_nwp].to_csv(nwp_path, index=False)
    
    print(f"\nSuccess!")
    print(f" -> scada_generation.csv ({len(final_scada)} columns)")
    print(f" -> nwp_weather.csv ({len(final_nwp)} columns)")
    print("\nTraining ready. Close all CSV files before running the trainer!")

if __name__ == "__main__":
    split_energy_data()
