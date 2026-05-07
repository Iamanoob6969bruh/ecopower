import pandas as pd
import joblib
from sklearn.metrics import mean_absolute_percentage_error
from src.data.loader import load_scada, load_nwp, merge_datasets
from src.data.cleaner import clean
from src.features.engineering import build_features
from src.models.train import load_feature_cols

def test_accuracy():
    print("Loading data...")
    scada_df = load_scada("data/raw/scada_generation.csv")
    nwp_df = load_nwp("data/raw/nwp_weather.csv")
    
    # Merge and clean
    merged = merge_datasets(scada_df, nwp_df)
    clean_df, _ = clean(merged)
    
    # Build features
    print("Building features...")
    feature_df = build_features(clean_df)
    
    # Filter to Wind plants
    wind_df = feature_df[feature_df["plant_type"] == "wind"].copy()
    
    if len(wind_df) == 0:
        print("No wind data found to test.")
        return {"error": "No wind data found to test."}
        
    print(f"Testing on {len(wind_df)} historical records...")
    
    # Load trained P50 model
    try:
        model_p50 = joblib.load("models/saved/wind_p50.pkl")
    except FileNotFoundError:
        print("Trained model not found. Run train.py first.")
        return {"error": "Trained model not found. Run train.py first."}
        
    # Get feature columns used during training. Prefer model metadata because older
    # saved JSON files may not include categorical columns.
    feature_cols = getattr(model_p50, "feature_name_", None) or load_feature_cols("wind")
    feature_cols = [col for col in feature_cols if col in wind_df.columns]
        
    X = wind_df[feature_cols].copy()
    categories = getattr(getattr(model_p50, "booster_", None), "pandas_categorical", None)
    if categories and "plant_id" in X.columns:
        X["plant_id"] = pd.Categorical(X["plant_id"], categories=categories[0])
    y_true_plf = wind_df["plf"].fillna(0)
    
    # Predict
    print("Running predictions...")
    y_pred_plf = model_p50.predict(X).clip(0, 1)
    
    # Filter out near-zero generation instances where MAPE gets distorted
    mask = y_true_plf > 0.05
    y_true_filtered = y_true_plf[mask]
    y_pred_filtered = y_pred_plf[mask]
    
    if len(y_true_filtered) > 0:
        mape = mean_absolute_percentage_error(y_true_filtered, y_pred_filtered) * 100
        accuracy = max(0, 100 - mape)
        
        print("\n=== Model Accuracy Results ===")
        print(f"Mean Absolute Percentage Error (MAPE): {mape:.2f}%")
        print(f"Overall Forecast Accuracy:             {accuracy:.2f}%")
        print("==============================")
        return {
            "mape": mape,
            "accuracy": accuracy,
            "records": len(wind_df),
            "filtered_records": len(y_true_filtered)
        }
    else:
        print("Not enough non-zero data to calculate meaningful MAPE.")
        return {"error": "Not enough non-zero data to calculate meaningful MAPE."}

if __name__ == "__main__":
    test_accuracy()
