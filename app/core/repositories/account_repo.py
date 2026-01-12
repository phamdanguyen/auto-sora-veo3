"""
Account Repository

Implementation of repository pattern for Account aggregate

Implements:
- DIP: Implements abstract BaseRepository
- SRP: Single responsibility (Account data access)
- ISP: Provides specific methods for account queries
"""

from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import or_
from .base import BaseRepository
from ..domain.account import Account, AccountId, AccountCredits, AccountSession
from ...models import Account as AccountModel


class AccountRepository(BaseRepository[Account]):
    """
    Repository cho Account aggregate

    Handles:
    - CRUD operations
    - Account-specific queries (by email, available accounts, etc.)
    - Conversion between domain models and ORM models
    """

    async def get_by_id(self, id: int) -> Optional[Account]:
        """
        Lấy account theo ID

        Args:
            id: Account ID

        Returns:
            Account domain model or None
        """
        orm_account = self.session.query(AccountModel).filter_by(id=id).first()
        return Account.from_orm(orm_account) if orm_account else None

    async def get_by_email(self, email: str) -> Optional[Account]:
        """
        Lấy account theo email

        Args:
            email: Account email

        Returns:
            Account domain model or None
        """
        orm_account = self.session.query(AccountModel).filter_by(email=email).first()
        return Account.from_orm(orm_account) if orm_account else None

    async def get_all(self, skip: int = 0, limit: int = 100) -> List[Account]:
        """
        Lấy danh sách accounts

        Args:
            skip: Records to skip
            limit: Max records to return

        Returns:
            List of Account domain models
        """
        orm_accounts = (
            self.session.query(AccountModel)
            .order_by(AccountModel.id.asc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return [Account.from_orm(acc) for acc in orm_accounts]

    async def get_available_accounts(
        self,
        platform: str,
        exclude_ids: Optional[List[int]] = None
    ) -> List[Account]:
        """
        Lấy accounts available (có credits)

        Business rules:
        - credits_remaining is None (not checked yet) OR credits_remaining > 0
        - Not in exclude_ids list

        Args:
            platform: Platform filter ("sora", "veo3", etc.)
            exclude_ids: IDs to exclude from results

        Returns:
            List of available Account domain models
        """
        query = self.session.query(AccountModel).filter(
            AccountModel.platform == platform,
            or_(
                AccountModel.credits_remaining == None,
                AccountModel.credits_remaining > 0
            )
        )

        if exclude_ids:
            query = query.filter(AccountModel.id.notin_(exclude_ids))

        orm_accounts = query.all()
        return [Account.from_orm(acc) for acc in orm_accounts]

    async def get_credits(self, account_id: int) -> Optional[AccountCredits]:
        """
        Chỉ lấy credits info (ISP - Interface Segregation)

        Optimized query - only SELECT credits fields

        Args:
            account_id: Account ID

        Returns:
            AccountCredits or None
        """
        orm_account = self.session.query(AccountModel).filter_by(id=account_id).first()
        if not orm_account:
            return None

        return AccountCredits(
            id=AccountId(orm_account.id),
            credits_remaining=orm_account.credits_remaining,
            credits_last_checked=orm_account.credits_last_checked,
            credits_reset_at=orm_account.credits_reset_at
        )

    async def get_session(self, account_id: int) -> Optional[AccountSession]:
        """
        Chỉ lấy session info (ISP - Interface Segregation)

        Optimized query - only SELECT session fields

        Args:
            account_id: Account ID

        Returns:
            AccountSession or None
        """
        orm_account = self.session.query(AccountModel).filter_by(id=account_id).first()
        if not orm_account:
            return None

        return AccountSession(
            id=AccountId(orm_account.id),
            cookies=orm_account.cookies,
            access_token=orm_account.access_token,
            device_id=orm_account.device_id,
            user_agent=orm_account.user_agent,
            token_status=orm_account.token_status or "pending",
            token_captured_at=orm_account.token_captured_at,
            token_expires_at=orm_account.token_expires_at
        )

    async def create(self, account: Account) -> Account:
        """
        Tạo account mới

        Args:
            account: Account domain model

        Returns:
            Created account with ID populated
        """
        orm_account = AccountModel(
            platform=account.platform,
            email=account.email,
            password=account.auth.password,
            proxy=account.proxy,
            login_mode=account.auth.login_mode
        )
        self.session.add(orm_account)
        self.flush()  # Get auto-generated ID
        return Account.from_orm(orm_account)

    async def update(self, account: Account) -> Account:
        """
        Cập nhật account

        Updates all fields from domain model

        Args:
            account: Account domain model

        Returns:
            Updated account

        Raises:
            ValueError: If account not found
        """
        orm_account = self.session.query(AccountModel).filter_by(id=account.id.value).first()
        if not orm_account:
            raise ValueError(f"Account {account.id.value} not found")

        # Update fields from domain model
        orm_account.email = account.email
        orm_account.platform = account.platform
        orm_account.password = account.auth.password
        orm_account.login_mode = account.auth.login_mode
        orm_account.cookies = account.session.cookies
        orm_account.access_token = account.session.access_token
        orm_account.device_id = account.session.device_id
        orm_account.user_agent = account.session.user_agent
        orm_account.token_status = account.session.token_status
        orm_account.token_captured_at = account.session.token_captured_at
        orm_account.token_expires_at = account.session.token_expires_at
        orm_account.credits_remaining = account.credits.credits_remaining
        orm_account.credits_last_checked = account.credits.credits_last_checked
        orm_account.credits_reset_at = account.credits.credits_reset_at
        orm_account.last_used = account.last_used
        orm_account.proxy = account.proxy

        self.flush()
        return Account.from_orm(orm_account)

    async def update_credits(
        self,
        account_id: int,
        credits: AccountCredits
    ) -> Account:
        """
        Update only credits fields (optimized)

        Args:
            account_id: Account ID
            credits: New credits data

        Returns:
            Updated account

        Raises:
            ValueError: If account not found
        """
        orm_account = self.session.query(AccountModel).filter_by(id=account_id).first()
        if not orm_account:
            raise ValueError(f"Account {account_id} not found")

        # Update only credits fields
        orm_account.credits_remaining = credits.credits_remaining
        orm_account.credits_last_checked = credits.credits_last_checked
        orm_account.credits_reset_at = credits.credits_reset_at

        self.flush()
        return Account.from_orm(orm_account)

    async def update_session(
        self,
        account_id: int,
        session: AccountSession
    ) -> Account:
        """
        Update only session fields (optimized)

        Args:
            account_id: Account ID
            session: New session data

        Returns:
            Updated account

        Raises:
            ValueError: If account not found
        """
        orm_account = self.session.query(AccountModel).filter_by(id=account_id).first()
        if not orm_account:
            raise ValueError(f"Account {account_id} not found")

        # Update only session fields
        orm_account.cookies = session.cookies
        orm_account.access_token = session.access_token
        orm_account.device_id = session.device_id
        orm_account.user_agent = session.user_agent
        orm_account.token_status = session.token_status
        orm_account.token_captured_at = session.token_captured_at
        orm_account.token_expires_at = session.token_expires_at

        self.flush()
        return Account.from_orm(orm_account)

    async def delete(self, id: int) -> bool:
        """
        Xóa account

        Args:
            id: Account ID

        Returns:
            True if deleted, False if not found
        """
        orm_account = self.session.query(AccountModel).filter_by(id=id).first()
        if orm_account:
            self.session.delete(orm_account)
            return True
        return False

    async def count_by_platform(self, platform: str) -> int:
        """
        Count accounts by platform

        Args:
            platform: Platform name

        Returns:
            Number of accounts
        """
        return self.session.query(AccountModel).filter_by(platform=platform).count()
