
import sqlite3
conn = sqlite3.connect('dashboard.db')
cursor = conn.cursor()
cursor.execute("SELECT plant_id, COUNT(*) FROM generation_data WHERE timestamp LIKE '2026-05-09%' GROUP BY plant_id")
print("Plant ID | Count (May 9th)")
print("-" * 30)
for row in cursor.fetchall():
    print(f"{row[0]} | {row[1]}")
conn.close()
