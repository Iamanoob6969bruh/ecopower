import pandas as pd
import numpy as np
from pvlib import solarposition, irradiance, atmosphere, clearsky
from pvlib.location import Location

def apply_solar_physics(df: pd.DataFrame, lat: float, lon: float, tilt: float, az: float, model_features: list = None) -> pd.DataFrame:
    """
    Applies comprehensive physics transformations to match the training pipeline.
    Calculates 40+ features including astronomy, clear-sky, rolling stats, and harmonics.
    """
    df = df.copy()
    
    # Ensure index is datetime and localized
    if df.index.tz is None:
        df.index = df.index.tz_localize('Asia/Kolkata')
    else:
        df.index = df.index.tz_convert('Asia/Kolkata')

    # 1. Solar Geometry
    # We use altitude=600 as a default if not provided
    loc = Location(lat, lon, altitude=600, tz='Asia/Kolkata')
    solpos = loc.get_solarposition(df.index)
    
    df['SZA']               = solpos['apparent_zenith']
    df['cos_SZA']           = np.cos(np.radians(df['SZA']))
    df['Solar_Azimuth']     = solpos['azimuth']
    df['Solar_Elevation']   = solpos['apparent_elevation']
    df['Solar_Declination'] = solarposition.declination_spencer71(df.index.dayofyear)
    df['AM_relative']       = atmosphere.get_relative_airmass(df['SZA'])
    df['Shading_Flag']      = (solpos['elevation'] > 0).astype(int)

    # 2. Clear Sky Irradiance (Ineichen model)
    # Use typical Linke Turbidity for the region
    month_to_lt = {1:2.5, 2:2.5, 3:3.5, 4:3.8, 5:3.8, 6:4.5,
                   7:4.5, 8:4.5, 9:4.2, 10:3.2, 11:3.0, 12:2.7}
    df['LT'] = df.index.month.map(month_to_lt)
    
    # Calculate clearsky for the whole range
    cs = loc.get_clearsky(df.index, model='ineichen', linke_turbidity=df['LT'])
    df['GHI_clear'] = cs['ghi']
    df['DNI_clear'] = cs['dni']
    
    # 3. Tilted Irradiance (POA) - Perez model
    # Note: We keep the original GHI/DNI/DHI in the dataframe as well
    dni_extra = irradiance.get_extra_radiation(df.index)
    poa = irradiance.get_total_irradiance(
        surface_tilt=tilt,
        surface_azimuth=az,
        solar_zenith=df['SZA'],
        solar_azimuth=df['Solar_Azimuth'],
        dni=df['DNI'],
        ghi=df['GHI'],
        dhi=df['DHI'],
        dni_extra=dni_extra,
        airmass=df['AM_relative'],
        model='perez'
    )
    # The model expects 'GHI' to be the primary irradiance feature, 
    # but in the training pipeline it was sometimes the tilted value.
    # However, 'GHI', 'DNI', 'DHI' are also features.
    # To avoid confusion, we preserve raw GHI and add POA_global as a separate feature if needed.
    # Actually, the model features list includes 'GHI', 'DNI', 'DHI'.
    
    # 4. Indices and Harmonics
    df['Clearness_Index'] = np.clip(df['GHI'] / df['GHI_clear'].replace(0, np.nan), 0, 1.2).fillna(0)
    
    doy = df.index.dayofyear
    df['hour_sin'] = np.sin(2 * np.pi * df.index.hour / 24)
    df['hour_cos'] = np.cos(2 * np.pi * df.index.hour / 24)
    df['doy_sin']  = np.sin(2 * np.pi * doy / 365)
    df['doy_cos']  = np.cos(2 * np.pi * doy / 365)
    df['doy_sin2'] = np.sin(4 * np.pi * doy / 365)
    df['doy_cos2'] = np.cos(4 * np.pi * doy / 365)

    # 5. Rolling and Lags (Temporal context)
    # Since we have at least 24h of data in the fetcher, we can compute these
    df['GHI_lag1'] = df['GHI'].shift(1).bfill()
    df['GHI_lag2'] = df['GHI'].shift(2).bfill()
    df['clearness_lag1'] = df['Clearness_Index'].shift(1).bfill()
    
    # Rolling means (assuming 15-min or 1-hour frequency, Open-Meteo is 1-hour but we interpolate in scheduler)
    # We use time-based windows for robustness
    df['GHI_rollmean_45m'] = df['GHI'].rolling('45min', min_periods=1).mean()
    df['GHI_rollmean_1h']  = df['GHI'].rolling('1h', min_periods=1).mean()
    df['GHI_rollmean_3h']  = df['GHI'].rolling('3h', min_periods=1).mean()
    df['GHI_rollstd_1h']   = df['GHI'].rolling('1h', min_periods=1).std().fillna(0)
    
    # Derivatives
    df['dGHI_dt'] = df['GHI'].diff().fillna(0)
    df['dTCC_dt'] = df['TCC'].diff().fillna(0)
    
    # 6. Operational Mocking (Matches training pipeline defaults)
    df['Consecutive_dark_steps'] = (df['GHI'] < 5).astype(int)
    # Simple cumulative sum reset for consecutive dark steps
    df['Consecutive_dark_steps'] = df.groupby((df['GHI'] >= 5).cumsum())['Consecutive_dark_steps'].cumsum()
    
    df['rolling_gen_efficiency'] = 0.85 
    df['rolling_PR_proxy'] = 0.80
    df['Days_Since_Rain'] = 5 # Constant for now
    
    # Night filter safety
    night_mask = (df['SZA'] >= 89) | (df['GHI_clear'] <= 0)
    df.loc[night_mask, ['GHI', 'DNI', 'DHI', 'Clearness_Index']] = 0.0

    # 7. Final Feature Alignment
    if model_features:
        for col in model_features:
            if col not in df.columns:
                # Map alternate names if necessary
                if col == 'Dew_Point':
                    # Calculate Dew Point from Temp and Humidity if we have them
                    if 'Temperature' in df.columns and 'Relative_Humidity' in df.columns:
                        T, RH = df['Temperature'], df['Relative_Humidity']
                        df['Dew_Point'] = T - ((100 - RH) / 5.0) # Simple approximation
                    else:
                        df[col] = 0.0
                elif col == 'Wind_Speed':
                    df['Wind_Speed'] = df.get('Wind_Speed', df.get('Wind_Speed_10m', 0))
                else:
                    df[col] = 0.0
                
    return df
