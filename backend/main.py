import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from src.data.database import init_db
from src.api.routes import router as api_router
from src.jobs.scheduler import start_scheduler
# Import the SLDC app to unify them
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

# Include prediction routes
app.include_router(api_router, prefix="/api")

# Mount or include SLDC routes
# Since src.api.main:app has its own routes, we can just include them
app.mount("/sldc_service", sldc_app) 
# OR more simply, we can just copy the critical SLDC routes or mount it at root
# Let's mount the SLDC app so /sldc/status becomes /sldc/status
app.mount("", sldc_app)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
