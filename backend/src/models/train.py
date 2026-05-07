"""
Model Training — LightGBM Quantile Regression

Training strategy:
  - Separate models for Solar and Wind (physics-correct separation)
  - Quantile regression for P10 (0.10), P50 (0.50), P90 (0.90)
  - Time-series cross-validation (no data leakage)
  - Baseline models: Persistence and Climatological
  - Metrics: RMSE, MAPE, Pinball Loss
  - Models saved to models/saved/
"""

import pandas as pd
import numpy as np
import logging
import json
import joblib
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import lightgbm as lgb
from sklearn.metrics import mean_squared_error, mean_absolute_percentage_error

from src.features.engineering import (
    SOLAR_FEATURES, WIND_FEATURES, CATEGORICAL_FEATURES, TARGET, build_features
)

logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).resolve().parents[3] / "models" / "saved"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

QUANTILES = [0.10, 0.50, 0.90]
QUANTILE_LABELS = {0.10: "p10", 0.50: "p50", 0.90: "p90"}


# --------------------------------------------------------------------------- #
# LightGBM hyperparameters
# --------------------------------------------------------------------------- #
def get_lgb_params(quantile: float, plant_type: str = "solar") -> dict:
    """Return LightGBM parameters for quantile regression, differentiated by plant type."""
    base_params = {
        "objective":        "quantile",
        "alpha":            quantile,
        "metric":           "quantile",
        "boosting_type":    "gbdt",
        "n_jobs":           -1,
        "verbose":          -1,
        "random_state":     42,
    }
    
    if plant_type == "wind":
        # Wind hyperparameters — tuned for Karnataka wind corridor characteristics:
        #
        # Physics rationale:
        #   - Wind power ∝ V³ (cubic), so the model needs enough leaves to
        #     approximate the steep ramp between cut-in (~3 m/s) and rated
        #     speed (~12 m/s), but not so many that it overfits gust noise.
        #   - 23 input features (4 wind, 3 met, 7 cyclical time, 2 calendar,
        #     3 lags, 6 rolling stats) → max_depth=8 is sufficient for the
        #     interaction space without combinatorial explosion.
        #   - Karnataka wind is monsoon-dominated (Jun-Sep) with high
        #     inter-seasonal variance → stronger bagging helps generalize
        #     across dry vs monsoon regimes.
        #   - L1 regularization for feature selection (wind_u/wind_v may be
        #     noisy if direction data is sparse), L2 to smooth leaf values.
        #
        specific_params = {
            "n_estimators":      1500,       # enough trees for slow learning rate
            "learning_rate":     0.015,      # slow learner → better generalization
            "num_leaves":        95,         # 2^8-1 range; captures cubic curve
            "max_depth":         8,          # bounded depth prevents gust overfitting
            "min_child_samples": 50,         # wind PLF is heavy-tailed; need robust leaves
            "min_split_gain":    0.01,       # skip trivial splits on noisy features
            "feature_fraction":  0.75,       # decorrelate trees across 23 features
            "bagging_fraction":  0.7,        # subsample rows for variance reduction
            "bagging_freq":      5,          # re-sample every 5 iterations
            "lambda_l1":         0.3,        # mild L1: prune weak wind_u/wind_v splits
            "lambda_l2":         0.2,        # gentle L2: smooth leaf outputs
        }
    else:
        # Solar hyperparameters (untouched)
        specific_params = {
            "n_estimators":     1000,
            "learning_rate":    0.03,
            "num_leaves":       63,
            "max_depth":        -1,
            "min_child_samples": 30,
            "feature_fraction": 0.8,
            "bagging_fraction": 0.8,
            "bagging_freq":     5,
            "lambda_l1":        0.1,
            "lambda_l2":        0.1,
        }
        
    return {**base_params, **specific_params}


# --------------------------------------------------------------------------- #
# Time-series cross-validation splits
# --------------------------------------------------------------------------- #
def time_series_splits(df: pd.DataFrame,
                       n_splits: int = 3,
                       val_months: int = 1) -> List[Tuple[pd.Index, pd.Index]]:
    """
    Generate rolling time-series train/validation splits.
    Ensures the validation window is always strictly AFTER the training window.

    Parameters
    ----------
    df         : feature-engineered DataFrame with 'timestamp' column
    n_splits   : number of (train, val) pairs to generate
    val_months : size of each validation window in months

    Returns
    -------
    List of (train_index, val_index) tuples
    """
    timestamps = df["timestamp"].sort_values()
    total_months = (
        (timestamps.max().year - timestamps.min().year) * 12 +
        timestamps.max().month - timestamps.min().month
    )

    if total_months < n_splits + val_months:
        logger.warning(
            f"Dataset spans only {total_months} months — reducing to 1 split."
        )
        n_splits = 1

    splits = []
    for i in range(n_splits):
        # Validation window: last n_splits-i months back
        val_end_offset   = (n_splits - i) * val_months
        val_start_offset = val_end_offset + val_months

        val_end   = timestamps.max() - pd.DateOffset(months=val_end_offset - val_months)
        val_start = timestamps.max() - pd.DateOffset(months=val_start_offset)

        val_mask   = (df["timestamp"] >= val_start) & (df["timestamp"] < val_end)
        train_mask = df["timestamp"] < val_start

        if train_mask.sum() == 0 or val_mask.sum() == 0:
            continue

        splits.append((df.index[train_mask], df.index[val_mask]))

    logger.info(f"Generated {len(splits)} time-series CV splits")
    return splits


# --------------------------------------------------------------------------- #
# Baseline models
# --------------------------------------------------------------------------- #
def persistence_forecast(val_df: pd.DataFrame) -> pd.Series:
    """
    Persistence baseline: predict next interval = last known PLF.
    Uses lag_1 feature (last 15-min actual PLF).
    """
    return val_df["plf_lag_1"].fillna(0)


def climatological_forecast(train_df: pd.DataFrame,
                             val_df: pd.DataFrame) -> pd.Series:
    """
    Climatological baseline: predict mean PLF for the same (month, hour, plant_type).
    """
    climate = (
        train_df.groupby(["month", "hour", "plant_type"])["plf"]
        .mean()
        .reset_index()
        .rename(columns={"plf": "climate_plf"})
    )
    val_merged = val_df.merge(climate, on=["month", "hour", "plant_type"], how="left")
    return val_merged["climate_plf"].fillna(val_df["plf"].mean())


# --------------------------------------------------------------------------- #
# Evaluation metrics
# --------------------------------------------------------------------------- #
def pinball_loss(y_true: np.ndarray,
                 y_pred: np.ndarray,
                 quantile: float) -> float:
    """Pinball / quantile loss — measures calibration of quantile forecasts."""
    residuals = y_true - y_pred
    return np.mean(
        np.where(residuals >= 0, quantile * residuals, (quantile - 1) * residuals)
    )


def evaluate_predictions(y_true: np.ndarray,
                          y_pred: np.ndarray,
                          label: str = "",
                          quantile: Optional[float] = None) -> dict:
    """Compute RMSE, MAPE, and optionally Pinball Loss."""
    # Avoid division by zero in MAPE
    nonzero = y_true > 1e-3
    mape = (
        mean_absolute_percentage_error(y_true[nonzero], y_pred[nonzero]) * 100
        if nonzero.sum() > 0 else np.nan
    )
    metrics = {
        "label": label,
        "rmse":  float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "mape":  float(mape),
        "n":     int(len(y_true)),
    }
    if quantile is not None:
        metrics["pinball_loss"] = float(pinball_loss(y_true, y_pred, quantile))

    logger.info(
        f"[{label}] RMSE={metrics['rmse']:.4f} | MAPE={metrics['mape']:.2f}% "
        + (f"| Pinball(q={quantile})={metrics.get('pinball_loss', 'N/A'):.4f}" if quantile else "")
    )
    return metrics


# --------------------------------------------------------------------------- #
# Core training function for one plant type
# --------------------------------------------------------------------------- #
def train_plant_type(df: pd.DataFrame,
                     plant_type: str) -> Dict[str, lgb.LGBMRegressor]:
    """
    Train P10, P50, P90 LightGBM models for a given plant type.

    Parameters
    ----------
    df         : full feature-engineered DataFrame
    plant_type : 'solar' or 'wind'

    Returns
    -------
    dict mapping quantile label to trained LGBMRegressor
    """
    subset = df[df["plant_type"] == plant_type].copy()

    if len(subset) == 0:
        logger.warning(f"No data for plant_type='{plant_type}'. Skipping.")
        return {}

    feature_cols = SOLAR_FEATURES if plant_type == "solar" else WIND_FEATURES
    # Only keep feature columns that exist in the dataset
    feature_cols = [f for f in feature_cols if f in subset.columns]
    cat_features  = [c for c in CATEGORICAL_FEATURES if c in subset.columns]
    for c in cat_features:
        subset[c] = subset[c].astype("category")
        if c not in feature_cols:
            feature_cols.append(c)

    logger.info(
        f"\n{'='*60}\n"
        f"Training {plant_type.upper()} models | "
        f"Rows: {len(subset):,} | Features: {len(feature_cols)}\n"
        f"{'='*60}"
    )

    splits = time_series_splits(subset)
    all_metrics = []
    trained_models = {}

    for quantile in QUANTILES:
        q_label = QUANTILE_LABELS[quantile]
        logger.info(f"\n--- Training {plant_type} {q_label.upper()} model ---")

        cv_rmse = []
        best_model = None

        for fold_idx, (train_idx, val_idx) in enumerate(splits):
            train_df = subset.loc[train_idx]
            val_df   = subset.loc[val_idx]

            X_train = train_df[feature_cols]
            y_train = train_df[TARGET].values
            X_val   = val_df[feature_cols]
            y_val   = val_df[TARGET].values

            params = get_lgb_params(quantile, plant_type)
            model  = lgb.LGBMRegressor(**params)

            model.fit(
                X_train, y_train,
                eval_set=[(X_val, y_val)],
                callbacks=[lgb.early_stopping(50, verbose=False),
                           lgb.log_evaluation(period=0)],
                categorical_feature=cat_features if cat_features else "auto",
            )

            y_pred = model.predict(X_val).clip(0, 1)
            fold_metrics = evaluate_predictions(
                y_val, y_pred,
                label=f"{plant_type}_{q_label}_fold{fold_idx+1}",
                quantile=quantile
            )
            cv_rmse.append(fold_metrics["rmse"])
            best_model = model  # Last fold becomes the production model

            # Baselines (only for P50 to avoid verbosity)
            if quantile == 0.50 and fold_idx == len(splits) - 1:
                persist_pred = persistence_forecast(val_df).values
                climate_pred = climatological_forecast(train_df, val_df).values
                evaluate_predictions(y_val, persist_pred,
                                     label=f"{plant_type}_persistence_fold{fold_idx+1}")
                evaluate_predictions(y_val, climate_pred,
                                     label=f"{plant_type}_climatological_fold{fold_idx+1}")

        mean_cv_rmse = np.mean(cv_rmse)
        logger.info(f"{plant_type} {q_label.upper()} — Mean CV RMSE: {mean_cv_rmse:.4f}")
        trained_models[q_label] = best_model
        all_metrics.append({"plant_type": plant_type, "quantile": q_label,
                             "cv_rmse": mean_cv_rmse})

    # Save metrics
    metrics_path = MODELS_DIR / f"{plant_type}_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(all_metrics, f, indent=2)
    logger.info(f"Metrics saved to {metrics_path}")

    return trained_models


# --------------------------------------------------------------------------- #
# Save and load utilities
# --------------------------------------------------------------------------- #
def save_models(models: dict, plant_type: str) -> None:
    """Persist trained models and feature column lists to disk."""
    for q_label, model in models.items():
        model_path = MODELS_DIR / f"{plant_type}_{q_label}.pkl"
        joblib.dump(model, model_path)
        logger.info(f"Model saved: {model_path}")

    # Save the feature list used for this plant type
    feature_cols = (SOLAR_FEATURES if plant_type == "solar" else WIND_FEATURES) + CATEGORICAL_FEATURES
    meta_path = MODELS_DIR / f"{plant_type}_feature_cols.json"
    with open(meta_path, "w") as f:
        json.dump(feature_cols, f)


def load_models(plant_type: str) -> Dict[str, lgb.LGBMRegressor]:
    """Load previously trained models for a given plant type."""
    models = {}
    for q_label in ["p10", "p50", "p90"]:
        model_path = MODELS_DIR / f"{plant_type}_{q_label}.pkl"
        if not model_path.exists():
            raise FileNotFoundError(
                f"Model not found: {model_path}. Run train.py first."
            )
        models[q_label] = joblib.load(model_path)
    return models


def load_feature_cols(plant_type: str) -> List[str]:
    """Load the feature column list for a plant type."""
    meta_path = MODELS_DIR / f"{plant_type}_feature_cols.json"
    if not meta_path.exists():
        return (SOLAR_FEATURES if plant_type == "solar" else WIND_FEATURES) + CATEGORICAL_FEATURES
    with open(meta_path) as f:
        return json.load(f)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def run_training(scada_path: Optional[str] = None,
                 nwp_path:   Optional[str] = None) -> None:
    """
    Full training pipeline:
      1. Load data
      2. Clean data
      3. Build features
      4. Train Solar models
      5. Train Wind models
      6. Save all models
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    from src.data.loader import load_all
    from src.data.cleaner import clean

    logger.info("=== Starting Training Pipeline ===")
    raw_df          = load_all(scada_path, nwp_path)
    training_df, _  = clean(raw_df)
    feature_df      = build_features(training_df)

    for plant_type in ["solar", "wind"]:
        models = train_plant_type(feature_df, plant_type)
        if models:
            save_models(models, plant_type)

    logger.info("=== Training Pipeline Complete ===")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Train Renewable Forecasting Models")
    parser.add_argument("--scada", type=str, default=None, help="Path to SCADA CSV")
    parser.add_argument("--nwp",   type=str, default=None, help="Path to NWP CSV")
    parser.add_argument("--type",  type=str, default=None, help="Plant type to train (solar or wind). Defaults to both.")
    args = parser.parse_args()
    
    # Filter plant types based on argument
    types = ["solar", "wind"]
    if args.type:
        types = [args.type.lower()]
        
    logging.basicConfig(level=logging.INFO)
    from src.data.loader import load_all
    from src.data.cleaner import clean
    from src.features.engineering import build_features

    df = load_all(args.scada, args.nwp)
    training_df, _ = clean(df)
    feature_df = build_features(training_df)

    for plant_type in types:
        models = train_plant_type(feature_df, plant_type)
        if models:
            save_models(models, plant_type)
