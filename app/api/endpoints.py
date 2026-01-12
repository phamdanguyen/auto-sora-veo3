from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from .. import models, schemas, database
from ..core import account_manager
import logging

logger = logging.getLogger(__name__)

# GLOBAL BROWSER LOCK: Ensures only ONE browser is running at a time
# This prevents "Opening in existing browser session" errors on Windows
import asyncio
_GLOBAL_BROWSER_LOCK = asyncio.Lock()

router = APIRouter()

# Dependency
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

from ..core.security import encrypt_password

# ... (Previous imports)

# --- Accounts ---
@router.post("/accounts/", response_model=schemas.Account)
def create_account(account: schemas.AccountCreate, db: Session = Depends(get_db)):
    db_account = models.Account(
        platform=account.platform,
        email=account.email,
        password=encrypt_password(account.password),
        proxy=account.proxy,
        status="live"
    )
    db.add(db_account)
    db.commit()
    db.refresh(db_account)
    return db_account

@router.get("/accounts/", response_model=List[schemas.Account])
def read_accounts(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    accounts = db.query(models.Account).order_by(models.Account.id.asc()).offset(skip).limit(limit).all()
    return accounts

@router.post("/accounts/global_manual_login")
async def global_manual_login(db: Session = Depends(get_db)):
    """
    Open browser (No specific account), wait for user to login, 
    detect Email from token/intercept data, and Create/Update Account in DB.
    """
    from ..core.drivers.sora import SoraDriver
    from datetime import datetime
    import asyncio
    import time
    import os
    import jwt # PyJWT
    
    logger.info("[LOCK]  Starting GLOBAL MANUAL login...")
    
    # Use a generic temporary profile to capture the login
    # We don't know the account ID yet, so use a 'temp_login' prefix
    profile_path = f"data/profiles/temp_login_{int(time.time())}"
    driver = None
    
    logger.info("🔒 Acquiring global browser lock for global manual login...")
    async with _GLOBAL_BROWSER_LOCK:
        logger.info("🔓 Global browser lock acquired")
        try:
            os.makedirs(profile_path, exist_ok=True)
            
            driver = SoraDriver(
                headless=False,
                user_data_dir=os.path.abspath(profile_path),
                channel=None
            )
            
            await driver.start()

            # Navigate directly to Login URL
            login_url = "https://chatgpt.com/auth/login?next=%2Fsora%2F"
            logger.info(f"🌏 Navigating to {login_url}")
            await driver.page.goto(login_url, wait_until="domcontentloaded")
            
            # Wait for valid token (User interaction loop)
            # Give longer time for manual typing (e.g. 5 mins)
            max_wait_seconds = 300
            poll_interval = 2
            max_attempts = max_wait_seconds // poll_interval
            token_captured = False
            detected_email = None
            
            logger.info(f"👤 Waiting for USER to login (max {max_wait_seconds}s)...")
            
            for i in range(max_attempts):
                elapsed = (i + 1) * poll_interval
                
                if driver.latest_access_token:
                    # Try to decode email from token
                    try:
                        token_str = driver.latest_access_token
                        if token_str.lower().startswith("bearer "):
                            token_str = token_str[7:]
                        
                        decoded = jwt.decode(token_str, options={"verify_signature": False})
                        # Look for email claim: usually 'https://api.openai.com/profile' -> 'email' OR just 'email'
                        # OpenAI structure often has it in profile claim or top level
                        if "email" in decoded:
                            detected_email = decoded["email"]
                        elif "https://api.openai.com/profile" in decoded:
                            detected_email = decoded["https://api.openai.com/profile"].get("email")
                        
                        if detected_email:
                            token_captured = True
                            logger.info(f"✨ Token captured for email: {detected_email}")
                            break
                    except Exception as jwt_err:
                        logger.warning(f"Failed to decode JWT: {jwt_err}")
                        # Fallback: Detect email via API if JWT fails
                        try:
                            logger.info("🕵️ JWT Decode failed, trying API profile fetch...")
                            # Just try to fetch user info from known endpoint
                            # We use cookies implicitly by likely not sending Auth header if token is missing
                            user_profile = await driver.page.evaluate("""async () => {
                                try {
                                    let headers = {};
                                    if (window.__accessToken) {
                                        headers['Authorization'] = 'Bearer ' + window.__accessToken;
                                    }
                                    const res = await fetch('https://chatgpt.com/backend-api/me', {
                                        headers: headers
                                    }); 
                                    if(res.status === 401) return null;
                                    const data = await res.json();
                                    return data.email || data.user?.email || null;
                                } catch (e) { return null; }
                            }""")
                            
                            if user_profile:
                                 detected_email = user_profile
                                 token_captured = True
                                 logger.info(f"✨ Email detected via API: {detected_email}")
                                 break
                        except Exception as api_err:
                             logger.warning(f"API fallback failed: {api_err}")
                        pass
                
                await asyncio.sleep(poll_interval)

            if not token_captured or not detected_email:
                 raise Exception("Login timeout or failed to detect email from token.")

            # --- UPSERT ACCOUNT ---
            logger.info(f"💾 Saving account for {detected_email}...")
            
            account = db.query(models.Account).filter(models.Account.email == detected_email).first()
            if not account:
                logger.info(f"🆕 Creating NEW account for {detected_email}")
                account = models.Account(
                    platform="sora",
                    email=detected_email,
                    password="", # Password unknown/not needed for cookie auth
                    status="live",
                    login_mode="manual" # Default to manual for captured accounts
                )
                db.add(account)
                db.commit()
                db.refresh(account)
            else:
                logger.info(f"♻️ Updating EXISTING account #{account.id}")
                # Force update to manual mode if user logs in manually
                account.login_mode = "manual"

            # Save Info
            driver.cookies = await driver.context.cookies()
            device_id = await driver.page.evaluate("() => localStorage.getItem('oai-did') || null")
            
            account.access_token = driver.latest_access_token
            account.device_id = device_id
            account.token_status = "valid"
            account.token_captured_at = datetime.utcnow()
            if driver.latest_user_agent:
                account.user_agent = driver.latest_user_agent
            account.cookies = driver.cookies
            
            db.commit()
            
            # Verify Credits
            try:
                credits = await driver.get_credits_api()
                if credits and credits.get('credits') is not None:
                    account.credits_remaining = int(credits.get('credits'))
                    account.credits_last_checked = datetime.utcnow()
                    db.commit()
            except:
                pass
                
            return {"ok": True, "message": f"Login successful for {detected_email}", "email": detected_email}

        except Exception as e:
            logger.error(f"[ERROR]  Global Manual Login failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            if driver:
                await driver.stop()
            # Clean up temp profile? Maybe keep it for debugging or future cache

@router.delete("/accounts/{account_id}")
def delete_account(account_id: int, db: Session = Depends(get_db)):
    account = db.query(models.Account).filter(models.Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    
    db.delete(account)
    db.commit()
    return {"ok": True}


@router.post("/accounts/{account_id}/login")
async def login_account(account_id: int, db: Session = Depends(get_db)):
    """
    Open browser (visible), perform login, capture token and save to DB.
    This enables 100% headless operation for job execution.
    """
    from ..core.drivers.sora import SoraDriver
    from ..core.security import decrypt_password
    from datetime import datetime
    import asyncio
    
    from ..core import account_manager
    
    account = db.query(models.Account).filter(models.Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    
    logger.info(f"[LOCK]  Starting login for account #{account_id} ({account.email})...")
    
    # Acquire Lock to prevent race with workers
    lock = await account_manager.get_account_lock(account_id)
    
    # Mark as busy so workers don't try to grab it while we are logging in
    await account_manager.mark_account_busy(account_id)
    
    # FRESH START: Always use a timestamped profile to avoid lock conflicts
    import time
    profile_path = f"data/profiles/acc_{account.id}_{int(time.time())}"
    driver = None
    
    # Acquire GLOBAL BROWSER LOCK first to ensure only one browser at a time
    logger.info("🔒 Acquiring global browser lock for login...")
    async with _GLOBAL_BROWSER_LOCK:
        logger.info("🔓 Global browser lock acquired for login")
        try:
            async with lock:
                import os
                
                os.makedirs(profile_path, exist_ok=True)
                logger.info(f"📁 Using fresh profile: {profile_path}")
                
                driver = SoraDriver(
                    headless=False,  # Visible for user to solve captcha
                    user_data_dir=os.path.abspath(profile_path),
                    channel=None  # Use Playwright bundled Chromium
                )
                
                await driver.start()

                # Perform login
                await driver.login(
                    email=account.email,
                    password=decrypt_password(account.password)
                )
            
            # Navigate to Sora
            if "sora.chatgpt.com" not in driver.page.url:
                 await driver.page.goto("https://sora.chatgpt.com/", wait_until="networkidle")
            
            # Wait for token capture (allow extended time for 2FA/verification)
            # User has 5 MINUTES to complete 2FA manually
            # Poll every 3 seconds = 100 attempts = 300 seconds = 5 minutes
            max_wait_seconds = 300
            poll_interval = 3
            max_attempts = max_wait_seconds // poll_interval
            token_captured = False
            
            logger.info(f"[LOCK]  Waiting for login/2FA completion (max {max_wait_seconds}s)...")
            logger.info("📢 If 2FA required, please complete it in the browser window.")
            
            for i in range(max_attempts):
                elapsed = (i + 1) * poll_interval
                remaining = max_wait_seconds - elapsed
                
                if driver.latest_access_token:
                    token_captured = True
                    logger.info(f"✨ Token captured after {elapsed}s!")
                    break
                
                # Log progress every 15 seconds
                if i % 5 == 0:
                    logger.info(f"[WAIT]  Waiting for token... ({elapsed}s elapsed, {remaining}s remaining)")
                
                await asyncio.sleep(poll_interval)
                
                # Reload page every 30 seconds to help trigger token capture
                if elapsed > 0 and elapsed % 30 == 0:
                    try:
                        # Check if we're still on a login/verification page
                        current_url = driver.page.url
                        if "sora.chatgpt.com" in current_url and "/library" not in current_url:
                            logger.info("[MONITOR]  Refreshing to help capture token...")
                            await driver.page.reload(wait_until="networkidle")
                    except:
                        pass

            if not token_captured:
                raise Exception(f"Login timeout after {max_wait_seconds}s. 2FA may not have been completed.")

            # --- SAVE TOKEN & COOKIES FIRST (before verification) ---
            logger.info("💾 Saving captured token and cookies to database...")
            
            # Get cookies from browser context
            driver.cookies = await driver.context.cookies()
            
            # Capture device_id
            device_id = await driver.page.evaluate("""() => {
                return localStorage.getItem('oai-did') || null;
            }""")
            
            # SAVE TO DB IMMEDIATELY
            account.access_token = driver.latest_access_token
            account.device_id = device_id
            account.token_status = "valid"
            account.token_captured_at = datetime.utcnow()
            
            if driver.latest_user_agent:
                account.user_agent = driver.latest_user_agent
            
            account.cookies = driver.cookies
            
            db.commit()
            logger.info(f"[OK]  Token & cookies saved for {account.email}")
            
            # --- OPTIONAL VERIFICATION (after save) ---
            logger.info("🕵️ Verifying token with API call (optional)...")
            credits_info = None
            try:
                credits_info = await driver.get_credits_api()
                if credits_info and credits_info.get('credits') is not None:
                    account.credits_remaining = int(credits_info.get('credits'))
                    
                    if credits_info.get('reset_seconds'):
                        from datetime import timedelta
                        reset_date = datetime.utcnow() + timedelta(seconds=int(credits_info.get('reset_seconds')))
                        account.credits_reset_at = reset_date
                    
                    account.credits_last_checked = datetime.utcnow()
                    db.commit()
                    logger.info(f"[OK]  Credits updated: {account.credits_remaining}")
            except Exception as api_err:
                logger.warning(f"[WARNING]  API verification failed (token still saved): {api_err}")
            
            logger.info(f"🎉 Login complete! Token saved for {account.email}")
            
            return {
                "ok": True,
                "message": "Login successful, token saved.",
                "token_status": "valid",
                "credits": account.credits_remaining,
                "device_id": device_id[:20] + "..." if device_id else None
            }
            
        except Exception as e:
            logger.error(f"[ERROR]  Login failed for {account.email}: {e}")
            account.token_status = "pending"
            db.commit()
            raise HTTPException(status_code=500, detail=f"Login Error: {str(e)}")
        finally:
            if driver:
                await driver.stop()
            # Mark free
            await account_manager.mark_account_free(account_id)
            logger.info("🔓 Global browser lock released after login")







@router.post("/accounts/refresh_all")
async def refresh_all_accounts(db: Session = Depends(get_db)):
    """
    Refresh all accounts:
    - Validate tokens via API
    - Update credits and reset time
    - Update token status (valid/expired)
    """
    from ..core.drivers.sora import SoraDriver
    from datetime import datetime
    import asyncio
    
    accounts = db.query(models.Account).filter(models.Account.platform == "sora").all()
    results = {"total": len(accounts), "valid": 0, "expired": 0, "errors": 0}
    
    logger.info(f"[MONITOR]  Refreshing all {len(accounts)} accounts...")
    
    for acc in accounts:
        # SKIP MANUAL ACCOUNTS if token is missing/invalid - User must login manually
        if acc.login_mode == 'manual':
            # Check if token is valid via API only?
            # Or just skip the re-login logic.
            # We'll allow "Check Credits" but NOT "Auto Re-login"
            pass

        if not acc.access_token:

            acc.token_status = "pending"
            results["expired"] += 1  # Count as needing login
            continue
            
        try:
            # API-only check
            driver = await SoraDriver.api_only(
                access_token=acc.access_token,
                device_id=acc.device_id,
                user_agent=acc.user_agent
            )
            
            # Check credits - wrap in try/except to handle API errors gracefully
            try:
                credits_info = await driver.get_credits_api()
            except Exception as api_err:
                logger.warning(f"[WARNING]  API check failed for {acc.email}: {api_err}")
                credits_info = None  # Trigger re-login branch
            
            if credits_info:
                acc.token_status = "valid"
                results["valid"] += 1
                
                # Update info
                if credits_info.get('credits') is not None:
                     acc.credits_remaining = int(credits_info.get('credits'))
                
                if credits_info.get('reset_seconds'):
                     from datetime import timedelta
                     reset_date = datetime.utcnow() + timedelta(seconds=int(credits_info.get('reset_seconds')))
                     acc.credits_reset_at = reset_date
                     
                acc.credits_last_checked = datetime.utcnow()
                
                # Try to decode JWT for expiry (if available and standard JWT)
                # This is "best effort"
                try:
                    import jwt
                    # standard JWT decode without verification
                    decoded = jwt.decode(acc.access_token, options={"verify_signature": False})
                    if "exp" in decoded:
                        acc.token_expires_at = datetime.fromtimestamp(decoded["exp"])
                except Exception:
                    # Token might not be standard JWT or library missing
                    pass
                
            else:
                # Token invalid/expired
                
                # IF MANUAL MODE: Do not attempt auto-login
                if acc.login_mode == 'manual':
                     logger.warning(f"[WARNING]  Account {acc.email} (Manual Mode) expired. Skipping auto-login.")
                     acc.token_status = "expired"
                     results["expired"] += 1
                     continue

                # Attempt re-login with 2FA support (AUTO MODE ONLY)
                logger.info(f"[MONITOR]  Account #{acc.id} ({acc.email}) token expired. Attempting re-login...")
                
                # Use global browser lock for sequential login
                from ..core.security import decrypt_password
                import time
                import os
                
                async with _GLOBAL_BROWSER_LOCK:
                    logger.info(f"🔓 Browser lock acquired for {acc.email}")
                    login_driver = None
                    
                    try:
                        await account_manager.mark_account_busy(acc.id)
                        
                        # Fresh profile
                        profile_path = f"data/profiles/acc_{acc.id}_{int(time.time())}"
                        os.makedirs(profile_path, exist_ok=True)
                        
                        login_driver = SoraDriver(
                            headless=False,
                            user_data_dir=os.path.abspath(profile_path),
                            channel=None
                        )
                        
                        await login_driver.start()
                        
                        # Perform login
                        await login_driver.login(
                            email=acc.email,
                            password=decrypt_password(acc.password)
                        )
                        
                        # Navigate to Sora if needed
                        if "sora.chatgpt.com" not in login_driver.page.url:
                            await login_driver.page.goto("https://sora.chatgpt.com/", wait_until="networkidle")
                        
                        # Wait for token (5 min for 2FA)
                        max_wait = 300
                        poll_interval = 3
                        token_captured = False
                        
                        logger.info(f"[WAIT]  Waiting for token capture (max {max_wait}s, user may need to complete 2FA)...")
                        
                        for i in range(max_wait // poll_interval):
                            if login_driver.latest_access_token:
                                token_captured = True
                                logger.info(f"✨ Token captured for {acc.email}!")
                                break
                            if i % 5 == 0:
                                logger.info(f"[WAIT]  Waiting... ({(i+1)*poll_interval}s elapsed)")
                            await asyncio.sleep(poll_interval)
                        
                        if token_captured:
                            # Save token immediately
                            acc.access_token = login_driver.latest_access_token
                            acc.cookies = await login_driver.context.cookies()
                            acc.device_id = await login_driver.page.evaluate("() => localStorage.getItem('oai-did') || null")
                            acc.token_status = "valid"
                            acc.token_captured_at = datetime.utcnow()
                            if login_driver.latest_user_agent:
                                acc.user_agent = login_driver.latest_user_agent
                            db.commit()
                            
                            logger.info(f"[OK]  Token saved for {acc.email}")
                            results["valid"] += 1
                        else:
                            logger.warning(f"⏱️ Login timeout for {acc.email}")
                            acc.token_status = "expired"
                            results["expired"] += 1
                            
                    except Exception as login_err:
                        logger.error(f"[ERROR]  Re-login failed for {acc.email}: {login_err}")
                        acc.token_status = "expired"
                        results["errors"] += 1
                    finally:
                        if login_driver:
                            try:
                                await login_driver.stop()
                            except:
                                pass
                        await account_manager.mark_account_free(acc.id)
                        logger.info(f"🔓 Browser lock released for {acc.email}")

        except Exception as e:
            logger.error(f"Failed to refresh account #{acc.id}: {e}")
            results["errors"] += 1
            
    db.commit()
    logger.info(f"[OK]  Refresh complete: {results}")
    return results


@router.post("/accounts/check_credits")
async def check_all_credits(db: Session = Depends(get_db)):
    """
    Check credits for all accounts using EXISTING tokens only.
    Does NOT trigger login/browser.
    """
    from ..core.drivers.sora import SoraDriver
    from datetime import datetime
    
    accounts = db.query(models.Account).filter(models.Account.platform == "sora").all()
    results = {
        "total": len(accounts), 
        "updated": 0, 
        "failed": 0, 
        "expired": 0,  # Token/cookies hết hạn
        "no_token": 0,  # Chưa login
        "details": []  # Chi tiết từng account
    }
    
    logger.info(f"[CREDITS]  Checking credits for {len(accounts)} accounts (API-only)...")
    
    for acc in accounts:
        detail = {"id": acc.id, "email": acc.email, "status": "unknown"}
        
        if not acc.access_token:
            detail["status"] = "no_token"
            detail["message"] = "Chưa login - cần nhấn nút Login"
            results["no_token"] += 1
            results["details"].append(detail)
            continue
            
        try:
            # API-only check
            driver = await SoraDriver.api_only(
                access_token=acc.access_token,
                device_id=acc.device_id,
                user_agent=acc.user_agent,
                cookies=acc.cookies
            )
            
            # Check credits
            credits_info = await driver.get_credits_api()
            
            # Handle new error response format
            if credits_info and credits_info.get('error_code'):
                error_code = credits_info.get('error_code')
                
                if error_code == "TOKEN_EXPIRED":
                    acc.token_status = "expired"
                    detail["status"] = "expired"
                    detail["message"] = "Token/cookies đã hết hạn - cần Login lại"
                    results["expired"] += 1
                    logger.warning(f"[WARNING]  Account {acc.email}: Token/cookies expired")
                    
                elif error_code == "NO_TOKEN":
                    detail["status"] = "no_token" 
                    detail["message"] = "Không có access token"
                    results["no_token"] += 1
                    
                elif error_code == "RATE_LIMITED":
                    detail["status"] = "rate_limited"
                    detail["message"] = "Bị rate limit - thử lại sau"
                    results["failed"] += 1
                    
                else:
                    detail["status"] = "error"
                    detail["message"] = credits_info.get('error', 'Unknown error')
                    results["failed"] += 1
                    
            elif credits_info and credits_info.get('credits') is not None:
                # Success!
                acc.token_status = "valid"
                results["updated"] += 1
                
                acc.credits_remaining = int(credits_info.get('credits'))
                
                if credits_info.get('reset_seconds'):
                    from datetime import timedelta
                    reset_date = datetime.utcnow() + timedelta(seconds=int(credits_info.get('reset_seconds')))
                    acc.credits_reset_at = reset_date
                     
                acc.credits_last_checked = datetime.utcnow()
                
                detail["status"] = "success"
                detail["credits"] = acc.credits_remaining
                detail["message"] = f"Credits: {acc.credits_remaining}"
                logger.info(f"[OK]  Credits checked for {acc.email}: {acc.credits_remaining}")
                
            else:
                # Unexpected response
                acc.token_status = "expired"
                detail["status"] = "error"
                detail["message"] = "Không nhận được dữ liệu credits"
                results["failed"] += 1
                
        except Exception as e:
            logger.error(f"[ERROR]  Failed to check credits for #{acc.id} ({acc.email}): {e}")
            detail["status"] = "error"
            detail["message"] = str(e)
            results["failed"] += 1
            
        results["details"].append(detail)
            
    db.commit()
    
    # Log summary
    logger.info(f"[STATS]  Credit Check Summary: Updated={results['updated']}, Expired={results['expired']}, NoToken={results['no_token']}, Failed={results['failed']}")
    
    return results



# --- Jobs ---
@router.post("/jobs/", response_model=schemas.Job)
def create_job(job: schemas.JobCreate, db: Session = Depends(get_db)):
    db_job = models.Job(
        prompt=job.prompt,
        image_path=job.image_path,
        duration=job.duration,
        aspect_ratio=job.aspect_ratio,
        # login_mode removed
        status="draft" # Default to draft so user must verify/start manually
    )
    db.add(db_job)
    db.commit()
    db.refresh(db_job)
    return db_job

@router.get("/jobs/", response_model=List[schemas.Job])
def read_jobs(skip: int = 0, limit: int = 100, category: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(models.Job)
    
    terminal_statuses = ['completed', 'done', 'failed', 'cancelled']
    
    if category == 'active':
        query = query.filter(models.Job.status.notin_(terminal_statuses))
    elif category == 'history':
        query = query.filter(models.Job.status.in_(terminal_statuses))
        
    jobs = query.order_by(models.Job.id.desc()).offset(skip).limit(limit).all()
    
    # Hydrate with real-time tracker info
    from ..core.progress_tracker import tracker
    
    results = []
    for job in jobs:
        # Check tracker
        track_info = tracker.get_job(job.id)
        
        if track_info:
            setattr(job, "progress", int(track_info.get("progress_pct", 0)))
            setattr(job, "progress_message", track_info.get("message", ""))
        else:
            # Fallback for old jobs
            if job.status == "processing":
                 setattr(job, "progress_message", "Initializing...")
            else:
                 setattr(job, "progress_message", "")
        
        results.append(job)
        
    return results

@router.get("/jobs/{job_id}", response_model=schemas.Job)
def read_job(job_id: int, db: Session = Depends(get_db)):
    # logger.info(f"Read Job. TM ID: {id(task_manager)}") # Overkill
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@router.put("/jobs/{job_id}", response_model=schemas.Job)
def update_job(job_id: int, job_update: schemas.JobUpdate, db: Session = Depends(get_db)):
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job_update.prompt is not None:
        job.prompt = job_update.prompt
    if job_update.duration is not None:
        job.duration = job_update.duration
    if job_update.aspect_ratio is not None:
        job.aspect_ratio = job_update.aspect_ratio
    if job_update.image_path is not None:
        job.image_path = job_update.image_path
        
    db.commit()
    db.refresh(job)
    return job

@router.delete("/jobs/{job_id}")
def delete_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if job:
        db.delete(job)
        db.commit()
    return {"ok": True}


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if job:
        # 1. Cancel running asyncio task if active
        from ..core import worker_v2
        if hasattr(worker_v2, "_active_generate_tasks"):
            active_tasks = worker_v2._active_generate_tasks
            if job_id in active_tasks:
                task = active_tasks[job_id]
                task.cancel()
                logger.warning(f"[STOP]  Force Cancelled active asyncio task for Job #{job_id}")

        # 2. Update DB status
        # Only allow cancelling if not already completed/failed (optional)
        if job.status in ["pending", "processing", "sent_prompt", "generating", "download"]:
            job.status = "cancelled"
            job.error_message = "Cancelled by user (Force Stop)"
            db.commit()
            
            # 3. Update active job set
            task_manager.remove_active_job(job_id)
            
    return {"ok": True}


# --- Bulk Actions ---
class BulkActionRequest(BaseModel):
    action: str # retry_failed, delete_all, clear_completed
    job_ids: Optional[List[int]] = None # Optional list of specific IDs

from fastapi import WebSocket, WebSocketDisconnect
from ..core.logger import log_manager

@router.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    await websocket.accept()
    log_manager.connected_clients.append(websocket)
    
    try:
        # Send Hello Message
        await websocket.send_json({"message": "✅ SYSTEM LOGS CONNECTED", "level": "INFO"})
        
        # Send buffer first
        buffer_list = list(log_manager.buffer)
        for entry in buffer_list:
            await websocket.send_json(entry)
            
        # Keep alive loop
        while True:
            await websocket.receive_text() # Just wait for disconnect
    except WebSocketDisconnect:
        if websocket in log_manager.connected_clients:
            log_manager.connected_clients.remove(websocket)
    except Exception as e:
        logger.error(f"WebSocket Error: {e}")
        if websocket in log_manager.connected_clients:
            log_manager.connected_clients.remove(websocket)

# --- Other Endpoints ---
@router.post("/jobs/upload")
async def upload_file(file: UploadFile = File(...)):
    import shutil
    import os
    import time
    
    upload_dir = "data/uploads"
    os.makedirs(upload_dir, exist_ok=True)
    
    # Create unique filename
    timestamp = int(time.time())
    safe_filename = file.filename.replace(" ", "_").replace("/", "").replace("\\", "")
    filename = f"{timestamp}_{safe_filename}"
    file_path = os.path.join(upload_dir, filename)
    
    # Save file
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # Return absolute path for worker to use
    abs_path = os.path.abspath(file_path)
    logger.info(f"💾 File uploaded: {abs_path}")
    
    return {"path": abs_path, "filename": safe_filename}

# --- Imports ---
# --- Imports ---
from app.core.task_manager import task_manager

# ... (Previous code)

@router.post("/jobs/{job_id}/retry")
async def retry_job(job_id: int, db: Session = Depends(get_db)):
    logger.info(f"[MONITOR]  Retry Job Request. TaskManager ID: {id(task_manager)}")
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if job:
        # Reset job
        job.status = "pending"
        job.error_message = None
        job.retry_count = 0
        db.commit()
        
        # Trigger Task
        await task_manager.start_job(job)
        db.commit() # Save task_state updated by start_job
        
    return {"ok": True}

@router.post("/jobs/{job_id}/tasks/{task_name}/run")
async def run_job_task(job_id: int, task_name: str, db: Session = Depends(get_db)):
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not job:
         raise HTTPException(status_code=404, detail="Job not found")

    import json
    state = json.loads(job.task_state or "{}")
    tasks = state.get("tasks", {})
    
    if task_name not in tasks:
         raise HTTPException(status_code=400, detail=f"Task '{task_name}' not found in job state")

    # Reset Task Status
    tasks[task_name]["status"] = "pending"
    # Clear error if exists
    if "last_error" in tasks[task_name]:
         del tasks[task_name]["last_error"]
    if "retry_count" in tasks[task_name]:
         tasks[task_name]["retry_count"] = 0
         
    state["tasks"] = tasks
    state["current_task"] = task_name  # Update current task
    
    # Reset retries counter if running download
    if task_name == "download":
        state["download_retries"] = 0
    
    job.task_state = json.dumps(state)
    
    # If job was failed/completed, reset to processing
    if job.status in ["failed", "completed", "done", "draft"]:
         job.status = "processing"
         job.error_message = None

    db.commit()
    
    # Directly enqueue the specific task (instead of calling start_job which resets state)
    from ..core.task_manager import task_manager, TaskContext
    
    # Check if active
    if job.id in task_manager._active_job_ids:
         # Log but allow if user really knows what they are doing? 
         # No, prevent duplicates.
         raise HTTPException(status_code=400, detail="Job is already active/running")

    task_manager._active_job_ids.add(job.id)

    if task_name == "generate":
        task = TaskContext(
            job_id=job.id,
            task_type="generate",
            input_data={"prompt": job.prompt, "duration": job.duration, "account_id": job.account_id}
        )
        await task_manager.generate_queue.put(task)
    elif task_name == "download":
        task = TaskContext(
            job_id=job.id,
            task_type="download",
            input_data={"video_url": job.video_url}
        )
        await task_manager.download_queue.put(task)
    elif task_name == "poll":
        task = TaskContext(
            job_id=job.id,
            task_type="poll",
            input_data={"account_id": job.account_id, "poll_count": 0}
        )
        await task_manager.poll_queue.put(task)
    
    return {"ok": True, "task_state": state}

# ...

@router.post("/jobs/bulk_action")
async def bulk_job_action(req: BulkActionRequest, db: Session = Depends(get_db)):
    from ..core import worker_v2
    
    tm_local_id = id(task_manager)
    tm_worker_id = id(worker_v2.task_manager)
    
    logger.info(f"🔍 [DEBUG] Local TM ID: {tm_local_id}")
    logger.info(f"🔍 [DEBUG] Worker TM ID: {tm_worker_id}")
    logger.info(f"🔍 [DEBUG] Worker Running: {worker_v2._worker_running}")
    logger.info(f"🔍 [DEBUG] Stop Event Set: {worker_v2.STOP_EVENT.is_set()}")
    logger.info(f"🔍 [DEBUG] Generate Queue Size: {task_manager.generate_queue.qsize()}")
    
    if tm_local_id != tm_worker_id:
        logger.error("[ERROR]  CRITICAL: TaskManager Instance Mismatch! Worker uses different instance.")

    elif req.action == "start_selected" and req.job_ids:
        # Check credits first
        if not account_manager.has_usable_account(db, platform="sora"):
             logger.error("[ERROR]  Bulk Start Failed: No usable account (credits Check)")
             raise HTTPException(status_code=400, detail="Tổng credits còn lại không đủ! Vui lòng nạp thêm.")

        jobs = db.query(models.Job).filter(models.Job.id.in_(req.job_ids)).with_for_update().all()
        for job in jobs:
            if job.status in ["draft", "pending"]:
                 await task_manager.start_job(job)
        db.commit()

    elif req.action == "start_all":
        # Check credits first
        if not account_manager.has_usable_account(db, platform="sora"):
             logger.error("[ERROR]  Bulk Start All Failed: No usable account (credits Check)")
             raise HTTPException(status_code=400, detail="Tổng credits còn lại không đủ! Vui lòng nạp thêm.")

        # Start all draft/pending jobs
        jobs = db.query(models.Job).filter(models.Job.status.in_(["draft", "pending"])).all()
        logger.info(f"[START]  Bulk Start All: Found {len(jobs)} jobs to start")
        
        for job in jobs:
            try:
                await task_manager.start_job(job)
            except Exception as e:
                logger.error(f"[ERROR]  Failed to start job #{job.id} during bulk start: {e}")
        
        db.commit()

    elif req.action == "retry_selected" and req.job_ids:
        jobs = db.query(models.Job).filter(models.Job.id.in_(req.job_ids)).all()
        for job in jobs:
            # IMMEDIATE CREDIT/AVAILABILITY CHECK
            if not account_manager.has_usable_account(db, platform="sora", specific_account_id=job.account_id):
                if job.account_id:
                    logger.error(f"[ERROR]  Retry Selected Failed: No usable account for Job #{job.id} (Account #{job.account_id})")
                    raise HTTPException(status_code=400, detail="Tài khoản được chỉ định đã hết quota.")
                else:
                    logger.error("[ERROR]  Retry Selected Failed: No usable account globally")
                    raise HTTPException(status_code=400, detail="Tổng credits còn lại không đủ! Hệ thống đang tạm dừng.")
            # Retry (Clean slate)
            job.status = "pending"
            job.error_message = None
            job.retry_count = 0
            
            # Use FORCE removal to ensure start_job accepts it
            task_manager.remove_active_job(job.id)
            
            await task_manager.start_job(job)
        db.commit()

    elif req.action == "retry_download_selected" and req.job_ids:
        # Retry only subtasks (Poll/Download) for Submitted/Completed jobs
        jobs = db.query(models.Job).filter(models.Job.id.in_(req.job_ids)).all()
        for job in jobs:
            await task_manager.retry_subtasks(job)
        db.commit()

        
    elif req.action == "retry_failed":
        # Check credits first
        if not account_manager.has_usable_account(db, platform="sora"):
             logger.error("[ERROR]  Retry Failed Failed: No usable account")
             raise HTTPException(status_code=400, detail="No available accounts with credits found!")

        jobs = db.query(models.Job).filter(models.Job.status.in_(["failed", "cancelled"])).all()
        for job in jobs:
             job.status = "pending"
             job.error_message = None
             job.retry_count = 0
             
             # Use FORCE removal to ensure start_job accepts it
             task_manager.remove_active_job(job.id)
             
             await task_manager.start_job(job)
        db.commit()

    elif req.action == "delete_all":
        db.query(models.Job).delete(synchronize_session=False)
        db.commit()
    elif req.action == "clear_completed":
         db.query(models.Job).filter(models.Job.status.in_(["completed", "done"])).delete(synchronize_session=False)
         db.commit()
    elif req.action == "delete_selected" and req.job_ids:
        db.query(models.Job).filter(models.Job.id.in_(req.job_ids)).delete(synchronize_session=False)
        db.commit()
    
    return {"ok": True}


@router.post("/system/reset")
async def system_reset(db: Session = Depends(get_db)):
    """
    Emergency Reset:
    1. Clear busy accounts
    2. Clear active job IDs
    3. Reset 'processing' jobs to 'pending'
    """
    logger.warning("[WARNING]  SYSTEM RESET TRIGGERED BY USER")
    
    # 1. Clear busy accounts
    account_manager.force_reset()
    
    # 2. Clear active job tracking
    task_manager.force_clear_active()
    
    # 3. Reset stuck jobs
    stuck_jobs = db.query(models.Job).filter(
        models.Job.status.in_(["processing", "sent_prompt", "generating", "download"])
    ).all()
    
    count = 0
    for job in stuck_jobs:
        job.status = "cancelled"
        job.error_message = "System Reset (Manual Start Required)"
        count += 1
    
    db.commit()
    logger.info(f"[OK]  System Reset complete. Cancelled {count} stuck jobs.")
    return {"ok": True, "reset_count": count}

@router.post("/system/pause")
async def pause_system():
    task_manager.pause()
    return {"ok": True, "paused": True}

@router.post("/system/resume")
async def resume_system():
    task_manager.resume()
    return {"ok": True, "paused": False}

@router.get("/system/queue_status")
async def get_queue_status(db: Session = Depends(get_db)):
    status = task_manager.get_status()
    
    # Add DB stats for Dashboard
    completed_count = db.query(models.Job).filter(models.Job.status.in_(['completed', 'done'])).count()
    pending_count = db.query(models.Job).filter(models.Job.status.in_(['pending', 'draft'])).count()
    failed_count = db.query(models.Job).filter(models.Job.status == 'failed').count()
    # Active = Processing, Generating, etc. (Anything not done/failed/draft/pending/cancelled)
    # Actually Dashboard uses a specific filter. Let's just return key counts.
    
    status["db_stats"] = {
        "completed": completed_count,
        "pending": pending_count,
        "failed": failed_count
    }
    return status

# --- System/OS Actions ---
import subprocess
import os
import sys

@router.post("/jobs/{job_id}/open_folder")
def open_job_folder(job_id: int, db: Session = Depends(get_db)):
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not job or not job.local_path:
        raise HTTPException(status_code=404, detail="Job/File not found")

    # local_path is relative web path e.g. /downloads/file.mp4
    # convert to absolute path
    # We assume local_path follows /downloads/ naming convention
    filename = os.path.basename(job.local_path)
    # Security: Ensure filename doesn't have path traversal
    if ".." in filename or "/" in filename or "\\" in filename: 
         # The basename check above handles slashes, but double check
         pass
         
    abs_path = os.path.abspath(os.path.join("data/downloads", filename))
    
    if not os.path.exists(abs_path):
         raise HTTPException(status_code=404, detail="File not found on disk")
         
    # Open FOLDER
    if os.name == 'nt':
        subprocess.run(['explorer', '/select,', abs_path])
    elif os.name == 'posix':
        subprocess.run(['xdg-open', os.path.dirname(abs_path)])
    
    return {"ok": True}

@router.post("/jobs/{job_id}/open_video")
def open_job_video(job_id: int, db: Session = Depends(get_db)):
    """Opens the video file in the system default media player."""
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not job or not job.local_path:
        raise HTTPException(status_code=404, detail="Job/File not found")

    filename = os.path.basename(job.local_path)
    abs_path = os.path.abspath(os.path.join("data/downloads", filename))
    
    if not os.path.exists(abs_path):
         raise HTTPException(status_code=404, detail="File not found on disk")
         
    try:
        os.startfile(abs_path) # Windows only
    except AttributeError:
        # Mac/Linux
        if os.name == 'posix':
             subprocess.run(['xdg-open', abs_path])
        else:
             subprocess.run(['open', abs_path])
    
    return {"ok": True}

# --- System Settings ---
@router.post("/settings/start_workers")
async def start_workers():
    """Manual trigger to start background workers"""
    from ..core import worker_v2 as worker
    from ..core import worker_download
    import asyncio
    
    # Check if we can/should check running status?
    # For now, asyncio.create_task is safe enough (idempotency depends on worker logic)
    # But better to log
    
    # We should probably have a singleton check, but for MVP just start them.
    # Users will click this if they see "Auto-start disabled"
    
    asyncio.create_task(worker.start_worker())
    asyncio.create_task(worker_download.start_worker())
    
    return {"ok": True, "message": "Workers started in background"}
