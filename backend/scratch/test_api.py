import requests
import json

try:
    response = requests.get("http://localhost:8000/api/summary/total/solar")
    print(f"Status: {response.status_code}")
    print(f"Data: {json.dumps(response.json(), indent=2)}")
except Exception as e:
    print(f"Error: {e}")
