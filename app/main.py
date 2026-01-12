from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
import logging
import sys
import asyncio

# Windows subprocess support for Playwright
# This must be set BEFORE any asyncio event loop is created
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP ---
    from .database import engine, Base, migrate_if_needed
    
    # Auto-migrate DB schema
    migrate_if_needed()
    
    # Create tables
    Base.metadata.create_all(bind=engine)
    
    # --- RESET JOBS ON STARTUP ---
    from sqlalchemy.orm import Session
    from . import models
    
    logger.info("🧹 Resetting non-completed jobs to 'draft' status...")
    db = Session(bind=engine)
    try:
        # Update all jobs that are not completed or done to 'draft'
        # This covers: pending, processing, sent_prompt, generating, download, failed, cancelled
        db.query(models.Job).filter(
            models.Job.status.notin_(['completed', 'done'])
        ).update({models.Job.status: 'draft'}, synchronize_session=False)
        db.commit()
        logger.info("✅ Job reset complete.")
    except Exception as e:
        logger.error(f"❌ Failed to reset jobs on startup: {e}")
        db.rollback()
    finally:
        db.close()
    
    # Start Background Workers
    auto_start = os.getenv("AUTO_START_WORKERS", "True").lower() == "true"
    
    if auto_start:
        logger.info("✅ Auto-starting workers based on configuration...")
        # 1. Generate Worker (handles Sora submission)
        asyncio.create_task(worker.start_worker())
        
        # 2. Download/Verify Worker (Scanning mode)
        asyncio.create_task(worker_download.start_worker())
    else:
        logger.info("⏸️ Auto-start disabled. Workers not started. Use API/Dashboard to start.")
        
    yield
    
    # --- SHUTDOWN ---
    logger.warning("🛑 Application shutdown triggered. Stopping workers...")
    await worker.stop_worker()
    
    # Also clear any locks if feasible
    from .core import account_manager
    account_manager.force_reset()
    logger.info("✅ Shutdown complete.")

app = FastAPI(title="Uni-Video Automation", lifespan=lifespan)

# Helper to get path to resource
def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    
    return os.path.join(base_path, relative_path)

# Mount static files (Frontend Assets)
static_dir = resource_path("app/web/static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Mount downloads (User Data)
# User data should be outside the exe (in the current working directory)
ABS_DOWNLOAD_DIR = os.path.abspath("data/downloads")
os.makedirs(ABS_DOWNLOAD_DIR, exist_ok=True)
app.mount("/downloads", StaticFiles(directory=ABS_DOWNLOAD_DIR), name="downloads")

# CORS (allow all for local dev)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.responses import FileResponse
import asyncio
from .core import worker_v2 as worker  # Use Refactored Worker (v2)
from .core import worker_download  # New Download Verification Worker

# Include API Router
from .api import endpoints
app.include_router(endpoints.router, prefix="/api")

@app.get("/")
async def read_dashboard():
    return FileResponse(resource_path("app/web/templates/index.html"))

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
