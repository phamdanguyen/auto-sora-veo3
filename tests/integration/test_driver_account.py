
import asyncio
import logging
import sys
import os

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add path
sys.path.append(os.getcwd())

from app.database import SessionLocal
from app.core.repositories.account_repo import AccountRepository
from app.core.drivers.sora.api_driver import SoraApiDriver

async def test_account():
    session = SessionLocal()
    try:
        repo = AccountRepository(session)
        account = await repo.get_by_id(1) # Account 1
        
        if not account:
            logger.error("Account #1 not found")
            return

        logger.info(f"Testing Account: {account.email}")
        
        driver = SoraApiDriver(
            access_token=account.session.access_token,
            device_id=account.session.device_id,
            cookies=account.session.cookies,
            user_agent=account.session.user_agent,
            account_email=account.email
        )
        
        print("Calling get_pending_tasks...")
        tasks = await driver.get_pending_tasks()
        print(f"Pending Tasks: {len(tasks)}")
        for t in tasks:
            print(f" - {t}")
            
        print("Calling get_drafts...")
        drafts = await driver.api_client.get_drafts()
        print(f"Drafts: {len(drafts)}")
        for d in drafts:
            print(f" - {d.get('id')} | {d.get('status')} | {d.get('prompt')[:30]}...")

        print("Calling Feed (Manual)...")
        from curl_cffi.requests import AsyncSession
        async with AsyncSession(impersonate="chrome120") as s:
            r = await s.get(
                "https://sora.chatgpt.com/backend/project_y/feed",
                headers=driver.api_client.headers,
                params={"limit": 15},
                timeout=20
            )
            print(f"Feed Status: {r.status_code}")
            if r.status_code == 200:
                feed_items = r.json().get("items", [])
                print(f"Feed Items: {len(feed_items)}")
                for f in feed_items:
                    print(f" - {f.get('id')} | {f.get('status')} | {f.get('prompt')[:30]}...")

        print("Calling get_credits...")
        credits = await driver.get_credits()
        print(f"Credits: {credits}")
    finally:
        session.close()

if __name__ == "__main__":
    asyncio.run(test_account())
