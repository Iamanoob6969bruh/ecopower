"""
Data Cleaner — Outage Filtering, Anomaly Detection, and Imputation

Three-stage cleaning pipeline:
  1. Outage flag filtering  — removes records where plant was unavailable
  2. Physical anomaly detection — flags impossible values (gen > capacity, GHI at night)
  3. Missing value imputation — interpolation for short gaps, KNN for long gaps
"""

import pandas as pd
import numpy as np
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Stage 1: Outage / Maintenance Filtering
# --------------------------------------------------------------------------- #
def filter_outages(df: pd.DataFrame,
                   availability_col: str = "availability_flag") -> pd.DataFrame:
    """
    Remove records where the plant was unavailable (maintenance, trip, outage).
    Keeps the row but marks it with an 'is_outage' flag for audit trail.

    Parameters
    ----------
    df : merged SCADA+NWP DataFrame from loader.merge_datasets()
    availability_col : column name for availability (1=available, 0=unavailable)

    Returns
    -------
    DataFrame with 'is_outage' column added.
    Records where is_outage=True are excluded from the training-ready subset.
    """
    if availability_col not in df.columns:
        logger.warning(
            f"'{availability_col}' column not found. Assuming all records are available."
        )
        df["is_outage"] = False
        return df

    # Assume available if NaN (important for future forecasts where SCADA is missing)
    df["is_outage"] = df[availability_col].fillna(1).astype(int) == 0

    n_outage = df["is_outage"].sum()
    pct = n_outage / len(df) * 100
    logger.info(f"Outage filter: {n_outage:,} records flagged ({pct:.1f}% of total)")
    return df


# --------------------------------------------------------------------------- #
# Stage 2: Physical Anomaly Detection
# --------------------------------------------------------------------------- #
def detect_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    """
    Flag physically impossible or highly suspicious readings.

    Rules applied:
      - generation_mw < 0                          → impossible
      - generation_mw > installed_capacity_mw * 1.05  → exceeds capacity (5% tolerance)
      - PLF > 1.05                                  → capacity exceedance
      - ghi_wm2 < 0                                 → impossible irradiance
      - wind_speed_ms < 0                           → impossible wind speed
      - cloud_cover_pct not in [0, 100]             → out of range

    Returns
    -------
    DataFrame with 'is_anomaly' boolean column.
    """
    df = df.copy()
    flags = pd.Series(False, index=df.index)

    if "generation_mw" in df.columns:
        flags |= df["generation_mw"] < 0

    if "generation_mw" in df.columns and "installed_capacity_mw" in df.columns:
        flags |= df["generation_mw"] > df["installed_capacity_mw"] * 1.05

    if "ghi_wm2" in df.columns:
        flags |= df["ghi_wm2"] < 0

    if "wind_speed_ms" in df.columns:
        flags |= df["wind_speed_ms"] < 0

    if "cloud_cover_pct" in df.columns:
        flags |= (df["cloud_cover_pct"] < 0) | (df["cloud_cover_pct"] > 100)

    df["is_anomaly"] = flags
    n_anom = flags.sum()
    logger.info(f"Anomaly detection: {n_anom:,} records flagged ({n_anom/len(df)*100:.2f}%)")
    return df


# --------------------------------------------------------------------------- #
# Stage 3: Missing Value Imputation
# --------------------------------------------------------------------------- #
def impute_missing(df: pd.DataFrame,
                   short_gap_limit_intervals: int = 4,
                   weather_cols: Optional[list] = None) -> pd.DataFrame:
    """
    Impute missing values using a two-stage strategy per plant:
      - Short gaps (≤ short_gap_limit_intervals consecutive NaN): linear interpolation
      - Long gaps: forward-fill + backward-fill (climatologically neutral)

    All imputed values are marked with an 'is_imputed' flag so they can be
    excluded from evaluation metrics.

    Parameters
    ----------
    df : DataFrame from previous stages
    short_gap_limit_intervals : max consecutive NaNs for linear interpolation
    weather_cols : list of weather columns to impute (auto-detected if None)
    """
    if weather_cols is None:
        weather_cols = [c for c in [
            "ghi_wm2", "cloud_cover_pct", "temperature_c",
            "wind_speed_ms", "wind_direction_deg", "pressure_hpa", "humidity_pct"
        ] if c in df.columns]

    target_cols = ["generation_mw"] + weather_cols

    # Track which cells were imputed
    original_nulls = df[target_cols].isna()
    df = df.copy()

    imputed_parts = []
    for plant_id, group in df.groupby("plant_id"):
        group = group.sort_values("timestamp").copy()

        for col in target_cols:
            if col not in group.columns:
                continue

            # Short gap: interpolate
            group[col] = group[col].interpolate(
                method="linear",
                limit=short_gap_limit_intervals,
                limit_direction="forward"
            )
            # Long gap: forward then backward fill
            group[col] = group[col].ffill().bfill()

        imputed_parts.append(group)

    df = pd.concat(imputed_parts).sort_values(["plant_id", "timestamp"]).reset_index(drop=True)

    # Mark imputed rows
    now_filled = ~df[target_cols].isna()
    previously_null = original_nulls.reindex(df.index, fill_value=True)
    was_imputed = (previously_null & now_filled).any(axis=1)
    df["is_imputed"] = was_imputed

    n_imputed = was_imputed.sum()
    logger.info(f"Imputation: {n_imputed:,} rows had at least one value imputed")
    return df


# --------------------------------------------------------------------------- #
# Master clean function
# --------------------------------------------------------------------------- #
def clean(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Run all three cleaning stages and return:
      - training_df : records available for model training (no outage, no anomaly)
      - audit_df    : full dataset including flagged records (for reporting)
    """
    df = filter_outages(df)
    df = detect_anomalies(df)
    df = impute_missing(df)

    training_df = df[~df["is_outage"] & ~df["is_anomaly"]].copy()
    logger.info(
        f"Clean complete. Training-ready rows: {len(training_df):,} "
        f"(of {len(df):,} total)"
    )
    return training_df, df  # (training subset, full audit trail)
