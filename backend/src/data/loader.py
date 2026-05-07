"""
Data Loader — Layer 1 of the Forecasting Pipeline

Responsible for ingesting raw SCADA generation data and NWP weather forecasts
from CSV or Parquet files. Validates schema on load and merges datasets
into a single analysis-ready DataFrame.
"""

import pandas as pd
import numpy as np
import logging
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Required schema columns
# --------------------------------------------------------------------------- #
SCADA_REQUIRED_COLS = [
    "timestamp", "plant_id", "plant_type", "installed_capacity_mw",
    "generation_mw", "availability_flag", "latitude", "longitude",
]
NWP_REQUIRED_COLS = ["timestamp", "plant_id"]
NWP_OPTIONAL_COLS = [
    "ghi_wm2", "cloud_cover_pct", "temperature_c",
    "wind_speed_ms", "wind_direction_deg", "pressure_hpa", "humidity_pct"
]

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
RAW_DIR  = DATA_DIR / "raw"
PROC_DIR = DATA_DIR / "processed"


# --------------------------------------------------------------------------- #
# Schema helpers
# --------------------------------------------------------------------------- #
def _validate_columns(df: pd.DataFrame, required: list, source: str) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"[{source}] Missing required columns: {missing}. "
            f"Found: {df.columns.tolist()}"
        )


def _parse_timestamps(df: pd.DataFrame) -> pd.DataFrame:
    df["timestamp"] = pd.to_datetime(df["timestamp"], format='mixed', utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


# --------------------------------------------------------------------------- #
# Public loaders
# --------------------------------------------------------------------------- #
def load_scada(path: Optional[str] = None, df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """
    Load and validate SCADA generation data.

    Parameters
    ----------
    path : str or None
        Absolute path to CSV/Parquet file. Defaults to data/raw/scada_generation.csv.
    df : pd.DataFrame or None
        Optional DataFrame to use instead of loading from path.

    Returns
    -------
    pd.DataFrame  with columns standardised and timestamp as datetime.
    """
    if df is None:
        if path is None:
            path = RAW_DIR / "scada_generation.csv"

        path = Path(path)
        logger.info(f"Loading SCADA data from {path}")

        if path.suffix == ".parquet":
            df = pd.read_parquet(path)
        else:
            df = pd.read_csv(path, low_memory=False)
    else:
        logger.info("Processing SCADA data from provided DataFrame")

    _validate_columns(df, SCADA_REQUIRED_COLS, "SCADA")
    df = _parse_timestamps(df)

    # Coerce numeric columns
    numeric_cols = ["installed_capacity_mw", "generation_mw", "latitude", "longitude"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Standardise plant_type casing
    df["plant_type"] = df["plant_type"].str.lower().str.strip()

    # hub_height_m is optional — fill missing with NaN for solar plants
    if "hub_height_m" not in df.columns:
        df["hub_height_m"] = np.nan

    logger.info(
        f"SCADA loaded: {len(df):,} rows | "
        f"Plants: {df['plant_id'].nunique()} | "
        f"Range: {df['timestamp'].min()} → {df['timestamp'].max()}"
    )
    return df


def load_nwp(path: Optional[str] = None, df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """
    Load and validate NWP weather forecast data.

    Parameters
    ----------
    path : str or None
        Absolute path to CSV/Parquet file. Defaults to data/raw/nwp_weather.csv.
    df : pd.DataFrame or None
        Optional DataFrame to use instead of loading from path.

    Returns
    -------
    pd.DataFrame  with numeric weather columns and datetime timestamps.
    """
    if df is None:
        if path is None:
            path = RAW_DIR / "nwp_weather.csv"

        path = Path(path)
        logger.info(f"Loading NWP data from {path}")

        if path.suffix == ".parquet":
            df = pd.read_parquet(path)
        else:
            df = pd.read_csv(path, low_memory=False)
    else:
        logger.info("Processing NWP data from provided DataFrame")

    _validate_columns(df, NWP_REQUIRED_COLS, "NWP")
    df = _parse_timestamps(df)

    for col in NWP_OPTIONAL_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            df[col] = np.nan

    logger.info(
        f"NWP loaded: {len(df):,} rows | "
        f"Plants: {df['plant_id'].nunique()} | "
        f"Range: {df['timestamp'].min()} → {df['timestamp'].max()}"
    )
    return df


def merge_datasets(scada: pd.DataFrame, nwp: pd.DataFrame) -> pd.DataFrame:
    """
    Merge SCADA generation data with NWP weather forecasts on [timestamp, plant_id].

    NWP data is upsampled to 15-minute intervals if provided at hourly resolution
    using forward-fill (weather changes slowly within an hour).

    Returns
    -------
    pd.DataFrame  merged and ready for the feature engineering pipeline.
    """
    logger.info("Merging SCADA and NWP datasets...")

    # If NWP is hourly but SCADA is 15-min, forward-fill NWP to 15-min
    nwp_freq = _infer_frequency_minutes(nwp)
    scada_freq = _infer_frequency_minutes(scada)

    if nwp_freq > scada_freq:
        logger.info(f"NWP frequency ({nwp_freq} min) > SCADA ({scada_freq} min) — upsampling NWP via ffill")
        nwp = _upsample_nwp(nwp, target_freq=f"{scada_freq}min")

    merged = pd.merge(scada, nwp, on=["timestamp", "plant_id"], how="outer")

    # Report merge quality
    if "ghi_wm2" in merged.columns:
        weather_null_pct = merged["ghi_wm2"].isna().mean() * 100
    elif "wind_speed_ms" in merged.columns:
        weather_null_pct = merged["wind_speed_ms"].isna().mean() * 100
    else:
        weather_null_pct = 100.0

    logger.info(
        f"Merge complete: {len(merged):,} rows | "
        f"Weather null rate: {weather_null_pct:.1f}%"
    )
    return merged


def _infer_frequency_minutes(df: pd.DataFrame) -> int:
    """Infer the modal time-step in minutes from the first plant's timestamps."""
    sample = df[df["plant_id"] == df["plant_id"].iloc[0]].copy()
    if len(sample) < 2:
        return 15
    diffs = sample["timestamp"].diff().dropna().dt.total_seconds() / 60
    return int(diffs.mode()[0])


def _upsample_nwp(nwp: pd.DataFrame, target_freq: str) -> pd.DataFrame:
    """Upsample NWP per plant to target frequency using forward-fill."""
    resampled_parts = []
    for plant_id, group in nwp.groupby("plant_id"):
        group = group.set_index("timestamp").sort_index()
        group = group.resample(target_freq).ffill()
        group["plant_id"] = plant_id
        group = group.reset_index()
        resampled_parts.append(group)
    return pd.concat(resampled_parts, ignore_index=True)


# --------------------------------------------------------------------------- #
# Convenience function for the training pipeline
# --------------------------------------------------------------------------- #
def load_all(scada_path: Optional[str] = None,
             nwp_path: Optional[str] = None) -> pd.DataFrame:
    """
    One-call loader: load, validate, and merge SCADA + NWP data.
    """
    scada = load_scada(scada_path)
    nwp   = load_nwp(nwp_path)
    return merge_datasets(scada, nwp)
