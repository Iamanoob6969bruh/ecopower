import lightgbm as lgb
import os

model_path = r"c:\Users\wadaf\OneDrive\Desktop\RF\solar_lightgbm_fixed.txt"
if not os.path.exists(model_path):
    print(f"Model NOT found at {model_path}")
else:
    try:
        bst = lgb.Booster(model_file=model_path)
        print("Model loaded successfully!")
        print(f"Number of features: {len(bst.feature_name())}")
    except Exception as e:
        print(f"Error loading model: {e}")
