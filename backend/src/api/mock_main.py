from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from pathlib import Path
import sqlite3
import pandas as pd
from datetime import datetime
import threading

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_sync_lock = threading.Lock()
_last_sync: datetime | None = None

@app.get("/health")
async def health():
    return {"status": "ok", "mock": False, "source": "kptclsldc.in"}

def sync_sldc(max_age_seconds: int = 55):
    global _last_sync
    now = datetime.now()
    if _last_sync and (now - _last_sync).total_seconds() < max_age_seconds:
        return
    if not _sync_lock.acquire(blocking=False):
        return
    from src.data.scraper import run_scrape
    try:
        run_scrape()
        _last_sync = datetime.now()
    finally:
        _sync_lock.release()

def db_path() -> Path:
    return Path("data/karnataka_solar.db")

@app.get("/sldc/status")
async def get_sldc_status():
    sync_sldc()
    con = sqlite3.connect(db_path())
    df = pd.read_sql("SELECT * FROM default_readings ORDER BY scraped_at DESC LIMIT 1", con)
    con.close()
    if df.empty:
        return {"status": "error", "message": "No SLDC data found"}
    row = df.iloc[0]
    return {
        "timestamp": row["sldc_ts"],
        "scraped_at": row["scraped_at"],
        "frequency": row["frequency"],
        "solar_mw": row["solar_mw"],
        "wind_mw": row["wind_mw"],
        "hydro_mw": row["hydro_mw"],
        "thermal_mw": row["thermal_mw"],
        "thermal_ipp_mw": row["thermal_ipp_mw"],
        "state_demand_mw": row["state_demand_mw"],
        "live_generation_mw": row["total_generation_mw"],
        "ncep_mw": row["solar_mw"] + row["wind_mw"],
        "is_stale": False,
    }

@app.get("/sldc/generation")
async def get_sldc_generation():
    sync_sldc()
    con = sqlite3.connect(db_path())
    df = pd.read_sql(
        """
        SELECT d.sldc_ts, d.state_demand_mw, d.total_generation_mw, d.solar_mw, d.wind_mw, d.scraped_at
        FROM default_readings
        d
        INNER JOIN (
            SELECT sldc_ts, MAX(id) AS id
            FROM default_readings
            WHERE sldc_ts IS NOT NULL AND sldc_ts != ''
            GROUP BY sldc_ts
        ) latest
          ON latest.id = d.id
        ORDER BY d.scraped_at DESC
        LIMIT 48
        """,
        con,
    )
    con.close()
    return df.sort_values("scraped_at").to_dict(orient="records")

@app.post("/sldc/sync")
async def sldc_sync():
    sync_sldc(max_age_seconds=0)
    return {"status": "ok"}

@app.get("/sldc/assets")
async def get_sldc_assets():
    sync_sldc()
    con = sqlite3.connect(db_path())
    default_df = pd.read_sql("SELECT * FROM default_readings ORDER BY scraped_at DESC LIMIT 1", con)
    ncep_df = pd.read_sql("SELECT * FROM ncep_readings WHERE scraped_at = (SELECT MAX(scraped_at) FROM ncep_readings) ORDER BY escom", con)
    plant_df = pd.read_sql("SELECT * FROM stategen_readings WHERE scraped_at = (SELECT MAX(scraped_at) FROM stategen_readings) ORDER BY plant", con)
    con.close()
    assets = []
    if not default_df.empty:
        row = default_df.iloc[0]
        for asset_id, name, asset_type, value in [
            ("SOLAR", "Solar", "solar", row["solar_mw"]),
            ("WIND", "Wind", "wind", row["wind_mw"]),
            ("HYDRO", "Hydro", "hydro", row["hydro_mw"]),
            ("THERMAL", "Thermal", "thermal", row["thermal_mw"]),
            ("THERMAL_IPP", "Thermal IPP", "thermal", row["thermal_ipp_mw"]),
            ("OTHER", "Other", "other", row["other_mw"]),
        ]:
            assets.append({"asset_id": asset_id, "name": name, "asset_type": asset_type, "generation_mw": float(value or 0), "timestamp": row["sldc_ts"], "source": "Default.aspx"})
    for _, row in ncep_df.iterrows():
        assets.append({"asset_id": f"NCEP_{row['escom']}", "name": row["escom"], "asset_type": "ncep_zone", "generation_mw": float((row["solar_mw"] or 0) + (row["wind_mw"] or 0)), "solar_mw": float(row["solar_mw"] or 0), "wind_mw": float(row["wind_mw"] or 0), "timestamp": row["sldc_ts"], "source": "StateNCEP.aspx"})
    for _, row in plant_df.iterrows():
        assets.append({"asset_id": f"PLANT_{row['plant']}", "name": row["plant"], "asset_type": "conventional_plant", "capacity_mw": float(row["capacity_mw"] or 0), "generation_mw": float(row["generation_mw"] or 0), "timestamp": row["sldc_ts"], "source": "StateGen.aspx"})
    return {"assets": assets}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
