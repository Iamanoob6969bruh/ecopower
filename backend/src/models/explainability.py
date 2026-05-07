"""
Explainability Module — SHAP Feature Attribution

Computes SHAP values using TreeExplainer (model-native, no sampling needed for LightGBM).
Returns both global feature importance and per-prediction local explanations.
"""

import numpy as np
import pandas as pd
import shap
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def get_shap_explainer(model) -> shap.TreeExplainer:
    """
    Create a SHAP TreeExplainer for a LightGBM model.
    TreeExplainer is exact (not approximate) for tree-based models.
    """
    return shap.TreeExplainer(model)


def compute_global_importance(model,
                               X: pd.DataFrame,
                               feature_names: List[str]) -> pd.DataFrame:
    """
    Compute global SHAP feature importance (mean |SHAP value| across all samples).

    Parameters
    ----------
    model         : trained LightGBMRegressor (P50 model recommended)
    X             : feature matrix
    feature_names : list of feature column names

    Returns
    -------
    DataFrame sorted by importance descending:
      [feature, mean_abs_shap, rank]
    """
    explainer = get_shap_explainer(model)
    shap_values = explainer.shap_values(X)

    importance = pd.DataFrame({
        "feature":        feature_names,
        "mean_abs_shap":  np.abs(shap_values).mean(axis=0),
    }).sort_values("mean_abs_shap", ascending=False).reset_index(drop=True)
    importance["rank"] = importance.index + 1

    logger.info(f"Global importance computed for {len(feature_names)} features")
    return importance


def compute_local_shap(model,
                        X_single: pd.DataFrame,
                        feature_names: List[str],
                        base_mw: Optional[float] = None) -> pd.DataFrame:
    """
    Compute SHAP values for a single prediction (local explanation).

    Parameters
    ----------
    model         : trained LightGBMRegressor
    X_single      : single-row feature DataFrame
    feature_names : list of feature column names
    base_mw       : installed capacity in MW (to scale from PLF to MW if provided)

    Returns
    -------
    DataFrame with [feature, value, shap_value, direction]
    Sorted by absolute SHAP value descending.
    """
    explainer   = get_shap_explainer(model)
    shap_values = explainer.shap_values(X_single)

    if shap_values.ndim > 1:
        shap_vals = shap_values[0]
    else:
        shap_vals = shap_values

    feature_values = X_single.iloc[0].values if hasattr(X_single, "iloc") else X_single

    df = pd.DataFrame({
        "feature":    feature_names,
        "value":      feature_values,
        "shap_value": shap_vals,
    })

    if base_mw is not None:
        df["shap_mw"] = df["shap_value"] * base_mw

    df["direction"] = np.where(df["shap_value"] >= 0, "↑ Increases", "↓ Decreases")
    df = df.reindex(df["shap_value"].abs().sort_values(ascending=False).index)
    return df.reset_index(drop=True)


def explain_forecast_block(model,
                            feature_df: pd.DataFrame,
                            plant_id: str,
                            timestamp: pd.Timestamp,
                            feature_cols: List[str],
                            installed_capacity_mw: float) -> Dict:
    """
    Produce a human-readable explanation for a specific forecast block.

    Returns
    -------
    dict with:
      - 'base_value'       : model base prediction (PLF)
      - 'predicted_plf'    : model output for this block
      - 'predicted_mw'     : predicted MW
      - 'top_drivers'      : list of dicts describing top 5 SHAP contributors
      - 'narrative'        : one-sentence plain English summary
    """
    plant_df = feature_df[
        (feature_df["plant_id"] == plant_id) &
        (feature_df["timestamp"] == timestamp)
    ]

    if len(plant_df) == 0:
        return {"error": f"No data found for {plant_id} at {timestamp}"}

    existing_cols = [f for f in feature_cols if f in plant_df.columns]
    X = plant_df[existing_cols].iloc[[0]]

    explainer   = get_shap_explainer(model)
    shap_values = explainer.shap_values(X)
    base_value  = float(explainer.expected_value)

    if np.ndim(shap_values) > 1:
        sv = shap_values[0]
    else:
        sv = shap_values

    pred_plf = float(model.predict(X)[0])
    pred_mw  = round(pred_plf * installed_capacity_mw, 2)

    local_df = compute_local_shap(model, X, existing_cols, installed_capacity_mw)
    top5 = local_df.head(5)

    top_drivers = []
    for _, row in top5.iterrows():
        top_drivers.append({
            "feature":    row["feature"],
            "value":      round(float(row["value"]), 4),
            "shap_value": round(float(row["shap_value"]), 4),
            "direction":  row["direction"],
        })

    # Narrative
    top_feature = top5.iloc[0]["feature"] if len(top5) > 0 else "unknown"
    direction   = top5.iloc[0]["direction"] if len(top5) > 0 else ""
    narrative = (
        f"The model predicts {pred_mw:.1f} MW "
        f"(PLF {pred_plf:.2%}). "
        f"The primary driver is '{top_feature}' which {direction.lower()} the forecast."
    )

    return {
        "plant_id":       plant_id,
        "timestamp":      str(timestamp),
        "base_value_plf": round(base_value, 4),
        "predicted_plf":  round(pred_plf, 4),
        "predicted_mw":   pred_mw,
        "top_drivers":    top_drivers,
        "narrative":      narrative,
    }


# --------------------------------------------------------------------------- #
# Drift Detection
# --------------------------------------------------------------------------- #
def compute_rolling_residuals(actuals: pd.Series,
                               predictions: pd.Series,
                               window_days: int = 3,
                               freq_min: int = 15) -> pd.DataFrame:
    """
    Compute rolling mean forecast error per plant to detect sensor drift.

    If the rolling mean error is consistently in the same direction over
    window_days, it suggests something has changed in the data (not the weather).

    Parameters
    ----------
    actuals     : actual generation values (MW or PLF)
    predictions : model predicted values (same unit)
    window_days : rolling window in days
    freq_min    : data frequency in minutes

    Returns
    -------
    DataFrame with [residual, rolling_mean_residual, drift_flag]
    """
    n_intervals = window_days * (24 * 60 // freq_min)

    residuals = actuals - predictions
    roll_mean = residuals.rolling(n_intervals, min_periods=n_intervals // 2).mean()

    # Drift flag: rolling mean consistently > 0 (over-forecasting) or < 0 (under)
    drift_threshold = actuals.std() * 0.1  # 10% of std as threshold

    drift_flag = pd.Series("STABLE", index=residuals.index)
    drift_flag[roll_mean >  drift_threshold] = "OVER_FORECASTING"
    drift_flag[roll_mean < -drift_threshold] = "UNDER_FORECASTING"

    return pd.DataFrame({
        "residual":             residuals,
        "rolling_mean_residual": roll_mean,
        "drift_flag":           drift_flag,
    })
