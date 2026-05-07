import sqlite3
conn = sqlite3.connect('backend/dashboard.db')
cursor = conn.cursor()
query = "SELECT timestamp, actual_kw, predicted_kw FROM generation_data WHERE plant_id='kpcl_shivanasamudra' AND timestamp >= '2026-05-06 14:00:00' AND timestamp <= '2026-05-06 17:00:00' LIMIT 10"
cursor.execute(query)
rows = cursor.fetchall()
for r in rows:
    print(f"TS: {r[0]} | Actual: {r[1]} | Pred: {r[2]}")
conn.close()
