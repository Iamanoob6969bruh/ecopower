"""
Physics-Informed Feature Engineering — Layer 2

All transformations in this module are grounded in physical reality:
  1. Solar Zenith Angle (SZA) — masks solar generation to zero at night
  2. Wind direction decomposition — U/V vector components (avoids 359°→1° discontinuity)
  3. Hub-height wind speed correction — power law profile adjustment
  4. Plant Load Factor (PLF) normalization — enables cross-plant generalization
  5. Temporal features — hour, month, day-of-week, season
  6. Lag features — T-15min, T-1h, T-24h actual generation
  7. Rolling statistics — mean/std over 1h, 3h, 6h windows
"""

import numpy as np
import pandas as pd
import logging
import math
from typing import Optional

logger = logging.getLogger(__name__)

# Reference height for NWP wind speed (metres above ground)
NWP_REFERENCE_HEIGHT_M = 10.0

# Wind shear exponent for open terrain (Hellmann exponent)
WIND_SHEAR_ALPHA = 0.143


# --------------------------------------------------------------------------- #
# 1. Solar Zenith Angle
# --------------------------------------------------------------------------- #
def solar_zenith_angle(lat: float, lon: float,
                       timestamps: pd.Series) -> pd.Series:
    """
    Compute the cosine of the Solar Zenith Angle (cos_sza) for each timestamp.

    cos_sza > 0  →  daytime   (sun above horizon)
    cos_sza ≤ 0  →  nighttime (sun at or below horizon)

    Uses the simplified astronomical algorithm valid within ±0.5° accuracy.

    Parameters
    ----------
    lat        : plant latitude in decimal degrees
    lon        : plant longitude in decimal degrees
    timestamps : pd.Series of datetime64 values

    Returns
    -------
    pd.Series of cos(SZA) values, clipped to [-1, 1]
    """
    lat_rad = math.radians(lat)

    # Day of year
    doy = timestamps.dt.dayofyear

    # Equation of time (minutes)
    B = (360 / 365) * (doy - 81)
    B_rad = np.radians(B)
    eot = 9.87 * np.sin(2 * B_rad) - 7.53 * np.cos(B_rad) - 1.5 * np.sin(B_rad)

    # Solar declination (radians)
    decl = np.radians(23.45 * np.sin(np.radians(360 / 365 * (doy - 81))))

    # Local Solar Time
    hour_utc   = timestamps.dt.hour + timestamps.dt.minute / 60.0
    lstm       = 15 * round(lon / 15)   # Local Standard Time Meridian
    lst        = hour_utc + (lon - lstm) / 15 + eot / 60  # local solar time
    hour_angle = np.radians(15 * (lst - 12))              # radians

    # cos(SZA)
    cos_sza = (
        np.sin(lat_rad) * np.sin(decl) +
        np.cos(lat_rad) * np.cos(decl) * np.cos(hour_angle)
    )
    return cos_sza.clip(-1, 1)


def mask_solar_at_night(df: pd.DataFrame) -> pd.DataFrame:
    """
    For solar plants: force GHI to zero and set a 'is_daytime' flag
    when Solar Zenith Angle ≥ 90° (sun below horizon).

    Each plant gets its own SZA calculation using its coordinates.
    """
    df = df.copy()
    df["cos_sza"]    = np.nan
    df["is_daytime"] = False

    solar_mask = df["plant_type"] == "solar"
    if not solar_mask.any():
        logger.info("No solar plants found — SZA masking skipped.")
        return df

    for plant_id, grp in df[solar_mask].groupby("plant_id"):
        lat = grp["latitude"].iloc[0]
        lon = grp["longitude"].iloc[0]
        cos_sza_vals = solar_zenith_angle(lat, lon, grp["timestamp"])
        df.loc[grp.index, "cos_sza"]    = cos_sza_vals.values
        df.loc[grp.index, "is_daytime"] = cos_sza_vals.values > 0

    # Zero out GHI during nighttime for solar plants
    night_solar = solar_mask & ~df["is_daytime"]
    if "ghi_wm2" in df.columns:
        df.loc[night_solar, "ghi_wm2"] = 0.0

    logger.info(f"SZA masking complete. Night intervals zeroed: {night_solar.sum():,}")
    return df


# --------------------------------------------------------------------------- #
# 2. Wind Direction Decomposition
# --------------------------------------------------------------------------- #
def wind_direction_to_vectors(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert wind direction (0–360°) to U (eastward) and V (northward) components,
    and also provide raw Sine and Cosine components as requested.

    This prevents the model from treating 359° and 1° as far apart.
    """
    if "wind_direction_deg" not in df.columns:
        return df
    df = df.copy()
    wd_rad = np.radians(df["wind_direction_deg"])

    # Speed-weight the vectors with hub-height wind (the operative wind for a
    # turbine). Requires adjust_wind_speed_to_hub_height to have run first; fall
    # back to wind_speed_ms only if the hub wind is unavailable.
    speed = df["wind_speed_hub_ms"] if "wind_speed_hub_ms" in df.columns else df.get("wind_speed_ms", 0.0)

    # Vector components (speed-weighted)
    df["wind_u"] = -speed * np.sin(wd_rad)
    df["wind_v"] = -speed * np.cos(wd_rad)

    # Pure cyclical components
    df["wind_dir_sin"] = np.sin(wd_rad)
    df["wind_dir_cos"] = np.cos(wd_rad)

    return df


# --------------------------------------------------------------------------- #
# 3. Hub-Height Wind Speed Correction
# --------------------------------------------------------------------------- #
def adjust_wind_speed_to_hub_height(df: pd.DataFrame,
                                    alpha_default: float = WIND_SHEAR_ALPHA) -> pd.DataFrame:
    """
    Estimate wind speed at each plant's turbine hub height.

    Turbines operate at 65-135 m, so the operative wind is the hub-height wind,
    NOT the 10 m surface wind. We derive it from the NWP wind speeds at 80 m and
    120 m using the power-law profile:

        V_hub = V_120 * (hub_height / 120) ^ alpha

    where the shear exponent alpha is estimated per-record from the two known
    heights:  alpha = ln(V_120 / V_80) / ln(120 / 80).

    This replaces the previous approach of extrapolating from a "10 m" wind that,
    in the training data, was actually the 80 m wind (10 m == 80 m for every row),
    which caused severe under-prediction once fed real 10 m wind at inference.

    Falls back gracefully when only one height is available, and to the raw
    wind_speed_ms as a last resort (e.g. malformed input).
    """
    df = df.copy()

    # Gather whatever measured heights are available, tallest first. Data sources
    # differ: the Open-Meteo *forecast* API gives 80 m + 120 m; the *archive*
    # (ERA5) API gives only 10 m + 100 m; training NWP has 10 m + 80 m + 120 m.
    # A column can also be present but all-null (archive returns null 80/120 m),
    # so require at least one real value.
    def height_col(name):
        if name in df.columns and df[name].notna().any():
            return df[name]
        return None

    candidates = [
        (120.0, height_col("wind_speed_120m")),
        (100.0, height_col("wind_speed_100m")),
        (80.0,  height_col("wind_speed_80m")),
        (10.0,  height_col("wind_speed_ms")),
    ]
    avail = [(h, s) for h, s in candidates if s is not None]

    if not avail:
        # Nothing usable — leave hub wind absent (downstream fills 0).
        return df

    # Effective hub height: the plant's hub, default 100 m when unknown (solar).
    if "hub_height_m" in df.columns:
        hub_eff = df["hub_height_m"].where(
            df["hub_height_m"].notna() & (df["hub_height_m"] > 0), 100.0
        )
    else:
        hub_eff = pd.Series(100.0, index=df.index)

    if len(avail) >= 2:
        # Estimate the shear exponent from the two tallest available heights.
        (h_hi, s_hi), (h_lo, s_lo) = avail[0], avail[1]
        safe_hi = s_hi.clip(lower=0.1)
        safe_lo = s_lo.clip(lower=0.1)
        alpha = (np.log(safe_hi / safe_lo) / np.log(h_hi / h_lo))
        alpha = alpha.clip(lower=0.0, upper=0.6).fillna(alpha_default)
        df["wind_speed_hub_ms"] = safe_hi * (hub_eff / h_hi) ** alpha
        df.loc[(s_hi <= 0.1) & (s_lo <= 0.1), "wind_speed_hub_ms"] = 0.0
        logger.info(f"Hub wind from {int(h_lo)}/{int(h_hi)} m profile for {len(df):,} records")
    else:
        h, s = avail[0]
        df["wind_speed_hub_ms"] = s.clip(lower=0.0) * (hub_eff / h) ** alpha_default
        logger.info(f"Hub wind from single {int(h)} m height (default shear) for {len(df):,} records")

    df["wind_speed_hub_ms"] = df["wind_speed_hub_ms"].fillna(0.0)
    return df


# --------------------------------------------------------------------------- #
# 4. Plant Load Factor Normalisation
# --------------------------------------------------------------------------- #
def compute_plf(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute Plant Load Factor (PLF) = generation_mw / installed_capacity_mw.
    PLF is the training target. It is clipped to [0, 1].

    For solar plants, PLF during nighttime is forced to 0.
    """
    df = df.copy()
    df["plf"] = (df["generation_mw"] / df["installed_capacity_mw"]).clip(0, 1)

    # Force nighttime solar PLF to 0
    if "is_daytime" in df.columns:
        night_solar = (df["plant_type"] == "solar") & ~df["is_daytime"]
        df.loc[night_solar, "plf"] = 0.0

    return df


# --------------------------------------------------------------------------- #
# 5. Temporal Features
# --------------------------------------------------------------------------- #
def add_temporal_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add time-based features that capture diurnal and seasonal patterns.
    Uses sine/cosine encoding to preserve cyclical nature of time.
    """
    df = df.copy()
    ts = df["timestamp"]

    df["hour"]           = ts.dt.hour
    df["month"]          = ts.dt.month
    df["day_of_week"]    = ts.dt.dayofweek
    df["day_of_year"]    = ts.dt.dayofyear
    df["quarter"]        = ts.dt.quarter
    df["is_weekend"]     = (df["day_of_week"] >= 5).astype(int)

    # Cyclical encoding
    df["hour_sin"]       = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"]       = np.cos(2 * np.pi * df["hour"] / 24)
    df["month_sin"]      = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"]      = np.cos(2 * np.pi * df["month"] / 12)
    df["doy_sin"]        = np.sin(2 * np.pi * df["day_of_year"] / 365)
    df["doy_cos"]        = np.cos(2 * np.pi * df["day_of_year"] / 365)

    # 15-minute slot within the day (0–95 for SLDC blocks)
    df["block_of_day"]   = ts.dt.hour * 4 + ts.dt.minute // 15

    return df


# --------------------------------------------------------------------------- #
# 6. Lag Features
# --------------------------------------------------------------------------- #
def add_lag_features(df: pd.DataFrame,
                     lag_intervals: Optional[list] = None) -> pd.DataFrame:
    """
    Add historical PLF lag features per plant.
    At 15-minute resolution:
        lag=1  → 15 minutes ago
        lag=4  → 1 hour ago
        lag=96 → 24 hours ago (same time yesterday)

    Parameters
    ----------
    lag_intervals : list of integer lags in number of intervals (default: [1, 4, 96])
    """
    if lag_intervals is None:
        lag_intervals = [1, 4, 96]

    df = df.copy()

    for plant_id, group in df.groupby("plant_id"):
        group = group.sort_values("timestamp")
        for lag in lag_intervals:
            col = f"plf_lag_{lag}"
            df.loc[group.index, col] = group["plf"].shift(lag).values

    logger.info(f"Lag features added: {[f'plf_lag_{l}' for l in lag_intervals]}")
    return df


# --------------------------------------------------------------------------- #
# 7. Rolling Statistics
# --------------------------------------------------------------------------- #
def add_rolling_features(df: pd.DataFrame,
                         windows_hours: Optional[list] = None) -> pd.DataFrame:
    """
    Add rolling mean and standard deviation of PLF per plant.
    Windows are specified in hours; converted to intervals at 15-min resolution.

    Parameters
    ----------
    windows_hours : list of window sizes in hours (default: [1, 3, 6])
    """
    if windows_hours is None:
        windows_hours = [1, 3, 6]

    df = df.copy()

    for plant_id, group in df.groupby("plant_id"):
        group = group.sort_values("timestamp")
        for hours in windows_hours:
            n_intervals = hours * 4  # 4 x 15-min intervals per hour
            df.loc[group.index, f"plf_roll_mean_{hours}h"] = (
                group["plf"].shift(1).rolling(n_intervals, min_periods=1).mean().values
            )
            df.loc[group.index, f"plf_roll_std_{hours}h"] = (
                group["plf"].shift(1).rolling(n_intervals, min_periods=1).std().values
            )

    logger.info(f"Rolling features added for windows: {windows_hours}h")
    return df


# --------------------------------------------------------------------------- #
# Master feature engineering pipeline
# --------------------------------------------------------------------------- #
def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Run the full physics-informed feature engineering pipeline.

    Expected input: cleaned and merged SCADA+NWP DataFrame.
    Returns a feature matrix ready for model training or inference.
    """
    logger.info("Starting feature engineering pipeline...")

    df = mask_solar_at_night(df)
    df = adjust_wind_speed_to_hub_height(df)   # must run before U/V (which uses hub wind)
    df = wind_direction_to_vectors(df)
    df = compute_plf(df)
    df = add_temporal_features(df)
    df = add_lag_features(df)
    df = add_rolling_features(df)

    lag_cols = [c for c in df.columns if c.startswith("plf_lag_")]
    # df = df.dropna(subset=lag_cols).reset_index(drop=True)
    logger.info(
        f"Feature engineering complete. Rows: {len(df):,}"
    )
    return df


# --------------------------------------------------------------------------- #
# Feature column lists by plant type (used during model training)
# --------------------------------------------------------------------------- #
SOLAR_FEATURES = [
    "cos_sza", "ghi_wm2", "cloud_cover_pct", "temperature_c",
    "hour_sin", "hour_cos", "month_sin", "month_cos", "doy_sin", "doy_cos",
    "block_of_day", "is_weekend",
    "plf_lag_1", "plf_lag_4", "plf_lag_96",
    "plf_roll_mean_1h", "plf_roll_mean_3h", "plf_roll_mean_6h",
    "plf_roll_std_1h",  "plf_roll_std_3h",  "plf_roll_std_6h",
    "humidity_pct", "pressure_hpa", "plant_id"
]

WIND_FEATURES = [
    # NOTE: raw 10 m wind (wind_speed_ms) is intentionally excluded. Turbines
    # operate at hub height; wind_speed_hub_ms is derived from the 80 m / 120 m
    # profile so training and inference use the same physical quantities.
    "wind_speed_hub_ms", "wind_u", "wind_v",
    "wind_dir_sin", "wind_dir_cos",
    "wind_speed_120m", "wind_speed_80m",  # hub-relevant heights
    "temperature_c", "pressure_hpa", "humidity_pct",
    "latitude", "longitude", "hub_height_m", # New location/spec factors
    "hour_sin", "hour_cos", "month_sin", "month_cos", "doy_sin", "doy_cos",
    "block_of_day", "is_weekend",
    "plf_lag_1", "plf_lag_4", "plf_lag_96",
    "plf_roll_mean_1h", "plf_roll_mean_3h", "plf_roll_mean_6h",
    "plf_roll_std_1h",  "plf_roll_std_3h",  "plf_roll_std_6h",
    "plant_id"
]

CATEGORICAL_FEATURES = ["plant_id"]
TARGET = "plf"
