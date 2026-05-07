from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional, List
import pandas as pd

from src.data.database import get_db, GenerationData
from src.config.plants import get_plants, get_plant_by_id

router = APIRouter(prefix="/api")

@router.get("/plants")
def api_get_plants():
    return get_plants()

@router.get("/generation/{plant_id}")
def api_get_generation(
    plant_id: str, 
    start: Optional[str] = None, 
    end: Optional[str] = None, 
    db: Session = Depends(get_db)
):
    print(f"FETCHING GENERATION: plant={plant_id} start={start} end={end}")
    plant = get_plant_by_id(plant_id)
    if not plant:
        raise HTTPException(status_code=404, detail="Plant not found")
        
    query = db.query(GenerationData).filter(GenerationData.plant_id == plant_id)
    
    if start:
        try:
            # Handle 'Z' suffix and other ISO variations
            start_clean = start.replace('Z', '+00:00')
            start_dt = datetime.fromisoformat(start_clean).replace(tzinfo=None)
            query = query.filter(GenerationData.timestamp >= start_dt)
        except ValueError as e:
            print(f"Error parsing start date: {e}")
            pass
            
    if end:
        try:
            end_clean = end.replace('Z', '+00:00')
            end_dt = datetime.fromisoformat(end_clean).replace(tzinfo=None)
            query = query.filter(GenerationData.timestamp <= end_dt)
        except ValueError as e:
            print(f"Error parsing end date: {e}")
            pass
            
    records = query.order_by(GenerationData.timestamp.asc()).all()
    print(f"RETURNED {len(records)} records for {plant_id}")
    
    return [
        {
            "timestamp": r.timestamp.isoformat(),
            "actual_kw": r.actual_kw,
            "predicted_kw": r.predicted_kw,
            "zone_label": r.zone_label
        }
        for r in records
    ]

@router.get("/generation/live/all")
def api_get_live(db: Session = Depends(get_db)):
    """Returns the latest non-null actual and predicted value for all plants."""
    plants = get_plants()
    result = {}
    
    for p in plants:
        # Get latest actual record (not null)
        latest_actual = db.query(GenerationData).filter(
            GenerationData.plant_id == p['id'],
            GenerationData.actual_kw != None
        ).order_by(GenerationData.timestamp.desc()).first()
        
        result[p['id']] = {
            "timestamp": latest_actual.timestamp.isoformat() if latest_actual else None,
            "actual_kw": latest_actual.actual_kw if latest_actual else 0,
            "predicted_kw": latest_actual.predicted_kw if latest_actual else 0
        }
        
    return result

@router.get("/summary/{plant_id}")
def api_get_summary(plant_id: str, db: Session = Depends(get_db)):
    """Today's total generation, average prediction accuracy, peak timestamp/value."""
    now = datetime.now()
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    records = db.query(GenerationData).filter(
        GenerationData.plant_id == plant_id,
        GenerationData.timestamp >= start_of_today,
        GenerationData.timestamp <= now,
        GenerationData.actual_kw != None
    ).all()
    
    if not records:
        return {
            "total_kwh": 0,
            "avg_accuracy_pct": 0,
            "peak_kw": 0,
            "peak_time": None
        }
        
    total_kwh = sum(r.actual_kw for r in records) * 0.25 # 15 min interval = 0.25 hours
    
    # Calculate accuracy
    errors = []
    for r in records:
        if r.predicted_kw > 0 or r.actual_kw > 0:
            err = abs(r.actual_kw - r.predicted_kw)
            max_val = max(r.actual_kw, r.predicted_kw)
            if max_val > 0:
                errors.append(err / max_val)
    
    avg_error = sum(errors) / len(errors) if errors else 0
    accuracy = max(0, (1 - avg_error) * 100)
    
    peak_record = max(records, key=lambda x: x.actual_kw)
    
    return {
        "total_kwh": round(total_kwh, 2),
        "avg_accuracy_pct": round(accuracy, 2),
        "peak_kw": round(peak_record.actual_kw, 2),
        "peak_time": peak_record.timestamp.isoformat()
    }

@router.get("/summary/total/{plant_type}")
def api_get_total_summary(plant_type: str, db: Session = Depends(get_db)):
    """Aggregated today's generation for all plants of a type."""
    from src.config.plants import get_plants
    plants = [p for p in get_plants() if p['type'] == plant_type]
    
    now = datetime.now()
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    total_kwh = 0
    for p in plants:
        # Sum up generation for each plant
        res = db.query(GenerationData).filter(
            GenerationData.plant_id == p['id'],
            GenerationData.timestamp >= start_of_today,
            GenerationData.timestamp <= now,
            GenerationData.actual_kw != None
        ).all()
        if res:
            total_kwh += sum(r.actual_kw for r in res) * 0.25
            
    return {
        "plant_type": plant_type,
        "total_mwh": round(total_kwh / 1000, 2),
        "timestamp": now.isoformat()
    }

@router.get("/generation/aggregate/all")
def api_get_aggregated_generation(
    start: Optional[str] = None, 
    end: Optional[str] = None, 
    db: Session = Depends(get_db)
):
    """Aggregated actual and predicted generation for ALL plants over time."""
    from src.config.plants import get_plants
    from datetime import timedelta
    plants = get_plants()
    
    # Standard time parsing
    start_dt = datetime.fromisoformat(start.replace('Z', '+00:00')).replace(tzinfo=None) if start else datetime.now().replace(hour=0, minute=0, second=0)
    end_dt = datetime.fromisoformat(end.replace('Z', '+00:00')).replace(tzinfo=None) if end else start_dt + timedelta(days=2)

    # Fetch all records in range, but only actuals up to now
    now_dt = datetime.now()
    records = db.query(GenerationData).filter(
        GenerationData.timestamp >= start_dt,
        GenerationData.timestamp <= end_dt,
        GenerationData.timestamp <= now_dt
    ).all()

    if not records:
        return []

    df = pd.DataFrame([
        {
            "timestamp": r.timestamp,
            "plant_id": r.plant_id,
            "actual_kw": r.actual_kw or 0,
            "predicted_kw": r.predicted_kw or 0,
            "type": next((p['type'] for p in plants if p['id'] == r.plant_id), "solar")
        }
        for r in records
    ])

    try:
        # Group by timestamp and type
        agg = df.groupby(['timestamp', 'type']).agg({
            'actual_kw': 'sum',
            'predicted_kw': 'sum'
        }).reset_index()

        # Pivot to get solar and wind in columns
        pivoted = agg.pivot(index='timestamp', columns='type', values=['actual_kw', 'predicted_kw']).fillna(0)
        pivoted.columns = [f"{col[1]}_{col[0]}" for col in pivoted.columns]
        
        # Calculate average weather for diagnostics
        weather_map = {}
        import json
        for r in records:
            ts_str = r.timestamp.isoformat()
            if ts_str not in weather_map:
                weather_map[ts_str] = {"reasons": [], "weather": {}, "anomalies": []}
            
            # Identify individual plant anomalies (>10% deviation)
            if r.predicted_kw and r.predicted_kw > 10: # Only check if prediction is significant
                diff = abs((r.actual_kw or 0) - r.predicted_kw) / r.predicted_kw
                if diff > 0.10:
                    weather_map[ts_str]["anomalies"].append({
                        "plant_id": r.plant_id,
                        "deviation": round(diff * 100, 1),
                        "cause": r.reasons or "Unexplained variance"
                    })

            if r.reasons:
                weather_map[ts_str]["reasons"].append(r.reasons)
            if r.weather_data:
                try:
                    # Handle both dict and string cases
                    w_data = r.weather_data if isinstance(r.weather_data, dict) else json.loads(r.weather_data)
                    weather_map[ts_str]["weather"].update(w_data)
                except Exception:
                    pass

        pivoted = pivoted.reset_index()
        
        # Format for frontend
        result = []
        for _, row in pivoted.iterrows():
            ts_str = row['timestamp'].isoformat()
            meta = weather_map.get(ts_str, {"reasons": [], "weather": {}, "anomalies": []})
            
            # Heuristic: pick the most common reason or just join them
            combined_reason = ". ".join(list(set(meta["reasons"]))) if meta["reasons"] else "Normal operating conditions."
            
            result.append({
                "timestamp": ts_str,
                "solar_actual_kw": round(row.get('solar_actual_kw', 0), 2),
                "solar_predicted_kw": round(row.get('solar_predicted_kw', 0), 2),
                "wind_actual_kw": round(row.get('wind_actual_kw', 0), 2),
                "wind_predicted_kw": round(row.get('wind_predicted_kw', 0), 2),
                "reason": combined_reason,
                "weather": meta["weather"],
                "anomalies": meta["anomalies"]
            })
            
        return result
    except Exception as e:
        print(f"CRITICAL ERROR in aggregation: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
