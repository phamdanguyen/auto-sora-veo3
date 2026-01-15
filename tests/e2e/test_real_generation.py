
import asyncio
import sys
import os
import json
import logging
import time

sys.path.append(os.getcwd())

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("REAL_GEN_TEST")

from app.database import SessionLocal
from app.core.repositories.account_repo import AccountRepository
from app.core.drivers.api_client import SoraApiClient
from app.core.watermark_remover import WatermarkRemover
from app.core.sentinel import get_sentinel_token

# USE ACCOUNT #1
ACCOUNT_ID = 1

# PROMPT
PROMPT = "A cute cyberpunk cat sitting on a neon rooftop, raining, extensive detail, 8k resolution, cinematic lighting."

async def test_real_generation():
    session = SessionLocal()
    try:
        # 1. Setup
        logger.info(f"--- STARTING REAL GENERATION TEST (Account #{ACCOUNT_ID}) ---")
        repo = AccountRepository(session)
        account = await repo.get_by_id(ACCOUNT_ID)
        
        if not account:
            logger.error("Account not found!")
            return

        api_client = SoraApiClient(
            access_token=account.session.access_token,
            user_agent=account.session.user_agent,
            cookies=account.session.cookies,
            account_email=account.email,
            device_id=account.session.device_id
        )

        # 2. Sentinel for Generate
        sentinel_token = get_sentinel_token(flow="sora_2_create_post")
        
        # CHECK PENDING FIRST
        logger.info("Checking for existing pending tasks...")
        pending_tasks = await api_client.get_pending_tasks()
        task_id = None
        
        if pending_tasks:
            logger.info(f"Found {len(pending_tasks)} pending tasks. Attaching to the first one.")
            # Assuming pending task structure has 'id'
            task_id = pending_tasks[0].get('id')
            logger.info(f"Attaching to Task ID: {task_id}")
        else:
            # 3. Generate Video (With Retry - Heavy Load)
            payload = {
                "kind": "video",
                "prompt": PROMPT,
                "aspect_ratio": "16:9",
                "duration": 5 
            }
            
            for attempt in range(5):
                logger.info(f"Generating video attempt {attempt+1}/5: '{PROMPT}'...")
                gen_result = await api_client.generate_video(payload, sentinel_token, account.session.device_id)
                
                if gen_result.get("success"):
                    task_id = gen_result.get("task_id")
                    logger.info(f"Generation Started! Task ID: {task_id}")
                    break
                else:
                    err = gen_result.get('error')
                    logger.warning(f"Generate Failed: {err}")
                    # If too many tasks, stop retrying and try to find it in pending again?
                    if "too_many_concurrent_tasks" in str(err):
                         logger.warning("Too many tasks! Checking pending list again...")
                         await asyncio.sleep(5)
                         pending = await api_client.get_pending_tasks()
                         if pending:
                             task_id = pending[0].get('id')
                             logger.info(f"Found pending task: {task_id}")
                             break
                    
                    logger.info("Waiting 30 seconds before retry due to heavy load...")
                    await asyncio.sleep(30)
        
        if not task_id:
             logger.error("All generate attempts failed / No pending tasks found.")
             return
        
        # 4. Poll for Completion
        video_id = None
        for i in range(60): # Wait up to 5-10 mins (poll every 10s)
            logger.info(f"Polling status... ({i+1}/60)")
            try:
                # Use get_pending_tasks or feed to find this task
                # Assuming get_task_status or similar logic. 
                # Since we don't have direct get_task(id), we check pending list or latest feed
                # But actually, successful task_id usually *IS* video_id or relates to it.
                # Let's check get_pending_tasks first
                pending = await api_client.get_pending_tasks()
                
                # Check if our task is in pending
                is_pending = False
                for t in pending:
                    if t.get('id') == task_id:
                        is_pending = True
                        progress = t.get('progress', 0)
                        logger.info(f"Task is pending. Progress: {progress}%")
                        break
                
                if not is_pending:
                    # If not pending, it might be done or failed.
                    # Check drafts/feed
                    logger.info("Task not in pending. Checking drafts for completed video...")
                    drafts = await api_client.get_drafts(limit=5)
                    for d in drafts:
                        # Logic to match draft to our task?
                        # Usually latest draft. 
                        # Or match prompt
                        if PROMPT[:20] in d.get('prompt', ''):
                             status = d.get('status')
                             if status == 'succeeded' or status == 'completed':
                                 video_id = d.get('id')
                                 logger.info(f"Found completed video! ID: {video_id}")
                                 break
                    
                    if video_id:
                        break
            
            except Exception as e:
                logger.error(f"Polling error: {e}")
                
            await asyncio.sleep(10)
            
        if not video_id:
            logger.error("Timeout waiting for video generation.")
            return

        # 5. Process (Post + Watermark)
        logger.info("Starting Watermark Removal Flow...")
        clean_url = await WatermarkRemover.process_video(
            video_id=video_id,
            api_client=api_client,
            sentinel_token=get_sentinel_token(flow="sora_2_create_post"), # New token for post
            title="Real Gen Test"
        )
        
        if clean_url:
            logger.info(f"Clean Link: {clean_url}")
            
            # 6. Download
            save_path = f"data/downloads/real_gen_{video_id}.mp4"
            success = WatermarkRemover.download_clean_video(clean_url, save_path)
            if success:
                logger.info("FULL CYCLE COMPLETE SUCCESS!")
            else:
                logger.error("Download failed.")
        else:
             logger.error("Failed to get clean link.")

    except Exception as e:
        logger.error(f"Test crash: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    asyncio.run(test_real_generation())
