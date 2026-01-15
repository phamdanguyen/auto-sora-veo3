from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
import logging
import sys
import asyncio

# ... (imports) ...

# This must be set BEFORE any asyncio event loop is created
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("server_debug.log", mode='a', encoding='utf-8')
    ]
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
    
    logger.info("[STARTUP] Resetting non-completed jobs to 'draft' status...")
    db = Session(bind=engine)
    try:
        # Update all jobs that are not completed or done to 'draft'
        # This covers: pending, processing, sent_prompt, generating, download
        # Query first to log what we are resetting (Debugging Persistence)
        jobs_to_reset = db.query(models.Job).filter(
            models.Job.status.notin_(['completed', 'done', 'failed', 'cancelled', 'download'])
        ).all()
        
        if jobs_to_reset:
            logger.warning(f"[STARTUP] Found {len(jobs_to_reset)} interrupted jobs. Resetting to 'draft'...")
            for j in jobs_to_reset:
                logger.warning(f"  -> Resetting Job #{j.id} (Status: {j.status}) to 'draft'")
                j.status = 'draft'
            
            db.commit()
            logger.info("[OK] Job reset complete.")
        else:
            logger.info("[STARTUP] No interrupted jobs found needing reset.")
    except Exception as e:
        logger.error(f"[ERROR] Failed to reset jobs on startup: {e}")
        db.rollback()
    finally:
        db.close()
    
    
    # Start Background Workers
    # ALWAYS START WORKERS as per user request
    logger.info("[OK] Auto-starting workers...")
    
    # --- NEW WORKER MANAGER INITIALIZATION ---
    from .database import SessionLocal
    from .core.repositories.job_repo import JobRepository
    from .core.repositories.account_repo import AccountRepository
    from .core.drivers.factory import register_default_drivers, driver_factory
    
    # 0. Register Drivers
    register_default_drivers()
    
    # 1. Initialize DB Session for Workers
    # Note: Using Sync Session in Async Workers is blocking but safe if single-threaded.
    # TODO: Migrate to AsyncSession for performance.
    worker_session = SessionLocal()
    
    # 2. Initialize Repositories
    job_repo = JobRepository(worker_session)
    account_repo = AccountRepository(worker_session)
    
    # 3. Initialize Manager
    worker_manager = init_worker_manager(job_repo, account_repo, driver_factory)
    
    # 4. Start All
    await worker_manager.start_all()
        
    yield
    
    # --- SHUTDOWN ---
    logger.warning("[SHUTDOWN] Application shutdown triggered. Stopping workers...")
    if worker_manager:
        await worker_manager.stop_all()
        
    # Close worker session
    worker_session.close()
    
    # Also clear any locks if feasible
    from .core import account_manager
    account_manager.force_reset()
    logger.info("[OK] Shutdown complete.")

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

# Mount Uploads
ABS_UPLOAD_DIR = os.path.abspath("data/uploads")
os.makedirs(ABS_UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=ABS_UPLOAD_DIR), name="uploads")

# Templates Configuration
templates = Jinja2Templates(directory=resource_path("app/web/templates"))

from fastapi.responses import FileResponse
import asyncio
# from .core import worker_v2 as worker  # REMOVED: Legacy Worker
# from .core import worker_download  # REMOVED: Legacy Download Worker
from .core.workers.manager import init_worker_manager, get_worker_manager

# ========== Include API Routers ==========
# Phase 4: New modular routers (SOLID principles)
from .api.routers import accounts, jobs, system

# Include new routers
app.include_router(accounts.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(system.router, prefix="/api")

# Legacy endpoints (maintained for backward compatibility)
# Note: New clients should use the modular routers above
# This can be removed once all clients migrate to new API structure
# from .api import endpoints # REMOVED: Moved to app.legacy
# Update import path if endpoints was moved to legacy
# Ideally we should use the new app.legacy.endpoints
# But endpoints.py in main was likely app.api.endpoints which was moved.
# Let's fix the import to point to new location or rely on modules being distinct.
# Since we moved app/api/endpoints.py to app/legacy/endpoints.py,
# and created app/legacy/__init__.py,
# we need to import from app.legacy.endpoints
# from .legacy import endpoints as legacy_endpoints
# app.include_router(legacy_endpoints.router, prefix="/api/legacy")

@app.get("/")
@app.get("/dashboard")
@app.get("/accounts")
@app.get("/jobs")
@app.get("/history")
@app.get("/about")
async def read_dashboard(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
