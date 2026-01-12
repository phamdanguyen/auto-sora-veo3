"""
Account Domain Models

Implements Interface Segregation Principle (ISP):
- Tách Account thành nhiều concerns: Auth, Session, Credits
- Code chỉ depend vào interface cần thiết

Value Objects:
- AccountId: Identity
- AccountAuth: Authentication data
- AccountSession: Session/Token data
- AccountCredits: Credits tracking

Aggregate Root:
- Account: Root entity managing all account concerns
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass(frozen=True)
class AccountId:
    """
    Value Object cho Account ID
    Immutable, validated identity
    """
    value: int

    def __post_init__(self):
        if self.value <= 0:
            raise ValueError("Account ID must be positive")

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class AccountAuth:
    """
    Value Object cho Authentication data
    Implements ISP: Chỉ chứa auth-related fields
    """
    id: AccountId
    email: str
    password: str  # Should be encrypted
    login_mode: str  # "auto" | "manual"

    def __post_init__(self):
        if not self.email:
            raise ValueError("Email cannot be empty")
        if self.login_mode not in ["auto", "manual"]:
            raise ValueError("login_mode must be 'auto' or 'manual'")

    def is_manual_login(self) -> bool:
        """Check if account uses manual login mode"""
        return self.login_mode == "manual"


@dataclass(frozen=True)
class AccountSession:
    """
    Value Object cho Session data
    Implements ISP: Chỉ chứa session-related fields
    """
    id: AccountId
    cookies: Optional[dict]
    access_token: Optional[str]
    device_id: Optional[str]
    user_agent: Optional[str]
    token_status: str  # "pending" | "valid" | "expired"
    token_captured_at: Optional[datetime] = None
    token_expires_at: Optional[datetime] = None

    def __post_init__(self):
        if self.token_status not in ["pending", "valid", "expired"]:
            raise ValueError("token_status must be 'pending', 'valid', or 'expired'")

    def has_valid_token(self) -> bool:
        """Check if session has valid token"""
        return (
            self.token_status == "valid"
            and self.access_token is not None
            and (
                self.token_expires_at is None
                or self.token_expires_at > datetime.utcnow()
            )
        )

    def is_expired(self) -> bool:
        """Check if token is expired"""
        if self.token_expires_at is None:
            return False
        return datetime.utcnow() > self.token_expires_at


@dataclass(frozen=True)
class AccountCredits:
    """
    Value Object cho Credits tracking
    Implements ISP: Chỉ chứa credits-related fields
    """
    id: AccountId
    credits_remaining: Optional[int]
    credits_last_checked: Optional[datetime]
    credits_reset_at: Optional[datetime]

    def has_credits(self) -> bool:
        """
        Check if account has available credits

        Business rule: credits_remaining = None means not checked yet (assume has credits)
        """
        return self.credits_remaining is None or self.credits_remaining > 0

    def is_exhausted(self) -> bool:
        """Check if credits exhausted"""
        return self.credits_remaining is not None and self.credits_remaining <= 0

    def needs_refresh(self, max_age_minutes: int = 60) -> bool:
        """Check if credits need to be refreshed"""
        if self.credits_last_checked is None:
            return True

        age = datetime.utcnow() - self.credits_last_checked
        return age.total_seconds() > (max_age_minutes * 60)


@dataclass
class Account:
    """
    Aggregate Root cho Account

    Manages all account concerns:
    - Authentication
    - Session
    - Credits
    - Usage tracking

    Implements:
    - SRP: Single responsibility (account management)
    - ISP: Composed from smaller value objects
    """
    id: AccountId
    email: str
    platform: str
    auth: AccountAuth
    session: AccountSession
    credits: AccountCredits
    last_used: Optional[datetime] = None
    proxy: Optional[str] = None

    def __post_init__(self):
        if not self.email:
            raise ValueError("Email cannot be empty")
        if not self.platform:
            raise ValueError("Platform cannot be empty")

    @staticmethod
    def from_orm(orm_account) -> 'Account':
        """
        Convert từ SQLAlchemy ORM model sang Domain model

        Implements Dependency Inversion: Domain không depend vào ORM
        """
        return Account(
            id=AccountId(orm_account.id),
            email=orm_account.email,
            platform=orm_account.platform,
            auth=AccountAuth(
                id=AccountId(orm_account.id),
                email=orm_account.email,
                password=orm_account.password,
                login_mode=orm_account.login_mode or "auto"
            ),
            session=AccountSession(
                id=AccountId(orm_account.id),
                cookies=orm_account.cookies,
                access_token=orm_account.access_token,
                device_id=orm_account.device_id,
                user_agent=orm_account.user_agent,
                token_status=orm_account.token_status or "pending",
                token_captured_at=orm_account.token_captured_at,
                token_expires_at=orm_account.token_expires_at
            ),
            credits=AccountCredits(
                id=AccountId(orm_account.id),
                credits_remaining=orm_account.credits_remaining,
                credits_last_checked=orm_account.credits_last_checked,
                credits_reset_at=orm_account.credits_reset_at
            ),
            last_used=orm_account.last_used,
            proxy=orm_account.proxy
        )

    def is_available_for_job(self) -> bool:
        """
        Check if account is available for job execution

        Business rules:
        - Must have credits
        - Must have valid session (if token-based)
        """
        return self.credits.has_credits() and (
            self.session.has_valid_token() or self.auth.is_manual_login()
        )

    def needs_login(self) -> bool:
        """Check if account needs login"""
        return (
            not self.session.has_valid_token()
            and not self.auth.is_manual_login()
        )

    def __str__(self) -> str:
        return f"Account(id={self.id}, email={self.email}, platform={self.platform})"

    def __repr__(self) -> str:
        return self.__str__()
