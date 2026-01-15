
import asyncio
import sys
import os
import json
import logging
sys.path.append(os.getcwd())

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("E2E_TEST")

from app.database import SessionLocal
from app.core.repositories.account_repo import AccountRepository
from app.core.drivers.api_client import SoraApiClient
from app.core.watermark_remover import WatermarkRemover
from app.core.sentinel import get_sentinel_token

async def test_full_flow():
    session = SessionLocal()
    try:
        # 1. Setup
        account_id = 1
        video_id = "gen_01kes5pzd4edwrhs38m10vqq3s"
        
        repo = AccountRepository(session)
        account = await repo.get_by_id(account_id)
        if not account:
            logger.error(f"Account #{account_id} not found")
            return
            
        logger.info(f"Using account: {account.email}")
        
        # 2. Initialize API Client
        api_client = SoraApiClient(
            access_token=account.session.access_token,
            user_agent=account.session.user_agent or "Mozilla/5.0",
            cookies=account.session.cookies,
            account_email=account.email,
            device_id=account.session.device_id
        )
        
        # 3. Get Sentinel Token
        logger.info("Generating Sentinel Token...")
        try:
            token_data = get_sentinel_token(flow="sora_2_create_post")
            sentinel_token = json.dumps(json.loads(token_data) if isinstance(token_data, str) else token_data)
        except Exception as e:
            logger.error(f"Sentinel failed: {e}")
            return
            
        # 4. Process Video (Post -> Clean URL)
        import time
        unique_title = f"E2E Test Video {int(time.time())}"
        logger.info(f"Processing video {video_id} for watermark removal with title: {unique_title}...")
        clean_url = await WatermarkRemover.process_video(
            video_id=video_id,
            api_client=api_client,
            sentinel_token=sentinel_token,
            title=unique_title
        )

        
        if not clean_url:
            logger.error("Failed to get clean URL")
            return
            
        logger.info(f"SUCCESS! Clean URL: {clean_url}")
        
        # 5. Download
        save_path = "data/downloads/e2e_test_clean.mp4"
        logger.info(f"Downloading to {save_path}...")
        success = WatermarkRemover.download_clean_video(clean_url, save_path)
        
        if success:
            logger.info(f"DONE! Video saved to {save_path}")
            size = os.path.getsize(save_path)
            logger.info(f"File size: {size:,} bytes")
        else:
            logger.error("Download failed")
            
    finally:
        session.close()

if __name__ == "__main__":
    asyncio.run(test_full_flow())
