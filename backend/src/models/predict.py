"""
Inference Engine — Generates 96-block SLDC Schedule from Trained Models

This module:
  1. Loads trained LightGBM models
  2. Applies physical constraint checks (night solar = 0, PLF ≤ 1)
  3. Falls back to persistence model if NWP data is unavailable
  4. Formats output as a 96-block SLDC-compatible schedule with uncertainty bands
"""

import pandas as pd
import numpy as np
import logging
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.models.train import load_models, load_feature_cols, QUANTILE_LABELS
from src.features.engineering import (
    build_features, SOLAR_FEATURES, WIND_FEATURES, CATEGORICAL_FEATURES
)

logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).resolve().parents[3] / "models" / "saved"

# Uncertainty band thresholds (as fraction of installed capacity)
UNCERTAINTY_NARROW  = 0.05   # <5% → high confidence
UNCERTAINTY_WIDE    = 0.20   # >20% → low confidence / flag for human review


# --------------------------------------------------------------------------- #
# Single-plant inference
# --------------------------------------------------------------------------- #
def predict_plant(feature_df: pd.DataFrame,
                  plant_id: str,
                  plant_type: str,
                  installed_capacity_mw: float,
                  models: Dict[str, object]) -> pd.DataFrame:
    """
    Run P10/P50/P90 inference for a single plant.

    Parameters
    ----------
    feature_df           : feature-engineered DataFrame (from build_features)
    plant_id             : plant identifier string
    plant_type           : 'solar' or 'wind'
    installed_capacity_mw: nameplate capacity for MW scaling
    models               : dict with keys 'p10', 'p50', 'p90'

    Returns
    -------
    DataFrame with columns: timestamp, plant_id, p10_mw, p50_mw, p90_mw,
                             uncertainty_band_mw, confidence_flag
    """
    plant_df = feature_df[feature_df["plant_id"] == plant_id].copy()
    if len(plant_df) == 0:
        logger.warning(f"No data found for plant_id='{plant_id}'")
        return pd.DataFrame()

    first_model = next(iter(models.values()))
    feature_cols = getattr(first_model, "feature_name_", None) or load_feature_cols(plant_type)
    feature_cols = [f for f in feature_cols if f in plant_df.columns]
    X = plant_df[feature_cols].copy()
    _apply_model_categories(X, first_model)

    results = {}
    for q_label, model in models.items():
        _apply_model_categories(X, model)
        pred_plf = model.predict(X).clip(0, 1)
        results[f"{q_label}_plf"] = pred_plf
        results[f"{q_label}_mw"]  = pred_plf * installed_capacity_mw

    out = pd.DataFrame({
        "timestamp":  plant_df["timestamp"].values,
        "plant_id":   plant_id,
        "plant_type": plant_type,
        "p10_mw":     results["p10_mw"],
        "p50_mw":     results["p50_mw"],
        "p90_mw":     results["p90_mw"],
    })

    # Physical constraints
    out = _apply_physical_constraints(out, plant_df, plant_type, installed_capacity_mw)
    out = _compute_uncertainty_flags(out, installed_capacity_mw)

    return out.reset_index(drop=True)


def _apply_model_categories(X: pd.DataFrame, model: object) -> None:
    """Match saved LightGBM pandas categorical metadata during inference."""
    categories = getattr(getattr(model, "booster_", None), "pandas_categorical", None)
    if not categories:
        return

    categorical_cols = [col for col in CATEGORICAL_FEATURES if col in X.columns]
    for col, values in zip(categorical_cols, categories):
        X[col] = pd.Categorical(X[col], categories=values)


def _apply_physical_constraints(out: pd.DataFrame,
                                 feature_df: pd.DataFrame,
                                 plant_type: str,
                                 capacity_mw: float) -> pd.DataFrame:
    """
    Enforce hard physical limits after model predictions:
      - Solar output = 0 at night
      - All outputs capped at installed capacity
      - All outputs floored at 0
    """
    out = out.copy()
    out[["p10_mw", "p50_mw", "p90_mw"]] = (
        out[["p10_mw", "p50_mw", "p90_mw"]].clip(lower=0, upper=capacity_mw)
    )

    if plant_type == "solar" and "is_daytime" in feature_df.columns:
        is_night = ~feature_df["is_daytime"].values
        out.loc[is_night, ["p10_mw", "p50_mw", "p90_mw"]] = 0.0

    return out


def _compute_uncertainty_flags(out: pd.DataFrame,
                                 capacity_mw: float) -> pd.DataFrame:
    """
    Compute uncertainty band and flag each block as high/medium/low confidence.
    """
    out = out.copy()
    out["uncertainty_band_mw"] = out["p90_mw"] - out["p10_mw"]
    out["uncertainty_pct"]     = out["uncertainty_band_mw"] / capacity_mw

    conditions = [
        out["uncertainty_pct"] < UNCERTAINTY_NARROW,
        out["uncertainty_pct"] > UNCERTAINTY_WIDE,
    ]
    choices = ["HIGH_CONFIDENCE", "LOW_CONFIDENCE"]
    out["confidence_flag"] = np.select(conditions, choices, default="MEDIUM_CONFIDENCE")

    return out


# --------------------------------------------------------------------------- #
# Portfolio-level prediction (multiple plants)
# --------------------------------------------------------------------------- #
def predict_portfolio(feature_df: pd.DataFrame,
                      plant_metadata: pd.DataFrame) -> pd.DataFrame:
    """
    Run inference across a portfolio of plants.

    Parameters
    ----------
    feature_df     : feature-engineered DataFrame with all plants
    plant_metadata : DataFrame with columns [plant_id, plant_type, installed_capacity_mw]

    Returns
    -------
    Concatenated per-plant forecast DataFrame
    """
    all_forecasts = []

    for _, row in plant_metadata.iterrows():
        plant_id  = row["plant_id"]
        plant_type = row["plant_type"]
        capacity   = row["installed_capacity_mw"]

        try:
            models = load_models(plant_type)
        except FileNotFoundError as e:
            logger.error(str(e))
            continue

        plant_forecast = predict_plant(
            feature_df, plant_id, plant_type, capacity, models
        )
        if len(plant_forecast) > 0:
            all_forecasts.append(plant_forecast)

    if not all_forecasts:
        return pd.DataFrame()

    return pd.concat(all_forecasts, ignore_index=True)


# --------------------------------------------------------------------------- #
# Cluster / regional aggregation
# --------------------------------------------------------------------------- #
def aggregate_cluster(portfolio_forecast: pd.DataFrame,
                      cluster_mapping: Optional[Dict[str, str]] = None) -> pd.DataFrame:
    """
    Aggregate plant-level forecasts to cluster level.

    Parameters
    ----------
    portfolio_forecast : output of predict_portfolio()
    cluster_mapping    : dict mapping plant_id → cluster_id
                         If None, aggregates all plants together.

    Returns
    -------
    Cluster-level forecast with P10/P50/P90 in MW.
    """
    df = portfolio_forecast.copy()

    if cluster_mapping:
        df["cluster_id"] = df["plant_id"].map(cluster_mapping).fillna("UNGROUPED")
    else:
        df["cluster_id"] = "ALL"

    # Aggregate: P50 sums; P10/P90 use portfolio theory (sum for simplicity in prototype)
    agg = df.groupby(["timestamp", "cluster_id"]).agg(
        p10_mw=("p10_mw", "sum"),
        p50_mw=("p50_mw", "sum"),
        p90_mw=("p90_mw", "sum"),
        n_plants=("plant_id", "count"),
    ).reset_index()

    agg["uncertainty_band_mw"] = agg["p90_mw"] - agg["p10_mw"]
    return agg


# --------------------------------------------------------------------------- #
# SLDC 96-block schedule formatter
# --------------------------------------------------------------------------- #
def format_sldc_schedule(plant_forecast: pd.DataFrame,
                          forecast_date: str) -> pd.DataFrame:
    """
    Format a plant forecast into the 96-block SLDC schedule structure.
    """
    if plant_forecast is None or plant_forecast.empty:
        logger.warning("Empty plant forecast provided to format_sldc_schedule")
        return pd.DataFrame()

    date_ts = pd.Timestamp(forecast_date)
    # Filter to just the forecast day
    mask = plant_forecast["timestamp"].dt.date == date_ts.date()
    day_df = plant_forecast[mask].copy()

    if len(day_df) == 0:
        logger.warning(f"No forecasts found for date {forecast_date}")
        return pd.DataFrame()

    # Build 96 blocks explicitly
    blocks = []
    for block_no in range(1, 97):
        mins_start = (block_no - 1) * 15
        time_from  = date_ts + pd.Timedelta(minutes=mins_start)
        time_to    = time_from + pd.Timedelta(minutes=15)

        row_match = day_df[day_df["timestamp"] == time_from]
        if len(row_match) == 0:
            # Missing block → use P50 from nearest available
            nearest = day_df.iloc[(day_df["timestamp"] - time_from).abs().argsort().iloc[0]]
            p50 = float(nearest["p50_mw"])
            p10 = float(nearest["p10_mw"])
            p90 = float(nearest["p90_mw"])
            flag = "INTERPOLATED"
        else:
            p50  = float(row_match["p50_mw"].iloc[0])
            p10  = float(row_match["p10_mw"].iloc[0])
            p90  = float(row_match["p90_mw"].iloc[0])
            flag = str(row_match["confidence_flag"].iloc[0])

        blocks.append({
            "date":               forecast_date,
            "block_no":           block_no,
            "time_from":          time_from.strftime("%H:%M"),
            "time_to":            time_to.strftime("%H:%M"),
            "plant_id":           day_df["plant_id"].iloc[0],
            "scheduled_gen_mw":   round(p50, 3),
            "p10_mw":             round(p10, 3),
            "p90_mw":             round(p90, 3),
            "uncertainty_band_mw": round(p90 - p10, 3),
            "confidence_flag":    flag,
        })

    return pd.DataFrame(blocks)


# --------------------------------------------------------------------------- #
# NWP fallback — persistence model
# --------------------------------------------------------------------------- #
def persistence_fallback(feature_df: pd.DataFrame,
                          plant_id: str,
                          installed_capacity_mw: float) -> pd.DataFrame:
    """
    Fallback when NWP data is unavailable. Predicts next interval = T-24h PLF.
    Returns same structure as predict_plant() but with wide uncertainty bands.
    """
    plant_df = feature_df[feature_df["plant_id"] == plant_id].copy()

    # Use yesterday's generation as today's forecast
    p50_plf = plant_df.get("plf_lag_96", plant_df.get("plf_lag_1", pd.Series(0)))
    p50_mw  = p50_plf.fillna(0).clip(0, 1) * installed_capacity_mw
    # Wide uncertainty band: ±30% of capacity
    band    = installed_capacity_mw * 0.30

    return pd.DataFrame({
        "timestamp":          plant_df["timestamp"].values,
        "plant_id":           plant_id,
        "plant_type":         plant_df["plant_type"].values,
        "p10_mw":             (p50_mw - band / 2).clip(0),
        "p50_mw":             p50_mw,
        "p90_mw":             (p50_mw + band / 2).clip(upper=installed_capacity_mw),
        "uncertainty_band_mw": band,
        "confidence_flag":    "NWP_FALLBACK",
    })
