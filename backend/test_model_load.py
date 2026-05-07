import lightgbm as lgb
import os

model_path = r"c:\Users\wadaf\OneDrive\Desktop\RF\solar_lightgbm.txt"
if not os.path.exists(model_path):
    print(f"Model NOT found at {model_path}")
else:
    try:
        bst = lgb.Booster(model_file=model_path)
        print("Model loaded successfully!")
        print(f"Feature names: {bst.feature_name()[:5]}...")
    except Exception as e:
        print(f"Error loading model: {e}")
