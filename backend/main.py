import os
import threading
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from src.data.database import init_db
from src.api.routes import router as api_router
from src.jobs.scheduler import start_scheduler
# Import SLDC app and its background scraper
from src.api.main import app as sldc_app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing database...")
    init_db()
    
    logger.info("Starting background scheduler...")
    global scheduler
    scheduler = start_scheduler()

    # Manually trigger the SLDC scraper thread since 'mount' doesn't run it
    from src.data.scraper import run_scrape
    import pytz
    from datetime import datetime
    def _run_sldc_job():
        kolkata = pytz.timezone('Asia/Kolkata')
        while True:
            try:
                logger.info(f"Background SLDC sync starting (Time: {datetime.now(kolkata)})...")
                run_scrape()
                logger.info("Background SLDC sync complete.")
            except Exception as e:
                logger.error(f"Background SLDC sync failed: {e}")
            import time
            time.sleep(600) # 10 mins
    
    threading.Thread(target=_run_sldc_job, daemon=True).start()
    
    yield
    
    # Shutdown
    if scheduler:
        scheduler.shutdown()
        logger.info("Scheduler shutdown complete.")

app = FastAPI(title="ECO POWER Unified API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# FIXED: Removed the redundant 'prefix="/api"' because it is already defined in routes.py
app.include_router(api_router)

# Mount the SLDC app for /sldc/... routes
app.mount("/", sldc_app)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
