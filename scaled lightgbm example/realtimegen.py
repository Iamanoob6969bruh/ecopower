import requests
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import pvlib
from pvlib.location import Location
from datetime import datetime

def get_actual_generation(capacity_mw, lat, lon, alt=600):
    # 1. System Constants
    P_dc0 = capacity_mw * 1e6      # 50 MW DC
    dc_ac_ratio = 1.2              
    ac_limit = P_dc0 / dc_ac_ratio # ~41.67 MW AC (THIS IS THE MAX ALLOWED)
    gamma_pdc = -0.004             # Temp loss
    sys_loss = 0.97                
    aging_rate = 0.005             
    commissioning_year = 2016      
    tilt, azimuth = 15, 180        
    NOCT = 44.0                    

    # 2. Fetch Real-time Weather
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        # CRITICAL FIX: direct_normal_irradiance MUST be used for 'dni'
        "hourly": "temperature_2m,shortwave_radiation,direct_normal_irradiance,diffuse_radiation",
        "timezone": "Asia/Kolkata",
        "forecast_days": 1
    }
    
    try:
        response = requests.get(url, params=params)
        data = response.json()
        df = pd.DataFrame(data["hourly"])
        df['datetime'] = pd.to_datetime(df['time'])
        df.set_index('datetime', inplace=True)
    except Exception as e:
        print(f"Error: {e}")
        return

    # 3. Physics Logic
    loc = Location(lat, lon, altitude=alt, tz="Asia/Kolkata")
    solpos = loc.get_solarposition(df.index)
    
    # Calculate Irradiance on Panel
    poa = pvlib.irradiance.get_total_irradiance(
        surface_tilt=tilt,
        surface_azimuth=azimuth,
        solar_zenith=solpos['apparent_zenith'],
        solar_azimuth=solpos['azimuth'],
        dni=df['direct_normal_irradiance'], # Fixed
        ghi=df['shortwave_radiation'],
        dhi=df['diffuse_radiation']
    )
    df['POA'] = poa['poa_global'].fillna(0)

    # 4. DC to AC Power Transformation
    df['T_cell'] = df['temperature_2m'] + df['POA'] * (NOCT - 20.0) / 800.0
    years_elapsed = datetime.now().year - commissioning_year
    aging_factor = np.clip(1 - aging_rate * years_elapsed, 0.80, 1.0)

    # Raw DC Power
    df['P_dc'] = P_dc0 * (df['POA'] / 1000.0) * (1 + gamma_pdc * (df['T_cell'] - 25.0)) * aging_factor * sys_loss
    
    # CRITICAL FIX: Enforce the Inverter Limit (Clipping)
    # This ensures the orange line never crosses the 41.67MW threshold
    df['P_ac'] = np.minimum(df['P_dc'] * 0.98, ac_limit).clip(lower=0)
    
    # Final SCADA Output in MW
    df['Generation_MW'] = df['P_ac'] / 1e6
    
    # Night filter
    df.loc[solpos['apparent_zenith'] > 88, 'Generation_MW'] = 0

    # 5. Plotting
    plt.figure(figsize=(10, 5))
    # FIX: Plot Generation_MW, which is the clipped AC value
    plt.plot(df.index, df['Generation_MW'], color='#f39c12', label='Actual SCADA (MW)', linewidth=2.5)
    plt.fill_between(df.index, df['Generation_MW'], color='#f39c12', alpha=0.15)
    
    # Reference Line for the Limit
    plt.axhline(y=ac_limit/1e6, color='red', linestyle='--', alpha=0.6, label=f'Inverter Cap ({round(ac_limit/1e6, 1)}MW)')
    
    plt.title(f"FIXED SCADA Actuals: {capacity_mw}MW Plant (Clipped at {round(ac_limit/1e6, 1)}MW)")
    plt.ylabel("Generation (MW)")
    plt.grid(True, linestyle=':', alpha=0.5)
    plt.legend()
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    get_actual_generation(capacity_mw=50, lat=15.66, lon=76.01)