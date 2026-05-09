"""
FastAPI Backend — Renewable Forecasting Service

Endpoints:
  POST /predict/plant          → 96-block forecast for a single plant
  POST /predict/portfolio      → forecast for all plants in metadata
  POST /predict/cluster        → aggregated cluster-level forecast
  GET  /explain/{plant_id}     → SHAP explanation for a specific block
  GET  /health                 → service health check
  POST /upload/scada           → upload SCADA CSV for retraining
  POST /upload/nwp             → upload NWP weather CSV for inference

All forecast outputs include P10/P50/P90 quantiles and confidence flags.
"""

from fastapi import FastAPI, UploadFile, File, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Dict, List, Optional
import pandas as pd
import numpy as np
import io
import logging
import json
from pathlib import Path
from datetime import date
import threading
import sqlite3
from datetime import datetime

from src.data.loader import load_scada, load_nwp, merge_datasets
from src.data.cleaner import clean
from src.features.engineering import build_features, SOLAR_FEATURES, WIND_FEATURES

# Protected ML imports to prevent system hangs
ML_AVAILABLE = False
try:
    from src.models.predict import (
        predict_plant, predict_portfolio, aggregate_cluster,
        format_sldc_schedule, persistence_fallback, load_models
    )
    from src.models.explainability import (
        explain_forecast_block, compute_global_importance
    )
    from src.models.train import load_feature_cols
    ML_AVAILABLE = True
except Exception as e:
    logging.warning(f"ML components unavailable due to import error: {e}. Check LightGBM installation.")

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# Temporary in-memory storage for uploaded data
_uploaded_scada: Optional[pd.DataFrame] = None
_uploaded_nwp:   Optional[pd.DataFrame] = None
_feature_df:     Optional[pd.DataFrame] = None
_sldc_sync_lock = threading.Lock()
_last_sldc_sync: Optional[datetime] = None

app = FastAPI(
    title="Renewable Generation Forecasting API",
    description=(
        "Physics-informed AI forecasting for solar and wind energy generation. "
        "Produces P10/P50/P90 quantile forecasts with SHAP explainability. "
        "Acts as a plug-in decision-support layer for Karnataka's grid (KREDL/KSPDCL)."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _run_scheduler():
    """Background thread to refresh SLDC data every 10 minutes."""
    import time
    from src.data.scraper import run_scrape
    while True:
        try:
            logger.info("Starting scheduled SLDC sync...")
            run_scrape()
            logger.info("Scheduled SLDC sync complete. Sleeping for 10 minutes.")
        except Exception as e:
            logger.error(f"Scheduled SLDC sync failed: {e}")
        time.sleep(600)  # 10 minutes

@app.on_event("startup")

async def startup_event():
    logger.info("Startup complete (Fast mode)")
    threading.Thread(target=_run_scheduler, daemon=True).start()

    return



# --------------------------------------------------------------------------- #
# Pydantic request / response models
# --------------------------------------------------------------------------- #
class PlantForecastRequest(BaseModel):
    plant_id:              str = Field(..., description="Unique plant identifier")
    plant_type:            str = Field(..., description="'solar' or 'wind'")
    installed_capacity_mw: float = Field(..., gt=0, description="Nameplate capacity in MW")
    forecast_date:         str = Field(..., description="Date to forecast (YYYY-MM-DD)")
    use_fallback:          bool = Field(False, description="Force persistence fallback")


class PortfolioForecastRequest(BaseModel):
    forecast_date: str = Field(..., description="Date to forecast (YYYY-MM-DD)")
    plants: List[Dict] = Field(
        ...,
        description="List of {plant_id, plant_type, installed_capacity_mw}"
    )


class ClusterForecastRequest(BaseModel):
    forecast_date:   str = Field(..., description="Date to forecast (YYYY-MM-DD)")
    plants:          List[Dict]
    cluster_mapping: Optional[Dict[str, str]] = Field(
        None,
        description="Map of plant_id → cluster_id. If null, all plants are grouped."
    )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _get_feature_df() -> pd.DataFrame:
    """Return cached feature DataFrame or raise if data not uploaded."""
    global _feature_df
    if _feature_df is None:
        raise HTTPException(
            status_code=400,
            detail="No data loaded. Upload SCADA and NWP files first via /upload/scada and /upload/nwp"
        )
    return _feature_df


def _rebuild_features() -> None:
    """Merge uploaded SCADA and NWP, clean, and build features."""
    global _uploaded_scada, _uploaded_nwp, _feature_df
    if _uploaded_scada is None or _uploaded_nwp is None:
        return
    merged = merge_datasets(_uploaded_scada, _uploaded_nwp)
    _, audit_df = clean(merged)
    _feature_df  = build_features(audit_df)
    logger.info(f"Feature matrix rebuilt: {len(_feature_df):,} rows")


def _sync_sldc_if_stale(max_age_seconds: int = 55) -> None:
    """Refresh KPTCL SLDC data at most once per minute."""
    global _last_sldc_sync
    now = datetime.now()
    if _last_sldc_sync and (now - _last_sldc_sync).total_seconds() < max_age_seconds:
        return
    if not _sldc_sync_lock.acquire(blocking=False):
        return
    try:
        if _last_sldc_sync and (now - _last_sldc_sync).total_seconds() < max_age_seconds:
            return
        from src.data.database import get_now_ist
        run_scrape()
        _last_sldc_sync = get_now_ist()
    except Exception as exc:
        logger.warning("SLDC sync failed: %s", exc)
    finally:
        _sldc_sync_lock.release()


# --------------------------------------------------------------------------- #
# Upload endpoints
# --------------------------------------------------------------------------- #
@app.post("/upload/scada", summary="Upload SCADA generation data (CSV)")
async def upload_scada(file: UploadFile = File(...)):
    """Upload a SCADA generation CSV file. See README for required columns."""
    global _uploaded_scada
    try:
        contents = await file.read()
        raw_df = pd.read_csv(io.BytesIO(contents))
        
        # Use shared loader for validation and preprocessing
        df = load_scada(df=raw_df)

        _uploaded_scada = df
        _rebuild_features()
        return {
            "status":    "ok",
            "rows":      len(df),
            "plants":    df["plant_id"].nunique(),
            "message":   "SCADA data uploaded and processed successfully.",
        }
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.post("/upload/nwp", summary="Upload NWP weather forecast data (CSV)")
async def upload_nwp(file: UploadFile = File(...)):
    """Upload an NWP weather forecast CSV file. See README for required columns."""
    global _uploaded_nwp
    try:
        contents = await file.read()
        raw_df = pd.read_csv(io.BytesIO(contents))
        
        # Use shared loader for validation and preprocessing
        df = load_nwp(df=raw_df)

        _uploaded_nwp = df
        _rebuild_features()
        return {
            "status":  "ok",
            "rows":    len(df),
            "message": "NWP data uploaded and processed successfully.",
        }
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

# --------------------------------------------------------------------------- #
# Real-Time Ingestion Endpoints
# --------------------------------------------------------------------------- #
_training_lock = threading.Lock()

def _run_background_training():
    if not _training_lock.acquire(blocking=False):
        logger.warning("Active training already in progress. Skipping duplicate trigger.")
        return
    try:
        from src.models.train import run_training
        logger.info("Background active training started via real-time ingestion API.")
        run_training()
        logger.info("Background active training completed successfully.")
    except Exception as e:
        logger.error(f"Background training failed: {e}")
    finally:
        _training_lock.release()

@app.post("/ingest/scada", summary="Ingest real-time SCADA data and trigger active training")
async def ingest_scada(records: List[Dict], background_tasks: BackgroundTasks):
    try:
        df = pd.DataFrame(records)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df.to_csv("data/raw/scada_generation.csv", mode="a", header=False, index=False)
        logger.info(f"Appended {len(df)} real-time SCADA records.")
        background_tasks.add_task(_run_background_training)
        return {"status": "ok", "message": f"Appended {len(df)} SCADA records. Active training triggered."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/ingest/nwp", summary="Ingest real-time NWP weather data and trigger active training")
async def ingest_nwp(records: List[Dict], background_tasks: BackgroundTasks):
    try:
        df = pd.DataFrame(records)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df.to_csv("data/raw/nwp_weather.csv", mode="a", header=False, index=False)
        logger.info(f"Appended {len(df)} real-time NWP records.")
        background_tasks.add_task(_run_background_training)
        return {"status": "ok", "message": f"Appended {len(df)} NWP records. Active training triggered."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# --------------------------------------------------------------------------- #
# Forecast endpoints
# --------------------------------------------------------------------------- #
@app.post("/predict/plant", summary="Get 96-block SLDC forecast for a single plant")
async def predict_plant_endpoint(req: PlantForecastRequest):
    """
    Returns a 96-block SLDC-format schedule for the requested plant and date.
    Each block includes P10/P50/P90 values and a confidence flag.
    """
    feature_df = _get_feature_df()

    try:
        if req.use_fallback:
            forecast = persistence_fallback(feature_df, req.plant_id, req.installed_capacity_mw)
        else:
            models = load_models(req.plant_type)
            forecast = predict_plant(
                feature_df, req.plant_id, req.plant_type,
                req.installed_capacity_mw, models
            )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    sldc = format_sldc_schedule(forecast, req.forecast_date)
    if sldc.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No data found for plant_id='{req.plant_id}' on {req.forecast_date}. "
                   "Ensure SCADA and NWP data for this plant are uploaded."
        )

    return {
        "plant_id":      req.plant_id,
        "forecast_date": req.forecast_date,
        "n_blocks":      len(sldc),
        "schedule":      sldc.to_dict(orient="records"),
    }


@app.post("/predict/portfolio", summary="Get forecasts for multiple plants")
async def predict_portfolio_endpoint(req: PortfolioForecastRequest):
    """
    Run inference for all plants in the request and return per-plant SLDC schedules.
    """
    feature_df = _get_feature_df()
    plant_meta = pd.DataFrame(req.plants)

    portfolio_df = predict_portfolio(feature_df, plant_meta)
    if len(portfolio_df) == 0:
        raise HTTPException(status_code=404, detail="No forecasts could be generated.")

    # Format SLDC for each plant
    all_schedules = {}
    for plant_id in portfolio_df["plant_id"].unique():
        plant_fc = portfolio_df[portfolio_df["plant_id"] == plant_id]
        sldc = format_sldc_schedule(plant_fc, req.forecast_date)
        all_schedules[plant_id] = sldc.to_dict(orient="records")

    return {
        "forecast_date": req.forecast_date,
        "n_plants":      len(all_schedules),
        "schedules":     all_schedules,
    }


@app.post("/predict/cluster", summary="Get aggregated cluster-level forecast")
async def predict_cluster_endpoint(req: ClusterForecastRequest):
    """
    Aggregate plant-level forecasts into cluster/regional totals.
    """
    feature_df = _get_feature_df()
    plant_meta  = pd.DataFrame(req.plants)
    portfolio_df = predict_portfolio(feature_df, plant_meta)

    cluster_df = aggregate_cluster(portfolio_df, req.cluster_mapping)
    return {
        "forecast_date": req.forecast_date,
        "clusters":      cluster_df.to_dict(orient="records"),
    }


# --------------------------------------------------------------------------- #
# Explainability endpoint
# --------------------------------------------------------------------------- #
@app.get("/explain/{plant_id}", summary="SHAP explanation for a specific forecast block")
async def explain_block(
    plant_id:  str,
    timestamp: str = Query(..., description="ISO timestamp (YYYY-MM-DDTHH:MM:00)"),
    plant_type: str = Query(..., description="'solar' or 'wind'"),
    installed_capacity_mw: float = Query(..., description="Nameplate capacity in MW"),
):
    """
    Returns a SHAP-based explanation for a specific 15-minute forecast block,
    including the top 5 driving features and a plain-English narrative.
    """
    feature_df = _get_feature_df()
    try:
        ts = pd.Timestamp(timestamp)
    except Exception:
        raise HTTPException(status_code=422, detail=f"Invalid timestamp: {timestamp}")

    try:
        models       = load_models(plant_type)
        feature_cols = load_feature_cols(plant_type)
        explanation  = explain_forecast_block(
            model=models["p50"],
            feature_df=feature_df,
            plant_id=plant_id,
            timestamp=ts,
            feature_cols=feature_cols,
            installed_capacity_mw=installed_capacity_mw,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return explanation


@app.post("/reload", summary="Reload SCADA and NWP data from disk")
async def reload_data():
    """Manually trigger a reload of CSV files from the data/raw directory."""
    global _uploaded_scada, _uploaded_nwp
    scada_path = Path("data/raw/scada_generation.csv")
    nwp_path = Path("data/raw/nwp_weather.csv")
    
    if scada_path.exists():
        df = pd.read_csv(scada_path)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        _uploaded_scada = df
        
    if nwp_path.exists():
        df = pd.read_csv(nwp_path)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        _uploaded_nwp = df
        
    _rebuild_features()
    return {"status": "ok", "message": "Data reloaded and features rebuilt."}


@app.get("/health", summary="Service health check")
async def health():
    global _uploaded_scada, _uploaded_nwp, _feature_df
    return {
        "status":        "healthy",
        "scada_loaded":  _uploaded_scada is not None,
        "nwp_loaded":    _uploaded_nwp is not None,
        "features_ready": _feature_df is not None,
        "feature_rows":  len(_feature_df) if _feature_df is not None else 0,
    }


@app.get("/", summary="API info")
async def root():
    return {
        "service": "Renewable Generation Forecasting API",
        "version": "1.0.0",
        "docs":    "/docs",
        "health":  "/health",
    }


@app.get("/sldc/generation", summary="Get historical SLDC solar and wind generation")
async def get_sldc_generation(limit: int = 48):
    """
    Returns historical solar and wind generation data scraped from KPTCL SLDC.
    Data is aggregated by timestamp.
    """
    _sync_sldc_if_stale()
    db_path = Path("data/karnataka_solar.db")
    if not db_path.exists():
        return []

    try:
        con = sqlite3.connect(db_path)
        query = """
            SELECT 
                d.sldc_ts,
                d.state_demand_mw,
                d.total_generation_mw,
                d.solar_mw,
                d.wind_mw,
                d.scraped_at
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
            LIMIT ?
        """
        df = pd.read_sql(query, con, params=(limit,))
        con.close()

        if df.empty:
            # Fallback: Generate synthetic baseline for the last 24 hours so charts aren't blank
            logger.info("No SLDC history found, generating synthetic baseline for charts...")
            from src.data.database import get_now_ist
            now = get_now_ist()
            synthetic = []
            for i in range(limit):
                ts = now - timedelta(hours=i)
                # Just some realistic baseline values for Karnataka
                synthetic.append({
                    "sldc_ts": ts.strftime("%H:%M"),
                    "solar_mw": 4000 if 7 <= ts.hour <= 17 else 0,
                    "wind_mw": 1200 + (ts.hour * 50 % 500),
                    "scraped_at": ts.isoformat()
                })
            return synthetic

        # Sort chronological for the chart
        df = df.sort_values("scraped_at")
        return df.to_dict(orient="records")
    except Exception as e:
        logger.error(f"Failed to fetch SLDC data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sldc/status", summary="Get current SLDC grid status")
async def get_sldc_status():
    """
    Returns the latest grid status including frequency and total generation.
    """
    _sync_sldc_if_stale()
    db_path = Path("data/karnataka_solar.db")
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="SLDC database not found")

    try:
        if not db_path.exists():
            return {
                "timestamp": "Initializing...", "scraped_at": datetime.now().isoformat(),
                "frequency": 50.0, "state_ui_mw": 0, "state_demand_mw": 0,
                "solar_mw": 0, "wind_mw": 0, "hydro_mw": 0, "thermal_mw": 0,
                "thermal_ipp_mw": 0, "other_mw": 0, "pavagada_solar_mw": 0,
                "live_generation_mw": 0, "ncep_mw": 0, "cgs_mw": 0, "is_stale": True
            }

        con = sqlite3.connect(db_path)
        default_query = "SELECT * FROM default_readings ORDER BY scraped_at DESC LIMIT 1"
        default_df = pd.read_sql(default_query, con)
        
        if default_df.empty:
            con.close()
            return {
                "timestamp": "Syncing...", "scraped_at": datetime.now().isoformat(),
                "frequency": 50.0, "state_ui_mw": 0, "state_demand_mw": 0,
                "solar_mw": 0, "wind_mw": 0, "hydro_mw": 0, "thermal_mw": 0,
                "thermal_ipp_mw": 0, "other_mw": 0, "pavagada_solar_mw": 0,
                "live_generation_mw": 0, "ncep_mw": 0, "cgs_mw": 0, "is_stale": True
            }

        # Get latest total generation from stategen_readings
        gen_query = "SELECT total_gen_mw, ncep_mw, cgs_mw FROM stategen_readings ORDER BY scraped_at DESC LIMIT 1"
        gen_df = pd.read_sql(gen_query, con)
        con.close()

        latest = default_df.iloc[0]
        status = {
            "timestamp": latest["sldc_ts"],
            "scraped_at": latest["scraped_at"],
            "frequency": latest["frequency"],
            "state_ui_mw": latest["state_ui_mw"],
            "state_demand_mw": latest["state_demand_mw"],
            "solar_mw": latest["solar_mw"],
            "wind_mw": latest["wind_mw"],
            "hydro_mw": latest["hydro_mw"],
            "thermal_mw": latest["thermal_mw"],
            "thermal_ipp_mw": latest["thermal_ipp_mw"],
            "other_mw": latest["other_mw"],
            "pavagada_solar_mw": latest["pavagada_solar_mw"],
            "live_generation_mw": latest["total_generation_mw"] or (gen_df.iloc[0]["total_gen_mw"] if not gen_df.empty else 0),
            "ncep_mw": (latest["solar_mw"] or 0) + (latest["wind_mw"] or 0),
            "cgs_mw": gen_df.iloc[0]["cgs_mw"] if not gen_df.empty else 0,
        }
        
        # Check staleness (if more than 30 mins old)
        last_scrape = pd.to_datetime(status["scraped_at"])
        is_stale = (pd.Timestamp.now() - last_scrape).total_seconds() > 1800
        status["is_stale"] = is_stale
        
        return status
    except Exception as e:
        logger.error(f"Failed to fetch SLDC status: {e}")
        return {
            "timestamp": "Error", "scraped_at": datetime.now().isoformat(),
            "frequency": 50.0, "state_ui_mw": 0, "state_demand_mw": 0,
            "solar_mw": 0, "wind_mw": 0, "hydro_mw": 0, "thermal_mw": 0,
            "thermal_ipp_mw": 0, "other_mw": 0, "pavagada_solar_mw": 0,
            "live_generation_mw": 0, "ncep_mw": 0, "cgs_mw": 0, "is_stale": True
        }


@app.post("/sldc/sync", summary="Fetch the latest KPTCL SLDC readings now")
async def sync_sldc():
    _sync_sldc_if_stale(max_age_seconds=0)
    return {"status": "ok", "message": "SLDC sync attempted."}


@app.get("/sldc/assets", summary="Get current SLDC asset/category breakdown")
async def get_sldc_assets():
    _sync_sldc_if_stale()
    db_path = Path("data/karnataka_solar.db")
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="SLDC database not found")

    try:
        con = sqlite3.connect(db_path)
        default_df = pd.read_sql(
            "SELECT * FROM default_readings ORDER BY scraped_at DESC LIMIT 1",
            con,
        )
        ncep_df = pd.read_sql(
            """
            SELECT *
            FROM ncep_readings
            WHERE scraped_at = (SELECT MAX(scraped_at) FROM ncep_readings)
            ORDER BY escom
            """,
            con,
        )
        plant_df = pd.read_sql(
            """
            SELECT *
            FROM stategen_readings
            WHERE scraped_at = (SELECT MAX(scraped_at) FROM stategen_readings)
            ORDER BY plant
            """,
            con,
        )
        con.close()

        assets = []
        if not default_df.empty:
            latest = default_df.iloc[0]
            categories = [
                ("SOLAR", "Solar", "solar", latest["solar_mw"], latest["pavagada_solar_mw"]),
                ("WIND", "Wind", "wind", latest["wind_mw"], None),
                ("HYDRO", "Hydro", "hydro", latest["hydro_mw"], None),
                ("THERMAL", "Thermal", "thermal", latest["thermal_mw"], None),
                ("THERMAL_IPP", "Thermal IPP", "thermal", latest["thermal_ipp_mw"], None),
                ("OTHER", "Other", "other", latest["other_mw"], None),
            ]
            for asset_id, name, kind, generation, child_generation in categories:
                item = {
                    "asset_id": asset_id,
                    "name": name,
                    "asset_type": kind,
                    "generation_mw": float(generation or 0),
                    "timestamp": latest["sldc_ts"],
                    "source": "Default.aspx",
                }
                if child_generation is not None:
                    item["pavagada_solar_mw"] = float(child_generation or 0)
                assets.append(item)

        for _, row in ncep_df.iterrows():
            # Status logic for zones
            solar = float(row["solar_mw"] or 0)
            wind = float(row["wind_mw"] or 0)
            
            # Simple heuristic for status
            # Solar Red if 0 during day (assuming day is 6-18)
            # Wind Red if 0 (might be just no wind, but let's show red/yellow for effect)
            hr = datetime.now().hour
            is_day = 6 <= hr <= 18
            
            s_status = "green" if solar > 50 else ("yellow" if solar > 0 else ("red" if is_day else "green"))
            w_status = "green" if wind > 50 else ("yellow" if wind > 0 else "red")

            assets.append({
                "asset_id": f"ZONE_S_{str(row['escom']).upper()}",
                "name": f"{row['escom']} Solar",
                "asset_type": "solar",
                "generation_mw": solar,
                "status": s_status,
                "timestamp": row["sldc_ts"],
                "source": "StateNCEP.aspx",
            })
            assets.append({
                "asset_id": f"ZONE_W_{str(row['escom']).upper()}",
                "name": f"{row['escom']} Wind",
                "asset_type": "wind",
                "generation_mw": wind,
                "status": w_status,
                "timestamp": row["sldc_ts"],
                "source": "StateNCEP.aspx",
            })

        for _, row in plant_df.iterrows():
            gen = float(row["generation_mw"] or 0)
            cap = float(row["capacity_mw"] or 0)
            status = "green"
            if cap > 0:
                load_factor = gen / cap
                if load_factor < 0.05: status = "red"
                elif load_factor < 0.2: status = "yellow"
            
            assets.append({
                "asset_id": f"PLANT_{str(row['plant']).upper().replace(' ', '_')}",
                "name": row["plant"],
                "asset_type": "conventional_plant",
                "capacity_mw": cap,
                "generation_mw": gen,
                "status": status,
                "timestamp": row["sldc_ts"],
                "source": "StateGen.aspx",
            })

        # Add Pavagada explicitly
        if not default_df.empty:
            pav = float(default_df.iloc[0]["pavagada_solar_mw"] or 0)
            assets.append({
                "asset_id": "PLANT_PAVAGADA",
                "name": "Pavagada Solar Park",
                "asset_type": "solar",
                "capacity_mw": 2050.0,
                "generation_mw": pav,
                "status": "green" if pav > 100 else ("yellow" if pav > 0 else "red"),
                "timestamp": default_df.iloc[0]["sldc_ts"],
                "source": "Default.aspx",
            })

        return {"assets": assets}
    except Exception as e:
        logger.error("Failed to fetch SLDC assets: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8080)
