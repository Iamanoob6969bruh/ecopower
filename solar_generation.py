import pandas as pd
import numpy as np
import pvlib
from pvlib import solarposition, irradiance, atmosphere, clearsky
from pvlib.location import Location
import scipy.signal as signal
import warnings

warnings.filterwarnings('ignore')

# ============================================================================
# 0. SYSTEM CONFIGURATION & CONSTANTS
# ============================================================================
lat, lon, alt = 15.66, 76.01, 628
tilt, azimuth = 15, 180
P_dc0         = 50e6           # 50 MW DC nameplate
gamma_pdc     = -0.004         # %/°C temperature coefficient
dc_ac_ratio   = 1.2
ac_limit      = P_dc0 / dc_ac_ratio   # ~41.67 MW AC limit
sys_loss      = 0.97           # DC wiring, mismatch, etc.
aging_rate    = 0.005          # 0.5%/year panel degradation
commissioning_year = 2016

# Lowered shutdown thresholds to induce more thermal events
INV_SHUTDOWN_TEMP  = 68.0
INV_RESTART_TEMP   = 63.0

rng = np.random.default_rng(42)

# ============================================================================
# 1. READ MERGED CSV & BASE FEATURES
# ============================================================================
print("1. Loading Data & Computing Base Astronomy (Local Time Mode)...")
df = pd.read_csv('data.csv')
df['datetime'] = pd.to_datetime(df[['Year', 'Month', 'Day', 'Hour', 'Minute']])
df.set_index('datetime', inplace=True)

# --- THE FIX: NSRDB is already IST. Localize only. ---
# Strip any existing TZ info just in case, then stamp strictly as Asia/Kolkata
if df.index.tz is not None:
    df.index = df.index.tz_localize(None)
df.index = df.index.tz_localize('Asia/Kolkata') 

df = df[df['Fill Flag'].isin([0, 2])].copy()
df.sort_index(inplace=True)

df['Latitude']  = lat
df['Longitude'] = lon
df['Altitude']  = alt
df['Tilt']      = tilt
df['Azimuth']   = azimuth

loc    = Location(lat, lon, tz='Asia/Kolkata', altitude=alt)
solpos = loc.get_solarposition(df.index, pressure=df['Pressure'] * 100)

df['SZA']              = solpos['apparent_zenith']
df['cos_SZA']          = np.cos(np.radians(df['SZA']))
df['Solar_Azimuth']    = solpos['azimuth']
df['Solar_Elevation']  = solpos['apparent_elevation']
df['Solar_Declination']= solarposition.declination_spencer71(df.index.dayofyear)
df['Shading_Flag']     = (solpos['elevation'] > 0).astype(int)

# Temporal harmonics (Now based on IST hours)
df['doy']      = df.index.dayofyear
df['hour_sin'] = np.sin(2 * np.pi * df.index.hour / 24)
df['hour_cos'] = np.cos(2 * np.pi * df.index.hour / 24)
df['doy_sin']  = np.sin(2 * np.pi * df['doy'] / 365)
df['doy_cos']  = np.cos(2 * np.pi * df['doy'] / 365)
df['doy_sin2'] = np.sin(4 * np.pi * df['doy'] / 365)
df['doy_cos2'] = np.cos(4 * np.pi * df['doy'] / 365)

df['AM_relative'] = atmosphere.get_relative_airmass(df['SZA'])

month_to_lt = {1:2.5, 2:2.5, 3:3.5, 4:3.8, 5:3.8, 6:4.5,
               7:4.5, 8:4.5, 9:4.2, 10:3.2, 11:3.0, 12:2.7}
df['Linke_Turbidity'] = df.index.month.map(month_to_lt)

cs_frames = []
for month, lt in month_to_lt.items():
    idx_m = df.index[df.index.month == month]
    if len(idx_m) > 0:
        cs_m = loc.get_clearsky(idx_m, model='ineichen', linke_turbidity=lt)
        cs_frames.append(cs_m)
cs = pd.concat(cs_frames).sort_index()
df['GHI_clear'] = cs['ghi'].reindex(df.index).fillna(0)
df['DNI_clear'] = cs['dni'].reindex(df.index).fillna(0)

cloud_mapping = {
    0:  (0.00, 0.00, 0.00, 0.00), 1:  (0.10, 0.05, 0.03, 0.02),
    2:  (1.00, 1.00, 0.00, 0.00), 3:  (1.00, 1.00, 0.00, 0.00),
    4:  (1.00, 0.80, 0.20, 0.00), 5:  (1.00, 0.30, 0.40, 0.30),
    6:  (1.00, 0.00, 0.00, 1.00), 7:  (0.40, 0.00, 0.00, 0.40),
    8:  (1.00, 0.30, 0.30, 0.40), 9:  (1.00, 0.20, 0.30, 0.50),
    10: (0.50, 0.20, 0.15, 0.15), 11: (0.00, 0.00, 0.00, 0.00),
    12: (0.00, 0.00, 0.00, 0.00), -15:(0.00, 0.00, 0.00, 0.00),
}
cloud_df = pd.DataFrame([cloud_mapping[ct] for ct in df['Cloud Type']],
                        columns=['TCC', 'Low_Cloud', 'Mid_Cloud', 'High_Cloud'], index=df.index)
df = pd.concat([df, cloud_df], axis=1)
df['Cloud_Transmittance'] = 1 - 0.75 * (df['TCC'] ** 3.4)

hour_frac = df.index.hour + df.index.minute / 60.0
df['AOD'] = 0.15 + 0.15 * np.exp(-0.5 * ((hour_frac - 7) / 2.5) ** 2) + 0.10 * np.exp(-0.5 * ((hour_frac - 17) / 2.0) ** 2)
df['AOD'] *= df['Linke_Turbidity'] / 3.5

# ============================================================================
# 2. LAYER 0: REALISTIC SENSOR NOISE (HIGH CHAOS)
# ============================================================================
print("2. Executing Layer 0: High-Chaos Sensor Noise...")

def make_ar1_noise(n, phi=0.7, sigma=0.01):
    white = rng.normal(0, sigma, n)
    return signal.lfilter([1], [1, -phi], white)

df['SZA_jit']     = np.clip(df['SZA'] + make_ar1_noise(len(df), 0.8, 0.15), 0, 90)
df['Azimuth_jit'] = (df['Solar_Azimuth'] + make_ar1_noise(len(df), 0.8, 0.15)) % 360

# CHAOS TWEAK 1: Massive GHI sensor noise (6% error instead of 0.5%)
df['GHI_dirty'] = np.clip(df['GHI'] + make_ar1_noise(len(df), 0.85, 0.06) * 800, 0, 1500)
df['DNI_dirty'] = np.clip(df['DNI'] + make_ar1_noise(len(df), 0.85, 0.08) * 800, 0, 1200)
df['DHI_dirty'] = np.clip(df['DHI'] + make_ar1_noise(len(df), 0.85, 0.05) * 200, 0, 800)

df['Clearness_Index'] = np.clip(df['GHI_dirty'] / df['GHI_clear'].replace(0, np.nan), 0, 1.2).fillna(0)

df['Regime'] = 'PartlyCloudy'
df.loc[(df['TCC'] < 0.1) & (df['Clearness_Index'] > 0.7), 'Regime'] = 'Clear'
df.loc[df['TCC'] > 0.8, 'Regime'] = 'Overcast'
monsoon_mask = (df.index.month.isin([6, 7, 8, 9]) & (df['Relative Humidity'] > 75) & (df['TCC'] > 0.5))
df.loc[monsoon_mask, 'Regime'] = 'Monsoon'

df['Wind_Speed_dirty'] = np.clip(df['Wind Speed'] + make_ar1_noise(len(df), 0.6, 0.8), 0, 35)

# ============================================================================
# 3. LAYER 1: MARKOV CLOUD SHADOWS & POA
# ============================================================================
print("3. Executing Layer 1: Cloud Shadows & True POA Physics...")

shadow_state = np.zeros(len(df), dtype=int)
p_sun_to_shadow, p_shadow_to_sun = 0.08, 0.15   
partly_cloudy_idx = (df['Regime'] == 'PartlyCloudy').values
state = 0
for i in range(len(df)):
    if partly_cloudy_idx[i]:
        if state == 0 and rng.random() < p_sun_to_shadow: state = 1
        elif state == 1 and rng.random() < p_shadow_to_sun: state = 0
    else: state = 0
    shadow_state[i] = state
df['Shadow_State'] = shadow_state

shadow_dni_factor = np.where(shadow_state == 1, rng.uniform(0.1, 0.4, len(df)), 1.0)
shadow_ghi_factor = np.where(shadow_state == 1, rng.uniform(0.4, 0.7, len(df)), 1.0)

df['GHI_dirty'] *= shadow_ghi_factor
df['DNI_dirty'] *= shadow_dni_factor

ghi_phys = df['GHI'] * shadow_ghi_factor
dni_phys = df['DNI'] * shadow_dni_factor
dhi_phys = df['DHI']

dni_extra = irradiance.get_extra_radiation(df.index)

poa = irradiance.get_total_irradiance(
    surface_tilt=tilt, surface_azimuth=azimuth,
    solar_zenith=df['SZA'], solar_azimuth=df['Solar_Azimuth'],
    dni=dni_phys, ghi=ghi_phys, dhi=dhi_phys,
    dni_extra=dni_extra, airmass=df['AM_relative'],
    model='perez', model_perez='allsitescomposite1990'
)
df['POA_base'] = poa['poa_global'].fillna(0)

sigma_map = {'Clear': 0.005, 'PartlyCloudy': 0.04, 'Overcast': 0.015, 'Monsoon': 0.03}
df['poa_noise'] = 0.0
for reg, sig in sigma_map.items():
    mask = df['Regime'] == reg
    if mask.sum() > 0: df.loc[mask, 'poa_noise'] = make_ar1_noise(mask.sum(), 0.7, sig) * 1000

df['POA_noisy']  = np.clip(df['POA_base'] + df['poa_noise'], 0, 1500)
df['POA_smooth'] = df['POA_noisy'].ewm(span=3, adjust=False).mean()

dtcc = df['TCC'].diff()
spike_raw = ((dtcc < -0.3) & (df['TCC'] < 0.7) & (df['SZA'] < 70) & 
             (df['POA_smooth'] > 100) & (shadow_state == 0) & (rng.random(len(df)) < 0.06))

sunrise_mask = (df['SZA'] < 88) & (df['SZA'].shift(1, fill_value=90) >= 88)
minutes_since_sunrise = pd.Series(0.0, index=df.index)
sunrise_count = 0
for i, is_sr in enumerate(sunrise_mask):
    if is_sr: sunrise_count = 0
    sunrise_count += 30 * (0 if is_sr else 1)
    minutes_since_sunrise.iloc[i] = sunrise_count

spike_mask = spike_raw & (minutes_since_sunrise >= 90)
if spike_mask.sum() > 0: df.loc[spike_mask, 'POA_smooth'] *= rng.uniform(1.10, 1.20, size=spike_mask.sum())

# Aggressive Night Mask: 89 degrees + NaN protection + Clear Sky zero-check
night_mask = (df['SZA'] >= 89) | (df['SZA'].isna()) | (df['GHI_clear'] <= 0)
df.loc[night_mask, ['POA_base','POA_noisy','POA_smooth', 'GHI_dirty','DNI_dirty','DHI_dirty']] = 0.0

NOCT = 44.0
raw_tcell = df['Temperature'] + df['POA_smooth'] * (NOCT - 20.0) / 800.0
alpha_arr  = np.where(minutes_since_sunrise <= 120, 0.06, 0.12)
tcell_vals = raw_tcell.values.copy()
for i in range(1, len(tcell_vals)):
    tcell_vals[i] = alpha_arr[i] * tcell_vals[i] + (1 - alpha_arr[i]) * tcell_vals[i-1]
df['T_cell_eff'] = np.clip(tcell_vals, -20, 85)

# ============================================================================
# 4. LAYER 2: SEVERE SOILING, DEGRADATION & OUTAGES
# ============================================================================
print("4. Executing Layer 2: Severe Soiling & Plant Micro-Outages...")

daily_rh  = df['Relative Humidity'].resample('D').mean()
daily_tcc = df['TCC'].resample('D').mean()
monsoon_d = pd.Series(df.index.month.isin([6,7,8,9]), index=df.index).resample('D').mean()
rain_prob = (0.25 * daily_rh/100 + 0.35 * daily_tcc + 0.40 * monsoon_d).clip(0.05, 0.85)
rain_amount = np.where(rng.random(len(rain_prob)) < rain_prob.values, rng.exponential(6, size=len(rain_prob)), 0.0)
df_daily = pd.DataFrame({'Rain_mm': rain_amount}, index=rain_prob.index)

soiling, pr_drift, days_since_rain_list = [], [], []
curr_soil, curr_pr, days_dry = 0.02, 1.00, 0

for i, rain in enumerate(df_daily['Rain_mm']):
    if rain >= 5.0:
        curr_soil, days_dry = 0.003, 0
    elif rain >= 2.0:
        curr_soil, days_dry = max(curr_soil - 0.03, 0.005), 0
    elif rain >= 0.5:
        curr_soil += 0.0005
        days_dry += 1
    else:
        # CHAOS TWEAK 2: Dust accumulates much faster
        month = df_daily.index[i].month
        dust_rate = 0.0025 if month in [6,7,8,9] else 0.0015
        curr_soil += dust_rate
        days_dry += 1

    # Scheduled cleaning is rare (every 45 days)
    if i % 45 == 0 and i > 0:
        curr_soil = max(0, curr_soil - 0.05)
        days_dry = 0

    curr_soil = np.clip(curr_soil, 0, 0.25) # Max 25% loss due to dirt
    curr_pr = np.clip(curr_pr + rng.normal(0, 0.0015), 0.88, 1.05)

    soiling.append(curr_soil)
    pr_drift.append(curr_pr)
    days_since_rain_list.append(days_dry)

df_daily['Soiling']          = soiling
df_daily['PR_Drift']         = pr_drift
df_daily['Days_Since_Rain']  = days_since_rain_list

df_daily['Soiling']         = df_daily['Soiling'].shift(1).fillna(0.02)
df_daily['PR_Drift']        = df_daily['PR_Drift'].shift(1).fillna(1.0)
df_daily['Days_Since_Rain'] = df_daily['Days_Since_Rain'].shift(1).fillna(0)

df['Soiling_Loss']    = df.index.normalize().map(df_daily['Soiling'])
df['PR_Drift']        = df.index.normalize().map(df_daily['PR_Drift'])
df['Days_Since_Rain'] = df.index.normalize().map(df_daily['Days_Since_Rain'])

# CHAOS TWEAK 3: Plant Availability (Micro-outages of strings/inverters)
# Simulates random drops of 2% to 12% capacity that persist for days
plant_availability = np.clip(1.0 - np.abs(make_ar1_noise(len(df), 0.995, 0.03)), 0.85, 1.0)
df['Plant_Availability'] = plant_availability

# ============================================================================
# 5. LAYER 3: GRID OPERATIONS, WIND STOW & DC→AC
# ============================================================================
print("5. Executing Layer 3: High-Frequency Grid Curtailments...")

high_wind = df['Wind Speed'] > 14.0   
stow_state = np.zeros(len(df), dtype=bool)
stow_on, below_count = False, 0
for i in range(len(df)):
    if high_wind.iloc[i]:
        stow_on, below_count = True, 0
    else:
        below_count += 1
        if below_count >= 2: stow_on = False
    stow_state[i] = stow_on

stow_mask = pd.Series(stow_state, index=df.index)
if stow_mask.sum() > 0:
    poa_flat = irradiance.get_total_irradiance(
        surface_tilt=0, surface_azimuth=180,
        solar_zenith=df['SZA'], solar_azimuth=df['Solar_Azimuth'],
        dni=dni_phys, ghi=ghi_phys, dhi=dhi_phys,
        dni_extra=dni_extra, airmass=df['AM_relative'],
        model='perez', model_perez='allsitescomposite1990'
    )
    df.loc[stow_mask, 'POA_smooth'] = poa_flat['poa_global'][stow_mask].clip(lower=0)

df['years_elapsed'] = df.index.year - commissioning_year
df['aging_factor']  = np.clip(1 - aging_rate * df['years_elapsed'], 0.80, 1.0)

df['P_dc'] = P_dc0 * (df['POA_smooth'] / 1000.0) * (1 + gamma_pdc * (df['T_cell_eff'] - 25.0))

max_ramp = 0.06 * P_dc0
P_dc_vals = df['P_dc'].values.copy()
for i in range(1, len(P_dc_vals)):
    if minutes_since_sunrise.iloc[i] <= 60:
        delta = P_dc_vals[i] - P_dc_vals[i-1]
        if delta > max_ramp: P_dc_vals[i] = P_dc_vals[i-1] + max_ramp
df['P_dc'] = P_dc_vals

# Apply Plant Availability (String Outages)
df['P_dc_soiled'] = df['P_dc'].clip(lower=0) * (1 - df['Soiling_Loss']) * df['Plant_Availability'] * df['aging_factor'] * sys_loss

load_frac = df['P_dc_soiled'] / P_dc0
inv_eff = np.where(load_frac < 0.05,  0.82 + (load_frac / 0.05) * 0.13,
          np.where(load_frac < 0.20,  0.95 + (load_frac - 0.05) / 0.15 * 0.03,
          np.where(load_frac < 0.60,  0.98 + (load_frac - 0.20) / 0.40 * 0.005,
                   0.985 - (load_frac - 0.60) / 0.40 * 0.015)))
df['P_ac_raw'] = df['P_dc_soiled'] * inv_eff

thermal_derate = np.clip(1 - 0.012 * (df['T_cell_eff'] - 50), 0.88, 1.0)
effective_ac_limit = ac_limit * np.where(df['T_cell_eff'] > 50, thermal_derate, 1.0)

inv_shutdown, inv_off = np.zeros(len(df), dtype=bool), False
t_cell_vals = df['T_cell_eff'].values
for i in range(len(df)):
    if not inv_off and t_cell_vals[i] >= INV_SHUTDOWN_TEMP: inv_off = True
    elif inv_off and t_cell_vals[i] <= INV_RESTART_TEMP: inv_off = False
    inv_shutdown[i] = inv_off

df['P_ac'] = np.where(inv_shutdown, 0.0, np.minimum(df['P_ac_raw'], effective_ac_limit) * df['PR_Drift'])

# CHAOS TWEAK 4: Curtailment happens 8% of days (up from 1%)
df['Curtail_Cap'] = 1e9
high_ghi_days  = df['GHI_dirty'].resample('D').max()[lambda x: x > 550].index
all_days       = df.index.normalize().unique()
curtail_high   = rng.choice(high_ghi_days, size=int(len(high_ghi_days) * 0.08), replace=False)
curtail_rand   = rng.choice(all_days, size=int(len(all_days) * 0.04), replace=False)
curtail_days   = np.unique(np.concatenate([curtail_high, curtail_rand]))

for day in curtail_days:
    start = day + pd.Timedelta(hours=int(rng.integers(9, 14)))
    end   = start + pd.Timedelta(hours=int(rng.integers(3, 7)))
    mask  = (df.index >= start) & (df.index < end)
    df.loc[mask, 'Curtail_Cap'] = float(rng.uniform(0.15, 0.50)) * ac_limit

df['Generation_MW'] = (np.minimum(df['P_ac'], df['Curtail_Cap']) / 1e6).clip(lower=0)
df['Generation_MW'] = df['Generation_MW'] * rng.normal(1.0, 0.005, len(df)) # Increased meter jitter

# Final safety check: Force zero generation using the global night_mask
df.loc[night_mask, 'Generation_MW'] = 0.0

# ============================================================================
# 6. LAYER 4: SCADA CORRUPTIONS & OBSERVABILITY FEATURES
# ============================================================================
print("6. Executing Layer 4: SCADA Data Dropouts & Errors...")

df['GHI_dirty'] *= (1 + 0.003 * df['years_elapsed'])

_ghi_col = df.columns.get_loc('GHI_dirty')
stuck_starts = rng.random(len(df)) < 0.003
for idx in np.where(stuck_starts)[0]:
    length = int(rng.integers(3, 8))
    if idx + length < len(df): df.iloc[idx:idx+length, _ghi_col] = df.iloc[idx, _ghi_col]

# CHAOS TWEAK 5: Higher communication dropouts
nan_mask = rng.random(len(df)) < 0.03
df.loc[nan_mask, ['GHI_dirty', 'Temperature', 'Generation_MW']] = np.nan

_ghi_for_dark = df['GHI_dirty'].fillna(0)
df['Consecutive_dark_steps'] = (_ghi_for_dark < 5).astype(int)
df['Consecutive_dark_steps'] = df.groupby((_ghi_for_dark >= 5).cumsum())['Consecutive_dark_steps'].cumsum()

df['GHI_rollmean_45m'] = df['GHI_dirty'].rolling('45min', min_periods=1).mean()
df['GHI_rollmean_1h']  = df['GHI_dirty'].rolling('1h',   min_periods=1).mean()
df['GHI_rollmean_3h']  = df['GHI_dirty'].rolling('3h',   min_periods=1).mean()
df['GHI_rollstd_1h']   = df['GHI_dirty'].rolling('1h',   min_periods=2).std()
df['dGHI_dt']          = df['GHI_dirty'].diff().fillna(0)
df['dTCC_dt']          = df['TCC'].diff().fillna(0)

df['GHI_lag1']      = df['GHI_dirty'].shift(1)
df['GHI_lag2']      = df['GHI_dirty'].shift(2)
df['clearness_lag1']= df['Clearness_Index'].shift(1)

df['Panel_Temp_Penalty'] = np.maximum(0, df['Temperature'] - 25) * 0.004

gen_shifted = df['Generation_MW'].shift(48)   
ghi_shifted = df['GHI_dirty'].shift(48)

df['rolling_gen_efficiency'] = (gen_shifted.rolling('7D', min_periods=4).mean() / ghi_shifted.rolling('7D', min_periods=4).mean().replace(0, np.nan)).ffill().fillna(0)
df['rolling_PR_proxy'] = (gen_shifted.rolling('30D', min_periods=10).mean() / (ghi_shifted.rolling('30D', min_periods=10).mean().replace(0, np.nan) * P_dc0 / 1e6 / 1000)).ffill().fillna(0).clip(0, 2)

# ============================================================================
# 7. RENAME & EXPORT
# ============================================================================
print("7. Exporting...")

df.drop(columns=['GHI', 'DNI', 'DHI', 'Wind Speed'], inplace=True, errors='ignore')
df.rename(columns={
    'GHI_dirty':        'GHI',
    'DNI_dirty':        'DNI',
    'DHI_dirty':        'DHI',
    'Wind_Speed_dirty': 'Wind Speed',
}, inplace=True)

# THE HARSH REALITY FEATURE LIST
feature_columns = [
    'SZA', 'cos_SZA', 'Solar_Azimuth', 'Solar_Elevation', 'Solar_Declination',
    'AM_relative', 'Shading_Flag',
    'hour_sin', 'hour_cos', 'doy_sin', 'doy_cos', 'doy_sin2', 'doy_cos2',
    'Temperature', 'Dew Point', 'Relative Humidity', 'Pressure', 'Wind Speed',
    'TCC', 'Low_Cloud', 'Mid_Cloud', 'High_Cloud',
    'GHI_clear', 'DNI_clear', 
    'GHI', 'DNI', 'DHI', 'Clearness_Index',
    'GHI_lag1', 'GHI_lag2', 'clearness_lag1',
    'GHI_rollmean_45m', 'GHI_rollmean_1h', 'GHI_rollmean_3h', 'GHI_rollstd_1h',
    'dGHI_dt', 'dTCC_dt',
    'Days_Since_Rain',           
    'Consecutive_dark_steps',    
    'rolling_gen_efficiency',    
    'rolling_PR_proxy',          
    'Generation_MW'
]

df_model = df[feature_columns].dropna(subset=['Generation_MW'])
df_model.to_csv('karnataka_training_data_realistic.csv', index=True)
print(f"\nSuccess! HARSH REALITY dataset generated (IST SYNCED).")