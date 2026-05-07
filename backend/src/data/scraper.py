"""
scraper.py — KPTCL SLDC Karnataka Solar/Wind Generation Scraper
Fetches live data from kptclsldc.in and stores to CSV + SQLite.
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import sqlite3
import logging
import re
from datetime import datetime
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
# Resolve BASE_DIR to the root of the "renewable forecast" project
BASE_DIR   = Path(__file__).parent.parent.parent
DATA_DIR   = BASE_DIR / "data"
LOGS_DIR   = BASE_DIR / "logs"
DB_PATH    = DATA_DIR / "karnataka_solar.db"
CSV_NCEP   = DATA_DIR / "ncep_solar_wind.csv"
CSV_GEN    = DATA_DIR / "state_generation.csv"

DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# ── Logging ────────────────────────────────────────────────────────────────────
log = logging.getLogger("sldc_scraper")
if not log.handlers:
    log.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s")
    fh = logging.FileHandler(LOGS_DIR / "scraper.log")
    fh.setFormatter(formatter)
    sh = logging.StreamHandler()
    sh.setFormatter(formatter)
    log.addHandler(fh)
    log.addHandler(sh)

# ── URLs ───────────────────────────────────────────────────────────────────────
URLS = {
    "default": "https://kptclsldc.in/Default.aspx",
    "ncep":   "https://kptclsldc.in/StateNCEP.aspx",
    "stategen": "https://kptclsldc.in/StateGen.aspx",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":           "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language":  "en-US,en;q=0.9",
    "Accept-Encoding":  "gzip, deflate",
    "Referer":          "https://kptclsldc.in/",
    "Connection":       "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# Persistent session — shares cookies across requests (required by SLDC)
_session = requests.Session()
_session.trust_env = False
_session.headers.update(HEADERS)

# ── Database setup ─────────────────────────────────────────────────────────────
def init_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS default_readings (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            scraped_at          TEXT NOT NULL,
            sldc_ts             TEXT,
            frequency           REAL DEFAULT 0,
            state_ui_mw         REAL DEFAULT 0,
            state_demand_mw     REAL DEFAULT 0,
            thermal_mw          REAL DEFAULT 0,
            thermal_ipp_mw      REAL DEFAULT 0,
            hydro_mw            REAL DEFAULT 0,
            wind_mw             REAL DEFAULT 0,
            solar_mw            REAL DEFAULT 0,
            other_mw            REAL DEFAULT 0,
            total_generation_mw REAL DEFAULT 0,
            pavagada_solar_mw   REAL DEFAULT 0,
            central_gen_mw      REAL DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ncep_readings (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            scraped_at  TEXT NOT NULL,
            sldc_ts     TEXT,
            frequency   REAL,
            escom       TEXT NOT NULL,
            biomass_mw  REAL DEFAULT 0,
            cogen_mw    REAL DEFAULT 0,
            minihydro_mw REAL DEFAULT 0,
            wind_mw     REAL DEFAULT 0,
            solar_mw    REAL DEFAULT 0,
            grid_drawal_mw REAL DEFAULT 0,
            total_mw    REAL DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS stategen_readings (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            scraped_at      TEXT NOT NULL,
            sldc_ts         TEXT,
            frequency       REAL,
            total_gen_mw    REAL,
            ncep_mw         REAL,
            cgs_mw          REAL,
            state_thermal_mw REAL,
            major_hydro_mw  REAL,
            ipp_thermal_mw  REAL,
            other_hydro_mw  REAL,
            plant           TEXT,
            capacity_mw     REAL,
            generation_mw   REAL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS scrape_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            scraped_at  TEXT NOT NULL,
            url         TEXT,
            status      TEXT,
            rows_saved  INTEGER,
            error       TEXT
        )
    """)

    _ensure_column(cur, "ncep_readings", "grid_drawal_mw", "REAL DEFAULT 0")

    con.commit()
    con.close()
    log.info("Database initialised at %s", DB_PATH)


def _ensure_column(cur: sqlite3.Cursor, table: str, column: str, ddl: str) -> None:
    existing = {row[1] for row in cur.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


# ── Fetch helpers ──────────────────────────────────────────────────────────────
_homepage_seeded = False

def seed_session():
    """Hit the SLDC homepage once to obtain session cookies."""
    global _homepage_seeded
    if _homepage_seeded:
        return
    try:
        _session.get(URLS["default"], timeout=5)
        _homepage_seeded = True
        log.debug("Session seeded from homepage")
    except Exception:
        _homepage_seeded = True
        pass


def fetch_page(url: str, timeout: int = 20) -> BeautifulSoup | None:
    seed_session()
    try:
        resp = _session.get(url, timeout=timeout)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")
    except requests.RequestException as e:
        log.error("Failed to fetch %s: %s", url, e)
        return None


def safe_float(text: str) -> float:
    """Convert scraped text to float, handling expressions like '260+1200'."""
    if not text:
        return 0.0
    
    text = str(text).strip()
    
    # Handle '260+1200' style strings by summing them
    if "+" in text:
        try:
            parts = [re.sub(r"[^\d.]", "", p) for p in text.split("+")]
            return sum(float(p) for p in parts if p)
        except Exception:
            pass

    try:
        # Standard cleaning: remove non-numeric except decimal
        cleaned = re.sub(r"[^\d.]", "", text)
        return float(cleaned) if cleaned else 0.0
    except (ValueError, TypeError):
        return 0.0


def extract_sldc_timestamp(soup: BeautifulSoup) -> str:
    """Pull the SLDC-reported timestamp from page Label3."""
    lbl = soup.find(id="Label3")
    if lbl:
        return lbl.get_text(strip=True)
    
    # Fallback to regex if Label3 not found
    text = soup.get_text(" ", strip=True)
    m = re.search(r"\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}(?::\d{2})?", text)
    return m.group(0) if m else ""


def extract_frequency(soup: BeautifulSoup) -> float:
    """Pull grid frequency from Label2."""
    lbl = soup.find(id="Label2")
    if lbl:
        return safe_float(lbl.get_text(strip=True))
    
    # Fallback to regex
    text = soup.get_text(" ", strip=True)
    m = re.search(r"FREQUENCY\s*:?\s*([\d.]+)", text, re.IGNORECASE)
    return float(m.group(1)) if m else 0.0


# ── Default homepage scraper ──────────────────────────────────────────────────
def label_float(soup: BeautifulSoup, label_id: str) -> float:
    lbl = soup.find(id=label_id)
    return safe_float(lbl.get_text(strip=True)) if lbl else 0.0


def label_text(soup: BeautifulSoup, label_id: str) -> str:
    lbl = soup.find(id=label_id)
    return lbl.get_text(strip=True) if lbl else ""


def scrape_default() -> list[dict]:
    """Scrape Default.aspx — live statewide generation mix refreshed every minute."""
    soup = fetch_page(URLS["default"])
    if not soup:
        return []

    rec = {
        "scraped_at":          datetime.now().isoformat(timespec="seconds"),
        "sldc_ts":             label_text(soup, "Label6") or extract_sldc_timestamp(soup),
        "frequency":           label_float(soup, "Label1") or extract_frequency(soup),
        "state_ui_mw":         label_float(soup, "Label12"),
        "state_demand_mw":     label_float(soup, "Label5"),
        "thermal_mw":          label_float(soup, "lbl_thermal"),
        "thermal_ipp_mw":      label_float(soup, "lbl_thrmipp"),
        "hydro_mw":            label_float(soup, "lbl_hydro"),
        "wind_mw":             label_float(soup, "lbl_wind"),
        "solar_mw":            label_float(soup, "lbl_solar"),
        "other_mw":            label_float(soup, "lbl_other"),
        "total_generation_mw": label_float(soup, "Label3"),
        "pavagada_solar_mw":   label_float(soup, "lblpvgslr"),
        "central_gen_mw":      label_float(soup, "Label7"),
    }

    log.info(
        "Default scrape: demand=%s MW | solar=%s MW | wind=%s MW | SLDC ts=%s",
        rec["state_demand_mw"], rec["solar_mw"], rec["wind_mw"], rec["sldc_ts"],
    )
    return [rec]


# ── NCEP scraper ───────────────────────────────────────────────────────────────
ESCOM_NAMES = {"BESCOM", "MESCOM", "CESC", "GESCOM", "HESCOM", "PAVAGADA SOLAR PARK"}

def scrape_ncep() -> list[dict]:
    """Scrape StateNCEP.aspx — solar/wind by ESCOM zone."""
    soup = fetch_page(URLS["ncep"])
    if not soup:
        return []

    scraped_at = datetime.now().isoformat(timespec="seconds")
    sldc_ts    = extract_sldc_timestamp(soup)
    frequency  = extract_frequency(soup)

    records = []
    tables  = soup.find_all("table")

    for tbl in tables:
        rows = tbl.find_all("tr")
        for row in rows:
            cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
            if not cells:
                continue

            escom = cells[0].upper().strip()
            if not any(escom.startswith(e) for e in ESCOM_NAMES) and "TOTAL" not in escom:
                continue

            if len(cells) >= 6:
                rec = {
                    "scraped_at":    scraped_at,
                    "sldc_ts":       sldc_ts,
                    "frequency":     frequency,
                    "escom":         cells[0].strip(),
                    "biomass_mw":    safe_float(cells[1]) if len(cells) > 1 else 0,
                    "cogen_mw":      safe_float(cells[2]) if len(cells) > 2 else 0,
                    "minihydro_mw":  safe_float(cells[3]) if len(cells) > 3 else 0,
                    "wind_mw":       safe_float(cells[4]) if len(cells) > 4 else 0,
                    "solar_mw":      safe_float(cells[5]) if len(cells) > 5 else 0,
                    "grid_drawal_mw": safe_float(cells[6]) if len(cells) > 6 else 0,
                }
                
                rec["total_mw"] = (
                    rec["biomass_mw"] + 
                    rec["cogen_mw"] + 
                    rec["minihydro_mw"] + 
                    rec["wind_mw"] + 
                    rec["solar_mw"]
                )
                records.append(rec)
                log.debug("NCEP row: %s → solar=%s MW", rec["escom"], rec["solar_mw"])

    log.info("NCEP scrape: %d rows | SLDC ts=%s | freq=%.2f Hz",
             len(records), sldc_ts, frequency)
    return records


# ── StateGen scraper ───────────────────────────────────────────────────────────
PLANT_NAMES = {
    "RTPS","BTPS","YTPS","SHARAVATHI","NAGJHARI","VARAHI",
    "KODSALLI","KADRA","GERUSOPPA","JOG","LPH","SUPA","SHIMSHA",
    "SHIVASAMUDRA","MANIDAM","MUNRABAD","BHADRA","GHATAPRABHA",
    "ALMATTI","JINDAL","UPCL","YCCP",
}

def scrape_stategen() -> list[dict]:
    """Scrape StateGen.aspx — full Karnataka generation by plant."""
    soup = fetch_page(URLS["stategen"])
    if not soup:
        return []

    scraped_at = datetime.now().isoformat(timespec="seconds")
    sldc_ts    = extract_sldc_timestamp(soup)
    frequency  = extract_frequency(soup)

    text = soup.get_text(" ", strip=True)
    total_gen = 0.0
    lbl_gen = soup.find(id="Label1")
    if lbl_gen:
        total_gen = safe_float(lbl_gen.get_text(strip=True))
    else:
        m = re.search(r"TOTAL GENERATION\s*:?\s*([\d,]+)\s*MW", text, re.IGNORECASE)
        if m:
            total_gen = safe_float(m.group(1).replace(",", ""))

    ncep_mw = 0.0
    lbl_ncep = soup.find(id="Label4")
    if lbl_ncep:
        ncep_mw = safe_float(lbl_ncep.get_text(strip=True))
    else:
        m2 = re.search(r"NCEP\s*:?\s*([\d,]+)", text, re.IGNORECASE)
        if m2:
            ncep_mw = safe_float(m2.group(1).replace(",", ""))

    cgs_mw = 0.0
    lbl_cgs = soup.find(id="Label5")
    if lbl_cgs:
        cgs_mw = safe_float(lbl_cgs.get_text(strip=True))
    else:
        m3 = re.search(r"CGS\s*:?\s*([\d,]+)", text, re.IGNORECASE)
        if m3:
            cgs_mw = safe_float(m3.group(1).replace(",", ""))

    state_thermal = major_hydro = ipp_thermal = other_hydro = 0.0
    tables = soup.find_all("table")
    for tbl in tables:
        rows = tbl.find_all("tr")
        for i, row in enumerate(rows):
            hdrs = [th.get_text(strip=True).upper() for th in row.find_all(["th","td"])]
            if "STATE THERMAL" in hdrs and "MAJOR HYDRO" in hdrs:
                if i + 1 < len(rows):
                    vals = [td.get_text(strip=True) for td in rows[i+1].find_all("td")]
                    if len(vals) >= 4:
                        state_thermal = safe_float(vals[0])
                        major_hydro   = safe_float(vals[1])
                        ipp_thermal   = safe_float(vals[2])
                        other_hydro   = safe_float(vals[3])

    records = []
    for tbl in tables:
        rows = tbl.find_all("tr")
        for row in rows:
            cells = [td.get_text(strip=True) for td in row.find_all(["td","th"])]
            if not cells:
                continue
            plant = cells[0].upper().strip()
            if plant not in PLANT_NAMES:
                continue
            rec = {
                "scraped_at":        scraped_at,
                "sldc_ts":           sldc_ts,
                "frequency":         frequency,
                "total_gen_mw":      total_gen,
                "ncep_mw":           ncep_mw,
                "cgs_mw":            cgs_mw,
                "state_thermal_mw":  state_thermal,
                "major_hydro_mw":    major_hydro,
                "ipp_thermal_mw":    ipp_thermal,
                "other_hydro_mw":    other_hydro,
                "plant":             cells[0].strip(),
                "capacity_mw":       safe_float(cells[1]) if len(cells) > 1 else 0,
                "generation_mw":     safe_float(cells[2]) if len(cells) > 2 else 0,
            }
            records.append(rec)

    log.info("StateGen scrape: %d plant rows | total=%s MW | SLDC ts=%s",
             len(records), total_gen, sldc_ts)
    return records


# ── Persist to DB + CSV ────────────────────────────────────────────────────────
def save_ncep(records: list[dict]):
    if not records:
        return 0
    con = sqlite3.connect(DB_PATH)
    df  = pd.DataFrame(records)
    df.to_sql("ncep_readings", con, if_exists="append", index=False)
    con.close()

    header = not CSV_NCEP.exists()
    df.to_csv(CSV_NCEP, mode="a", header=header, index=False)
    log.info("Saved %d NCEP rows to DB + CSV", len(records))
    return len(records)


def save_default(records: list[dict]):
    if not records:
        return 0
    con = sqlite3.connect(DB_PATH)
    df = pd.DataFrame(records)
    df.to_sql("default_readings", con, if_exists="append", index=False)
    con.close()
    log.info("Saved %d Default rows to DB", len(records))
    return len(records)


def save_stategen(records: list[dict]):
    if not records:
        return 0
    con = sqlite3.connect(DB_PATH)
    df  = pd.DataFrame(records)
    df.to_sql("stategen_readings", con, if_exists="append", index=False)
    con.close()

    header = not CSV_GEN.exists()
    df.to_csv(CSV_GEN, mode="a", header=header, index=False)
    log.info("Saved %d StateGen rows to DB + CSV", len(records))
    return len(records)


def log_scrape(url: str, status: str, rows: int, error: str = ""):
    con = sqlite3.connect(DB_PATH)
    con.execute(
        "INSERT INTO scrape_log (scraped_at, url, status, rows_saved, error) VALUES (?,?,?,?,?)",
        (datetime.now().isoformat(), url, status, rows, error),
    )
    con.commit()
    con.close()


# ── Main scrape job ────────────────────────────────────────────────────────────
def run_scrape():
    """Single scrape cycle. Default.aspx itself refreshes every 60 seconds."""
    init_db()
    log.info("── Scrape cycle starting ──────────────────────────────")

    # Homepage statewide live generation mix
    try:
        default_rows = scrape_default()
        n = save_default(default_rows)
        log_scrape(URLS["default"], "ok", n)
    except Exception as e:
        log.exception("Default scrape failed: %s", e)
        log_scrape(URLS["default"], "error", 0, str(e))

    # NCEP (solar/wind by ESCOM)
    try:
        ncep_rows = scrape_ncep()
        n = save_ncep(ncep_rows)
        log_scrape(URLS["ncep"], "ok", n)
    except Exception as e:
        log.exception("NCEP scrape failed: %s", e)
        log_scrape(URLS["ncep"], "error", 0, str(e))

    # StateGen (all plants)
    try:
        gen_rows = scrape_stategen()
        n = save_stategen(gen_rows)
        log_scrape(URLS["stategen"], "ok", n)
    except Exception as e:
        log.exception("StateGen scrape failed: %s", e)
        log_scrape(URLS["stategen"], "error", 0, str(e))

    log.info("── Scrape cycle complete ──────────────────────────────")
