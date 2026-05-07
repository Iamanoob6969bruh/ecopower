import os
import pandas as pd
import numpy as np
import lightgbm as lgb

# Paths
BASE_DIR = r"c:\Users\FSOS\Desktop\ah final not\ECO_POWER"
MODEL_PATH = os.path.join(BASE_DIR, 'solar_lightgbm.txt')

def test_model():
    if not os.path.exists(MODEL_PATH):
        print(f"Model not found at {MODEL_PATH}")
        return

    bst = lgb.Booster(model_file=MODEL_PATH)
    features = bst.feature_name()
    importance = bst.feature_importance(importance_type='gain')
    feat_imp = sorted(zip(features, importance), key=lambda x: x[1], reverse=True)
    
    print("Top 20 Features by Gain:")
    for f, imp in feat_imp[:20]:
        print(f"{f}: {imp}")

if __name__ == "__main__":
    test_model()
