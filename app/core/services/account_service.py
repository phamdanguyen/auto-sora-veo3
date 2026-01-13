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
                password=password,  # Should be encrypted
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
            
            # Get Device ID
            device_id = None
            try:
                 device_id = await driver.page.evaluate("() => localStorage.getItem('oai-did') || null")
                 logger.info(f"   Captured device_id: {device_id}")
            except Exception as e:
                 logger.warning(f"Failed to capture device_id: {e}")
            
            # Capture cookies
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
