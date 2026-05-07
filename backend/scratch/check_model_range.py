import sys
import os
import pandas as pd
import numpy as np
import lightgbm as lgb

# Load model
model_path = os.path.join(os.getcwd(), 'scaled lightgbm example', 'synthetic_base_model.txt')
bst = lgb.Booster(model_file=model_path)
model_features = bst.feature_name()

# Test with GHI = 1000
test_data = {
    'GHI': [1000.0],
    'SZA': [30.0],
    'cos_SZA': [np.cos(np.radians(30))],
    'Temperature': [30.0],
    'TCC': [0.0],
    'hour_sin': [0.0],
    'hour_cos': [-1.0],
    'AM_relative': [1.15],
    'GHI_lag1': [950.0],
    'rolling_gen_efficiency': [0.85],
    'rolling_PR_proxy': [0.80],
    'Shading_Flag': [0]
}

df = pd.DataFrame(test_data)
for col in model_features:
    if col not in df.columns: df[col] = 0.0

pred = bst.predict(df[model_features])[0]
print(f"Prediction for 1000 W/m2: {pred}")
