"""
Account Service - Business logic cho Account management
Implements: Single Responsibility Principle (SRP)
"""
from typing import Optional, List
from ..repositories.account_repo import AccountRepository
from ..domain.account import Account, AccountCredits
from ..drivers.factory import DriverFactory
import logging

logger = logging.getLogger(__name__)

class AccountService:
    """Service xử lý account business logic"""

    def __init__(
        self,
        account_repo: AccountRepository,
        driver_factory: DriverFactory
    ):
        self.account_repo = account_repo
        self.driver_factory = driver_factory

    async def create_account(
        self,
        platform: str,
        email: str,
        password: str,
        proxy: Optional[str] = None
    ) -> Account:
        """Create new account"""
        # Import encryption function
        from ..security import encrypt_password

        # Business rule: Email must be unique
        existing = await self.account_repo.get_by_email(email)
        if existing:
            raise ValueError(f"Account with email {email} already exists")

        # Create account
        from ..domain.account import AccountAuth, AccountSession, AccountCredits, AccountId
        account = Account(
            id=AccountId(0),  # Will be set by DB
            email=email,
            platform=platform,
            auth=AccountAuth(
                id=AccountId(0),
                email=email,
                password=encrypt_password(password),  # Encrypt password before storing
                login_mode="auto"
            ),
            session=AccountSession(
                id=AccountId(0),
                cookies=None,
                access_token=None,
                device_id=None,
                user_agent=None,
                token_status="pending"
            ),
            credits=AccountCredits(
                id=AccountId(0),
                credits_remaining=None,
                credits_last_checked=None,
                credits_reset_at=None
            ),
            proxy=proxy
        )

        created = await self.account_repo.create(account)
        self.account_repo.commit()
        return created

    async def delete_account(self, account_id: int) -> bool:
        """Delete account"""
        success = await self.account_repo.delete(account_id)
        if success:
            self.account_repo.commit()
        return success

    async def get_account(self, account_id: int) -> Optional[Account]:
        """Get account by ID"""
        return await self.account_repo.get_by_id(account_id)

    async def list_accounts(self, skip: int = 0, limit: int = 100) -> List[Account]:
        """List all accounts"""
        return await self.account_repo.get_all(skip, limit)

    async def refresh_credits(self, account_id: int) -> Optional[AccountCredits]:
        """
        Refresh credits for an account using API

        Returns:
            Updated AccountCredits or None if failed
        """
        account = await self.account_repo.get_by_id(account_id)
        if not account:
            raise ValueError(f"Account {account_id} not found")

        if not account.session.access_token:
            logger.warning(f"Account {account_id} has no access token")
            return None

        # Create driver
        driver = self.driver_factory.create_driver(
            platform=account.platform,
            access_token=account.session.access_token,
            device_id=account.session.device_id,
            user_agent=account.session.user_agent
        )

        try:
            # Get credits via API
            credits_info = await driver.get_credits()

            if credits_info.credits is not None:
                # Update account credits
                from datetime import datetime, timedelta
                from ..domain.account import AccountCredits, AccountId

                new_credits = AccountCredits(
                    id=account.id,
                    credits_remaining=credits_info.credits,
                    credits_last_checked=datetime.utcnow(),
                    credits_reset_at=(
                        datetime.utcnow() + timedelta(seconds=credits_info.reset_seconds)
                        if credits_info.reset_seconds else None
                    )
                )

                # Update account
                account.credits = new_credits
                await self.account_repo.update(account)
                self.account_repo.commit()

                return new_credits
            else:
                logger.warning(f"Failed to get credits for account {account_id}: {credits_info.error}")
                return None

        finally:
            await driver.stop()

    async def update_account(self, account_id: int, **kwargs) -> Optional[Account]:
        """Update account fields"""
        account = await self.account_repo.get_by_id(account_id)
        if not account:
            return None
        
        from dataclasses import replace

        # Handle specific fields
        if 'login_mode' in kwargs and account.auth:
             # AccountAuth is frozen, use replace
             account.auth = replace(account.auth, login_mode=kwargs['login_mode'])
        
        if 'proxy' in kwargs:
             account.proxy = kwargs['proxy']
        
        # Add other fields as needed
        
        await self.account_repo.update(account)
        self.account_repo.commit()
        return account

    async def login_account(self, account_id: int) -> Optional[Account]:
        """
        Manual login for specific account.
        Opens visible browser, logs in, captures token.
        """
        import time
        import os
        import asyncio
        from datetime import datetime
        from ..security import decrypt_password
        # Note: account_manager and global lock should be injected or handled globally
        # For simplicity in this refactor, we will implement the logic here directly
        # but ideally we should use the same locking mechanisms usually found in account_manager
        
        # We need to import account_manager dynamically to avoid circular header issues if any
        from .. import account_manager
        
        account = await self.account_repo.get_by_id(account_id)
        if not account:
            raise ValueError("Account not found")

        # Acquire Lock
        # Using account_manager locks
        lock = await account_manager.get_account_lock(account_id)
        await account_manager.mark_account_busy(account_id)

        # Global Lock (Simple implementation for now within Service, 
        # normally should be shared. We can use a class var or simple Lock)
        # BUT, if we run multiple workers, this lock needs to be effective. 
        # Since we are moving away from legacy, lets define a lock here or use the one in manager if exists.
        # account_manager doesn't have a global browser lock exposed usually.
        # Let's create a local one for the service or just proceed carefully.
        # For safety, let's assume single operation for manual tasks.
        
        logger.info(f"[LOGIN] Starting manual login for {account.email}")
        
        driver = None
        try:
            async with lock:
                # Profile path
                profile_path = f"data/profiles/acc_{account.id.value}_{int(time.time())}"
                os.makedirs(profile_path, exist_ok=True)
                
                # Create Driver (Visible)
                # We use factory but need to specify headless=False. 
                # Factory might not expose headless override easily if simpler signature found.
                # Let's check factory usage. Factory create_driver signature:
                # create_driver(self, platform, access_token=None, device_id=None, user_agent=None)
                # It doesn't seem to allow overriding headless/userdata easily if not designed.
                # So we fallback to creating SoraDriver directly for this specialized manual task.
                
                from ..drivers.sora import SoraBrowserDriver
                driver = SoraBrowserDriver(
                    headless=False,
                    user_data_dir=os.path.abspath(profile_path),
                    channel=None
                )
                
                await driver.start()
                
                # Login
                await driver.login(
                    email=account.email,
                    password=decrypt_password(account.auth.password) if account.auth.password else ""
                )
                
                # Check URL
                if "sora.chatgpt.com" not in driver.page.url:
                     await driver.page.goto("https://sora.chatgpt.com/", wait_until="networkidle")
                     
                # Wait for token
                max_wait = 300
                poll_interval = 3
                token_captured = False
                
                logger.info(f"[WAIT] Waiting for token capture (max {max_wait}s)...")
                
                for i in range(max_wait // poll_interval):
                    if driver.latest_access_token:
                        token_captured = True
                        break
                    await asyncio.sleep(poll_interval)
                    
                if not token_captured:
                    raise TimeoutError("Login timeout or 2FA not completed")
                    
                # Save Data
                from dataclasses import replace
                
                cookies = await driver.context.cookies()
                device_id = await driver.page.evaluate("() => localStorage.getItem('oai-did') || null")
                
                new_session = replace(
                    account.session,
                    access_token=driver.latest_access_token,
                    cookies=cookies,
                    device_id=device_id,
                    user_agent=driver.latest_user_agent,
                    token_status="valid",
                    token_captured_at=datetime.utcnow()
                )
                account.session = new_session
                
                # Update Credits immediately if possible
                try:
                    credits = await driver.get_credits()
                    if credits.credits is not None:
                         from ..domain.account import AccountCredits
                         new_credits = AccountCredits(
                            id=account.id,
                            credits_remaining=credits.credits,
                            credits_last_checked=datetime.utcnow(),
                            credits_reset_at=None # TODO: Parse reset seconds if needed
                         )
                         account.credits = new_credits
                except:
                    pass
                
                await self.account_repo.update(account)
                self.account_repo.commit()
                
                return account

        finally:
            if driver:
                await driver.stop()
            await account_manager.mark_account_free(account_id)

    async def global_manual_login(self) -> Optional[Account]:
        """
        Global manual login process.
        Opens browser, waits for user login, creates/updates account.
        """
        import time
        from ..domain.account import AccountAuth, AccountSession, AccountCredits, AccountId
        from datetime import datetime
        import logging

        # Setup file logging for debug
        file_handler = logging.FileHandler("debug_login.log", mode='w', encoding='utf-8')
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(file_handler)
        logger.setLevel(logging.INFO)

        # Create driver (Headless=False)
        # Use temp profile
        profile_path = f"data/profiles/temp_login_{int(time.time())}"
        import os
        os.makedirs(profile_path, exist_ok=True)
        
        # We need a custom driver instance here, bypassing factory if factory assumes existing account
        # But factory.create_driver is for EXISTING accounts.
        # We want a fresh driver.
        # Ideally factory should support "anonymous" driver creation?
        # For now, let's use the factory to get the class and instantiate it?
        # Or better: Add create_anonymous_driver to factory?
        # Let's import SoraDriver directly here to keep it simple as specialized logic, 
        # OR extend factory. Let's use factory if possible.
        # But for now, direct import is easiest for migration path.
        # To adhere to SRP, let's ask factory for the class.
        
        # To adhere to SRP, let's ask factory for the class.
        
        try:
             driver = self.driver_factory.create_driver(
                "sora",
                headless=False,
                user_data_dir=os.path.abspath(profile_path)
             )
        except ValueError:
             raise ValueError("Sora driver not registered")
        
        try:
            await driver.start()
            
            # Wait for login
            email = await driver.wait_for_login(timeout=300)
            
            if not email:
                raise TimeoutError("Login timed out or email not detected")
                
            # Upsert Account
            logger.info(f"💾 Upserting account for {email}...")
            existing = await self.account_repo.get_by_email(email)
            
            if existing:
                logger.info(f"   Found existing account {existing.id}")
                account = existing
                account.auth.login_mode = "manual"
            else:
                logger.info("   Creating NEW account...")
                account = Account(
                    id=AccountId(0),
                    email=email,
                    platform="sora",
                    auth=AccountAuth(
                        id=AccountId(0),
                        email=email,
                        password="",
                        login_mode="manual"
                    ),
                    session=AccountSession(
                        id=AccountId(0),
                        cookies=None,
                        access_token=None,
                        device_id=None,
                        user_agent=None,
                        token_status="valid",
                        token_captured_at=None,
                        token_expires_at=None
                    ),
                    credits=AccountCredits(
                        id=AccountId(0),
                        credits_remaining=None,
                        credits_last_checked=None,
                        credits_reset_at=None
                    )
                )
                account = await self.account_repo.create(account)
                logger.info(f"   Created account with ID: {account.id}")
                
            # Update Session Info
            logger.info("UPDATE: Updating session info...")
            from dataclasses import replace
            from ..drivers.abstractions import BrowserBasedDriver
            
            if not isinstance(driver, BrowserBasedDriver):
                 logger.error("Global manual login requires a BrowserBasedDriver")
                 return None

            # Get Device ID
            device_id = None
            try:
                 # Check if page is initialized
                 if driver.page:
                    device_id = await driver.page.evaluate("() => localStorage.getItem('oai-did') || null")
                    logger.info(f"   Captured device_id: {device_id}")
            except Exception as e:
                 logger.warning(f"Failed to capture device_id: {e}")
            
            # Capture cookies
            cookies = []
            if driver.context:
                cookies = await driver.context.cookies()
            logger.info(f"   Captured {len(cookies)} cookies")
            
            # Create new session object with updated values
            new_session = replace(
                account.session,
                access_token=driver.latest_access_token,
                user_agent=driver.latest_user_agent,
                device_id=device_id,
                cookies=cookies,
                token_captured_at=datetime.utcnow(),
                token_status="valid"
            )
            
            account.session = new_session
            
            logger.info("UPDATE: Saving account update...")
            await self.account_repo.update(account)
            self.account_repo.commit()
            
            logger.info("✅ Global manual login SUCCESS")
            return account
            
        finally:
            await driver.stop()
            try:
                logger.removeHandler(file_handler)
                file_handler.close()
            except:
                pass

    async def check_all_credits(self) -> dict:
        """
        Check credits for all accounts using EXISTING tokens only.
        Does NOT trigger login/browser.
        """
        # Import moved inside to avoid circular imports if any, though driver factory handles it
        from datetime import datetime
        
        accounts = await self.account_repo.get_all(skip=0, limit=1000) # Get all accounts
        results = {
            "total": len(accounts), 
            "updated": 0, 
            "failed": 0, 
            "expired": 0,  # Token/cookies hết hạn
            "no_token": 0,  # Chưa login
            "details": []  # Chi tiết từng account
        }
        
        logger.info(f"[CREDITS] Checking credits for {len(accounts)} accounts (API-only)...")
        
        for acc in accounts:
            detail = {"id": acc.id.value, "email": acc.email, "status": "unknown"}
            
            if not acc.session.access_token:
                detail["status"] = "no_token"
                detail["message"] = "Chưa login - cần nhấn nút Login"
                results["no_token"] += 1
                results["details"].append(detail)
                continue
                
            try:
                # Use Factory to get a driver instance configured for API access
                # Note: We need a way to pass cookies/email if the driver needs them
                # The factory creates a driver. The driver might need hydration.
                
                # For now, let's assume we create a driver and it uses the token.
                driver = self.driver_factory.create_driver(
                    platform=acc.platform,
                    access_token=acc.session.access_token,
                    device_id=acc.session.device_id,
                    user_agent=acc.session.user_agent
                )
                # Manually set cookies if the driver supports/needs it (SoraApiDriver usually does)
                if hasattr(driver, 'cookies') and acc.session.cookies:
                     driver.cookies = acc.session.cookies
                if hasattr(driver, 'account_email'):
                     driver.account_email = acc.email

                # Check credits
                credits_obj = await driver.get_credits()
                
                # Handle response
                if credits_obj.error_code:
                     # Map error codes
                    if credits_obj.error_code == "TOKEN_EXPIRED":
                        acc.session.token_status = "expired"
                        detail["status"] = "expired"
                        detail["message"] = "Token/cookies đã hết hạn"
                        results["expired"] += 1
                    elif credits_obj.error_code == "NO_TOKEN":
                        detail["status"] = "no_token"
                        results["no_token"] += 1
                    else:
                        detail["status"] = "error"
                        detail["message"] = credits_obj.error or "Unknown error"
                        results["failed"] += 1
                        
                    # Update status in DB
                    await self.account_repo.update(acc)

                elif credits_obj.credits is not None:
                    # Success
                    from datetime import datetime, timedelta
                    from ..domain.account import AccountCredits
                    
                    acc.session.token_status = "valid"
                    
                    new_credits = AccountCredits(
                        id=acc.id,
                        credits_remaining=credits_obj.credits,
                        credits_last_checked=datetime.utcnow(),
                        credits_reset_at=(
                            datetime.utcnow() + timedelta(seconds=credits_obj.reset_seconds)
                            if credits_obj.reset_seconds else None
                        )
                    )
                    acc.credits = new_credits
                    
                    await self.account_repo.update(acc)
                    
                    results["updated"] += 1
                    detail["status"] = "success"
                    detail["credits"] = credits_obj.credits
                else:
                    detail["status"] = "error"
                    detail["message"] = "Không nhận được dữ liệu"
                    results["failed"] += 1
            
            except Exception as e:
                logger.error(f"[ERROR] Failed to check credits for {acc.email}: {e}")
                detail["status"] = "error"
                detail["message"] = str(e)
                results["failed"] += 1
            
            finally:
                if 'driver' in locals():
                    await driver.stop()
                    
            results["details"].append(detail)
            
        self.account_repo.commit()
        return results

    async def refresh_all_accounts(self) -> dict:
        """
        Refresh all accounts:
        - Check credits via API
        - If expired and login_mode='auto', try to re-login (NOT IMPLEMENTED HERE for safety/complexity, 
          usually we just mark expired and let worker or user handle it, 
          OR we can port the re-login logic if needed. 
          For now, mimicking check_all_credits but intended for 'Refresh' button action)
        
        Ref: legacy endpoints had auto-login logic. 
        For this refactor, we will focus on updating status. verify_all behavior.
        """
        return await self.check_all_credits()

