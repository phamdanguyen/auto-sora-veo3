"""
Dedicated Worker for Video Verification and Download
Scans for jobs that have video generated but not yet downloaded/verified on disk.
Refactored to separate URL Resolution (Auth) from Downloading (No Auth).
"""
import asyncio
import logging
import os
import json
from datetime import datetime
from sqlalchemy.orm import Session
from app.core import account_manager
from .. import models, database
from app.core.drivers.sora import SoraDriver
from app.core.security import decrypt_password
from app.core.third_party_downloader import ThirdPartyDownloader
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

# Semaphores
_url_res_semaphore = asyncio.Semaphore(1) # Only 1 browser for checking status
_download_semaphore = asyncio.Semaphore(2) # 2 concurrent downloads

async def get_task_state(job):
    if not job.task_state:
        return {"resolution_retries": 0, "download_retries": 0}
    try:
        return json.loads(job.task_state)
    except:
        return {"resolution_retries": 0, "download_retries": 0}

async def update_task_state(db, job_id, updates):
    """
    Refetches job to ensure fresh state, applies updates, and saves.
    """
    # Refetch inside this transaction context
    j = db.query(models.Job).filter(models.Job.id == job_id).with_for_update().first()
    if not j:
        return
        
    current_state = json.loads(j.task_state) if j.task_state else {}
    
    # Deep merge or specific field update? 
    # For now, we only update root keys like "resolution_retries" or specific task status
    # Simple merge:
    current_state.update(updates)
    
    j.task_state = json.dumps(current_state)
    db.commit()

async def process_url_resolution(job_id: int):
    """
    Step 1: Get the Public URL.
    Requires Login.
    """
    db = database.SessionLocal()
    driver = None
    try:
        job = db.query(models.Job).filter(models.Job.id == job_id).first()
        if not job or job.video_url: 
            return # Already has URL or invalid

        state = await get_task_state(job)
        
        # GUARD: Check if Generation is actually complete
        gen_status = state.get("tasks", {}).get("generate", {}).get("status")
        if gen_status != "completed":
            # Process not ready yet, even if status is 'processing'
            # logger.debug(f"[WAIT]  [Resolve] Job #{job.id} waiting for generation (Status: {gen_status})") 
            return

        if state.get("resolution_retries", 0) >= 3:
            logger.error(f"[ERROR]  [Resolve] Job #{job.id} failed after 3 retries.")
            job.status = "failed"
            job.error_message = "Failed to resolve URL after 3 attempts"
            db.commit()
            return

        logger.info(f"🔍 [Resolve] Processing Job #{job.id} (Attempt {state.get('resolution_retries', 0) + 1}/3)...")
        
        if not job.account_id:
            logger.error(f"[ERROR]  [Resolve] Job #{job.id} has no linked Account ID. Cannot resolve.")
            job.status = "failed"
            job.error_message = "Missing Account Linkage (Generation failed before assignment?)"
            db.commit()
            return

        account = db.query(models.Account).filter(models.Account.id == job.account_id).first()
        if not account:
            logger.error(f"[ERROR]  [Resolve] Linked Account #{job.account_id} not found in DB.")
            return

        # Start Driver with Account Lock to prevent conflict with Generation Worker
        account_lock = await account_manager.get_account_lock(account.id)
        
        async with account_lock:
             try:
                profile_path = os.path.abspath(f"data/profiles/acc_{account.id}")
                driver = SoraDriver(headless=False, proxy=account.proxy, user_data_dir=profile_path)
                
                # Login
                await driver.login(
                    email=account.email, 
                    password=decrypt_password(account.password),
                    cookies=account.cookies
                )
                
                # Check Status & Post if needed
                status = await driver.check_video_status_v2()
                logger.info(f"[STATS]  [Resolve] Job #{job.id} Status: {status}")
                
                if status == "draft" or status == "completed":
                    # Combined Logic: Whether Draft or Completed, we try to download directly.
                    # If Draft: We need to click the DRAFT_ITEM
                    # If Completed: We need to click the GRID_ITEM (usually in Profile)
                    
                    logger.info(f"[DOWNLOAD]  [Resolve] Job #{job.id} is {status}. Proceeding to download...")
                    # Capture Video ID (Consistency)
                    if not job.video_id:
                         vid = await driver.extract_video_id()
                         if vid:
                             job.video_id = vid
                             db.commit()
                             logger.info(f"🆔 [Resolve] Job #{job.id} mapped to Video ID: {vid}")

                    # ⚡ TRY DIRECT DOWNLOAD FIRST (Authenticated)
                    # Bypasses "Share" button issues and "Public Link" 403s
                    try:
                        logger.info("[DOWNLOAD]  [Resolve] Attempting direct download (Authenticated)...")
                        
                        # Open Detail View (Click first grid item)
                        # We assume check_video_status left us on Profile/Drafts with items visible
                        # --- ITERATIVE SEARCH LOGIC ---
                        from .drivers.sora.selectors import SoraSelectors
                        
                        target_selector = SoraSelectors.DRAFT_ITEM if status == "draft" else SoraSelectors.GRID_ITEM

                        # Fix: Selector might be a list, join with comma
                        if isinstance(target_selector, list):
                            target_selector = ", ".join(target_selector)
                        
                        # Get all potential items
                        # Note: This might only get currently visible items (virtual scroll). 
                        # For now, we assume recent items are at top.
                        items = await driver.page.query_selector_all(target_selector)
                        logger.info(f"🔍 Found {len(items)} items to check in {status}...")
                        
                        found_match = False
                        
                        for i, item in enumerate(items):
                            try:
                                logger.info(f"👀 Checking item {i+1}/{len(items)}...")
                                
                                # Click to open detail view
                                await item.click()
                                await asyncio.sleep(3) # Wait for overlay
                                
                                # --- VERIFY PROMPT ---
                                is_match = False
                                try:
                                    prompt_el = await driver.page.query_selector("div.max-h-\[50vh\].min-h-10.w-full.overflow-y-auto")
                                    if not prompt_el:
                                        for sel in SoraSelectors.PROMPT_DISPLAY:
                                            prompt_el = await driver.page.query_selector(sel)
                                            if prompt_el: break
                                    
                                    if prompt_el:
                                        ui_prompt = await prompt_el.inner_text()
                                        if ui_prompt:
                                            # Normalize
                                            p_job = job.prompt.lower().strip()
                                            p_ui = ui_prompt.strip().lower()
                                            
                                            # Check match
                                            if p_job in p_ui or p_ui in p_job:
                                                 logger.info("[OK]  Prompt verified matches.")
                                                 is_match = True
                                            else:
                                                 logger.warning(f"[WARNING]  Mismatch! Job: '{p_job[:30]}...' vs UI: '{p_ui[:30]}...'")
                                        else:
                                            logger.warning("[WARNING]  Prompt element empty.")
                                    else:
                                         logger.warning("[WARNING]  Could not find prompt element.")
                                except Exception as e:
                                    logger.warning(f"[WARNING]  Error verifying prompt: {e}")

                                if is_match:
                                    found_match = True
                                    # Proceed to download
                                    local_path, size = await driver.download_page.download_video_direct()
                        
                                    filename = os.path.basename(local_path)
                                    web_path = f"/downloads/{filename}"
                                    
                                    job.local_path = web_path
                                    job.status = "done"
                                    job.updated_at = datetime.utcnow()
                                    
                                    # Optimization: Try to get public link too
                                    try:
                                         job.video_url = await driver.get_video_public_link()
                                    except:
                                         pass
                                    
                                    # Update task_state to mark download as completed
                                    state["tasks"]["download"] = {
                                        "status": "completed",
                                        "completed_at": datetime.utcnow().isoformat(),
                                        "output": {"local_path": web_path, "file_size": size}
                                    }
                                    state["current_task"] = "completed"
                                    job.task_state = json.dumps(state)
                                    
                                    db.commit()
                                    logger.info(f"[OK]  [Resolve] Iterative Search Success! Job #{job.id}: {web_path}")
                                    return # Done! (Break out of function)
                                else:
                                    # PROMPT MISMATCH -> Close and Continue
                                    logger.info("[ERROR]  Not a match. Closing detail view...")
                                    
                                    # Find Close Button
                                    close_btn = None
                                    for sel in SoraSelectors.DETAIL_CLOSE_BTN:
                                        close_btn = await driver.page.query_selector(sel)
                                        if close_btn: break
                                    
                                    if close_btn:
                                        await close_btn.click()
                                        await asyncio.sleep(1) # Wait for grid to restore
                                    else:
                                        logger.warning("[WARNING]  Could not find Close button! Cannot continue search.")
                                        break # Fail safe
                            
                            except Exception as item_err:
                                logger.error(f"[WARNING]  Error checking item {i}: {item_err}")
                                # Try to recover (close modal if open)
                                try:
                                    await driver.page.keyboard.press("Escape")
                                    await asyncio.sleep(1)
                                except:
                                    pass
                                continue

                        if not found_match:
                             logger.error(f"[STOP]  Verification Failed: No video found matching prompt after checking {len(items)} items.")
                             job.status = "failed"
                             job.error_message = "Video not found matching prompt."
                             db.commit()
                             return

                    except Exception as direct_err:
                        # CRITICAL FIX: If Prompt Mismatch, do NOT fallback. Fail hard.
                        if "Prompt mismatch" in str(direct_err):
                             logger.error(f"[STOP]  Verification Failed: {direct_err}")
                             
                             # Fail the job immediately to prevent infinite retries
                             job.status = "failed"
                             job.error_message = str(direct_err)
                             db.commit()
                             logger.info(f"[ERROR]  Job #{job.id} marked as FAILED due to prompt mismatch.")
                             return # Stop processing this job

                        logger.warning(f"[WARNING]  [Resolve] Direct download failed: {direct_err}")
                        logger.error("[STOP]  ALL Download methods failed (3rd party fallback disabled).")
                        
                        # Fail the job if Direct Download fails (since iter check covers all items)
                        job.status = "failed"
                        job.error_message = f"Download failed: {direct_err}"
                        db.commit()
                        return

                    # --- FALLBACK DISABLED (User Request) ---
                    # try:
                    #     public_link = await driver.get_video_public_link()
                    #     ...
                    # except Exception as e:
                    #     ...

                elif status == "unknown" or status == "generating":
                     # Try to capture Video ID for consistency
                     if not job.video_id:
                         vid = await driver.extract_video_id()
                         if vid:
                             job.video_id = vid
                             db.commit()
                             logger.info(f"🆔 [Resolve] Job #{job.id} mapped to Video ID: {vid}")

                     # If generating, we don't count as retry (just wait)
                     if status == "unknown":
                         logger.warning(f"[WARNING]  [Resolve] Job #{job.id} video not found.")
                         await update_task_state(db, job.id, {"resolution_retries": state.get("resolution_retries", 0) + 1})
             finally:
                 if driver:
                     await driver.stop()
                     driver = None # Prevent outer finally from stopping it again

    
    except Exception as e:
        logger.error(f"[ERROR]  [Resolve] Error Job #{job_id}: {e}")
        try:
            await update_task_state(db, job_id, {"resolution_retries": state.get("resolution_retries", 0) + 1})
        except:
             pass
    finally:
        if driver:
            await driver.stop()
        db.close()

async def process_file_download(job_id: int):
    """
    Step 2: Download File.
    Uses authenticated browser + iterative search (preferred).
    """
    db = database.SessionLocal()
    driver = None
    try:
        job = db.query(models.Job).filter(models.Job.id == job_id).first()
        if not job:
            return

        state = await get_task_state(job)
        
        # GUARD: Check if Generation is actually complete
        gen_status = state.get("tasks", {}).get("generate", {}).get("status")
        if gen_status != "completed":
            # Video not ready yet - still generating
            logger.info(f"[WAIT]  [Download] Job #{job.id} waiting for generation to complete (gen_status={gen_status})")
            return
        
        if state.get("download_retries", 0) >= 3:
            logger.error(f"[ERROR]  [Download] Job #{job.id} failed after 3 retries.")
            job.status = "failed"
            job.error_message = "Failed to download file after 3 attempts"
            db.commit()
            return

        logger.info(f"[DOWNLOAD]  [Download] Processing Job #{job.id} (Attempt {state.get('download_retries', 0) + 1}/3)")
        
        if not job.account_id:
            logger.error(f"[ERROR]  [Download] Job #{job.id} has no linked Account. Cannot download.")
            job.status = "failed"
            job.error_message = "Missing Account Linkage"
            db.commit()
            return

        account = db.query(models.Account).filter(models.Account.id == job.account_id).first()
        if not account:
            logger.error(f"[ERROR]  [Download] Linked Account #{job.account_id} not found.")
            return

        # Start Driver with Account Lock
        account_lock = await account_manager.get_account_lock(account.id)
        
        async with account_lock:
            try:
                profile_path = os.path.abspath(f"data/profiles/acc_{account.id}")
                driver = SoraDriver(headless=False, proxy=account.proxy, user_data_dir=profile_path)
                
                # Login
                await driver.login(
                    email=account.email, 
                    password=decrypt_password(account.password),
                    cookies=account.cookies
                )
                
                # Check Status
                status = await driver.check_video_status_v2()
                logger.info(f"[STATS]  [Download] Job #{job.id} Status: {status}")
                
                if status == "draft" or status == "completed":
                    # --- ITERATIVE SEARCH LOGIC ---
                    from .drivers.sora.selectors import SoraSelectors
                    
                    target_selector = SoraSelectors.DRAFT_ITEM if status == "draft" else SoraSelectors.GRID_ITEM
                    if isinstance(target_selector, list):
                        target_selector = ", ".join(target_selector)
                    
                    items = await driver.page.query_selector_all(target_selector)
                    logger.info(f"🔍 Found {len(items)} items to check...")
                    
                    found_match = False
                    
                    for i, item in enumerate(items):
                        try:
                            logger.info(f"👀 Checking item {i+1}/{len(items)}...")
                            await item.click()
                            await asyncio.sleep(3)
                            
                            # Verify Prompt
                            is_match = False
                            try:
                                prompt_el = await driver.page.query_selector("div.max-h-\\[50vh\\].min-h-10.w-full.overflow-y-auto")
                                if not prompt_el:
                                    for sel in SoraSelectors.PROMPT_DISPLAY:
                                        prompt_el = await driver.page.query_selector(sel)
                                        if prompt_el: break
                                
                                if prompt_el:
                                    ui_prompt = await prompt_el.inner_text()
                                    if ui_prompt:
                                        p_job = job.prompt.lower().strip()
                                        p_ui = ui_prompt.strip().lower()
                                        if p_job in p_ui or p_ui in p_job:
                                            logger.info("[OK]  Prompt verified matches.")
                                            is_match = True
                                        else:
                                            logger.warning(f"[WARNING]  Mismatch! Job: '{p_job[:30]}...' vs UI: '{p_ui[:30]}...'")
                            except Exception as e:
                                logger.warning(f"[WARNING]  Error verifying prompt: {e}")
                            
                            if is_match:
                                found_match = True
                                local_path, size = await driver.download_page.download_video_direct()
                                
                                filename = os.path.basename(local_path)
                                web_path = f"/downloads/{filename}"
                                
                                job.local_path = web_path
                                job.status = "done"
                                job.updated_at = datetime.utcnow()
                                
                                # Update task_state to mark download as completed
                                state["tasks"]["download"] = {
                                    "status": "completed",
                                    "completed_at": datetime.utcnow().isoformat(),
                                    "output": {"local_path": web_path, "file_size": size}
                                }
                                state["current_task"] = "completed"
                                job.task_state = json.dumps(state)
                                
                                db.commit()
                                
                                logger.info(f"[OK]  [Download] Complete Job #{job.id}: {web_path}")
                                return
                            else:
                                # Close detail view
                                close_btn = None
                                for sel in SoraSelectors.DETAIL_CLOSE_BTN:
                                    close_btn = await driver.page.query_selector(sel)
                                    if close_btn: break
                                
                                if close_btn:
                                    await close_btn.click()
                                    await asyncio.sleep(1)
                                else:
                                    logger.warning("[WARNING]  Could not find Close button!")
                                    break
                        except Exception as item_err:
                            logger.error(f"[WARNING]  Error checking item {i}: {item_err}")
                            try:
                                await driver.page.keyboard.press("Escape")
                                await asyncio.sleep(1)
                            except:
                                pass
                            continue
                    
                    if not found_match:
                        logger.error(f"[STOP]  No video found matching prompt after checking {len(items)} items.")
                        state["download_retries"] = state.get("download_retries", 0) + 1
                        await update_task_state(db, job.id, state)
                else:
                    logger.warning(f"[WARNING]  [Download] Video not ready yet (Status: {status})")
                    
            except Exception as e:
                logger.error(f"[ERROR]  [Download] Failed: {e}")
                state["download_retries"] = state.get("download_retries", 0) + 1
                await update_task_state(db, job.id, state)
            finally:
                if driver and driver.browser:
                    await driver.browser.close()
                    
    except Exception as e:
        logger.error(f"[ERROR]  [Download] Wrapper Error Job #{job_id}: {e}")
    finally:
        db.close()

async def scan_and_process():
    logger.info("[POLL]  Split-Worker Scanner Started")
    while True:
        try:
            db = database.SessionLocal()
            
            # 1. Find Jobs needing URL (Processing + No URL)
            url_candidates = db.query(models.Job).filter(
                models.Job.status.in_(["processing"]),
                models.Job.video_url.is_(None)
            ).all()
            
            # 2. Find Jobs needing Download (Has URL + No Local Path)
            dl_candidates = db.query(models.Job).filter(
                models.Job.video_url.isnot(None),
                (models.Job.local_path.is_(None)) | (models.Job.local_path == "")
            ).all()
            
            db.close() # Close early
            
            # Dispatch
            tasks = []
            
            # Queue URL Resolutions
            for job in url_candidates:
                 # Heuristic: Check task state if generated?
                 # For now, just trust 'processing' means generated or generating
                 # We limit concurrency via semaphore
                 tasks.append(_safe_run(_url_res_semaphore, process_url_resolution, job.id))

            # Queue Downloads
            for job in dl_candidates:
                 tasks.append(_safe_run(_download_semaphore, process_file_download, job.id))
            
            if tasks:
                logger.info(f"[START]  Dispatching {len(tasks)} tasks...")
                await asyncio.gather(*tasks)
            
            await asyncio.sleep(10)
            
        except Exception as e:
            logger.error(f"Scanner Loop Error: {e}")
            await asyncio.sleep(5)

async def _safe_run(semaphore, func, *args):
    async with semaphore:
        await func(*args)

async def start_worker():
    # DEPRECATED: Download now happens in worker_v2 sequential flow
    # Keeping this function for backward compatibility / manual retry
    logger.info("[WARNING]  worker_download.start_worker() called but disabled. Download now in worker_v2.")
    # await scan_and_process()
    pass

if __name__ == "__main__":
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(start_worker())
