import numpy as np
import pandas as pd
from datetime import datetime
import pvlib
from pvlib.location import Location
from src.data.database import get_now_ist

def generate_solar_actual(weather_dict: dict, plant: dict, global_seed: int = 42) -> list:
    """
    Simulates actual SCADA generation by using physics-based pvlib calculations.
    This replaces the previous noise-on-prediction method with a real physical model.
    """
    if not weather_dict:
        return []

    # 1. Convert weather_dict to DataFrame and localize timezone
    df = pd.DataFrame.from_dict(weather_dict, orient='index')
    # Open-Meteo returns ISO strings. We must ensure they are treated as Asia/Kolkata
    df.index = pd.to_datetime(df.index)
    if df.index.tz is None:
        df.index = df.index.tz_localize('Asia/Kolkata')
    else:
        df.index = df.index.tz_convert('Asia/Kolkata')
        
    df.sort_index(inplace=True)

    # 2. Physics Constants
    dc_capacity_mw = plant.get('dc_capacity_mw', plant.get('capacity_kw', 0) / 1000.0 * 1.2)
    ac_capacity_mw = plant.get('ac_capacity_mw', plant.get('capacity_kw', 0) / 1000.0)
    P_dc0 = dc_capacity_mw * 1e6  # Watts
    ac_limit = ac_capacity_mw * 1e6 # Watts
    
    gamma_pdc = -0.004             # Temp coefficient
    sys_loss = 0.97                # Wiring/Mismatch losses
    aging_rate = 0.005             # 0.5% yearly degradation
    commissioning_year = 2016      # Base year for aging
    tilt = plant.get('tilt', 15.0)
    azimuth = plant.get('azimuth', 180.0)
    NOCT = 44.0                    # Nominal Operating Cell Temp
    lat, lon = plant['latitude'], plant['longitude']

    # 3. Solar Geometry & POA
    # We assume a default altitude if not provided
    loc = Location(lat, lon, altitude=600)
    solpos = loc.get_solarposition(df.index)
    
    # Map weather columns (Open-Meteo fields)
    ghi = df.get('shortwave_radiation', df.get('GHI', 0))
    dni = df.get('direct_normal_irradiance', df.get('DNI', 0))
    dhi = df.get('diffuse_radiation', df.get('DHI', 0))
    temp = df.get('temperature_2m', df.get('Temperature', 25))

    poa = pvlib.irradiance.get_total_irradiance(
        surface_tilt=tilt,
        surface_azimuth=azimuth,
        solar_zenith=solpos['apparent_zenith'],
        solar_azimuth=solpos['azimuth'],
        dni=dni,
        ghi=ghi,
        dhi=dhi
    )
    df['POA'] = poa['poa_global'].fillna(0)

    # 4. Thermal & Power Calculations
    # Calculate Cell Temperature
    df['T_cell'] = temp + df['POA'] * (NOCT - 20.0) / 800.0
    
    # Aging Factor
    years_elapsed = get_now_ist().year - commissioning_year
    aging_factor = np.clip(1 - aging_rate * years_elapsed, 0.80, 1.0)

    # DC Power logic
    df['P_dc'] = P_dc0 * (df['POA'] / 1000.0) * (1 + gamma_pdc * (df['T_cell'] - 25.0)) * aging_factor * sys_loss
    
    # AC Power with Inverter Clipping
    df['P_ac'] = np.minimum(df['P_dc'] * 0.98, ac_limit).clip(lower=0)

    # 5. Add "Chaos" (Sensor Jitter & Dropouts)
    # Seed per plant for deterministic but different noise
    plant_seed = global_seed + hash(plant['id']) % 10000
    rng = np.random.default_rng(plant_seed)
    
    jitter = rng.normal(1.0, 0.015, len(df))
    df['actual_kw'] = (df['P_ac'] / 1000.0) * jitter
    
    # Night mask (Force 0 if sun is too low)
    df.loc[solpos['apparent_zenith'] > 88, 'actual_kw'] = 0.0
    
    # Occasional SCADA dropouts (0.2% chance)
    dropouts = rng.random(len(df)) < 0.002
    df.loc[dropouts, 'actual_kw'] = 0.0

    # 6. Format result for backend pipeline
    actuals = []
    for ts, row in df.iterrows():
        actuals.append({
            "timestamp": ts,
            "actual_kw": round(float(row['actual_kw']), 2)
        })
        
    return actuals

def generate_wind_actual(weather_dict: dict, plant: dict, global_seed: int = 42) -> list:
    """
    Simulates actual wind generation using a standard power curve logic.
    """
    if not weather_dict:
        return []

    df = pd.DataFrame.from_dict(weather_dict, orient='index')
    df.index = pd.to_datetime(df.index)
    if df.index.tz is None:
        df.index = df.index.tz_localize('Asia/Kolkata')
    else:
        df.index = df.index.tz_convert('Asia/Kolkata')
    df.sort_index(inplace=True)

    # 1. Physics Parameters
    ac_capacity_mw = plant.get('ac_capacity_mw', plant.get('capacity_kw', 1000) / 1000.0)
    hub_height = plant.get('hub_height_m', 80.0)
    
    # Power Curve Parameters (Simplified IEC Class II)
    cut_in = 3.0   # m/s
    rated = 12.0   # m/s
    cut_out = 25.0 # m/s
    
    # 2. Wind Speed Adjustment (Power Law)
    # Open-Meteo gives 10m wind speed if we didn't fetch higher
    v_ref = df.get('wind_speed_10m', 0)
    alpha = 0.143 # Hellmann exponent
    v_hub = v_ref * (hub_height / 10.0)**alpha
    
    # Use 80m/100m/120m if available
    if 'wind_speed_80m' in df.columns and hub_height <= 90:
        v_hub = df['wind_speed_80m']
    elif 'wind_speed_100m' in df.columns and 90 < hub_height <= 110:
        v_hub = df['wind_speed_100m']
    elif 'wind_speed_120m' in df.columns and hub_height > 110:
        v_hub = df['wind_speed_120m']

    # 3. Power Curve Logic
    def calculate_p_norm(v):
        if v < cut_in or v > cut_out:
            return 0.0
        if v >= rated:
            return 1.0
        # Polynomial fit between cut-in and rated
        return ((v - cut_in) / (rated - cut_in))**3

    df['p_norm'] = v_hub.apply(calculate_p_norm)
    
    # 4. Add "Chaos"
    plant_seed = global_seed + hash(plant['id']) % 10000
    rng = np.random.default_rng(plant_seed)
    
    # Wind has more turbulence/variability
    jitter = rng.normal(0.95, 0.05, len(df))
    df['actual_kw'] = (df['p_norm'] * ac_capacity_mw * 1000.0) * jitter
    
    # Occasional downtime
    downtime = rng.random(len(df)) < 0.005
    df.loc[downtime, 'actual_kw'] = 0.0

    # 5. Format result
    actuals = []
    for ts, row in df.iterrows():
        actuals.append({
            "timestamp": ts.to_pydatetime().replace(tzinfo=None),
            "actual_kw": max(0, round(float(row['actual_kw']), 2))
        })
        
    return actuals
