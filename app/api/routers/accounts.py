"""
Accounts Router
Implements: Single Responsibility Principle (SRP)

This router handles all account-related endpoints:
- CRUD operations
- Credit management
- Login operations
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
from ...core.services.account_service import AccountService
from ...core.domain.account import Account
from ..dependencies import get_account_service
from sqlalchemy.orm import Session
from ..dependencies import get_db

import logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/accounts", tags=["accounts"])

# ========== Schemas ==========
class AccountCreate(BaseModel):
    """Schema for creating a new account"""
    platform: str
    email: str
    password: str
    password: str
    proxy: Optional[str] = None


class AccountUpdate(BaseModel):
    """Schema for updating an account"""
    login_mode: Optional[str] = None
    proxy: Optional[str] = None
    # Add other fields as needed


class AccountResponse(BaseModel):
    """Schema for account response"""
    id: int
    platform: str
    email: str
    proxy: Optional[str] = None
    last_used: Optional[datetime] = None
    credits_remaining: Optional[int] = None
    credits_last_checked: Optional[datetime] = None
    credits_reset_at: Optional[datetime] = None
    token_status: str = "pending"
    token_captured_at: Optional[datetime] = None
    login_mode: str = "auto"

    @staticmethod
    def from_domain(account: Account) -> "AccountResponse":
        """Convert domain Account to API response"""
        return AccountResponse(
            id=account.id.value,
            platform=account.platform,
            email=account.email,
            proxy=account.proxy,
            last_used=account.last_used,
            credits_remaining=account.credits.credits_remaining if account.credits else None,
            credits_last_checked=account.credits.credits_last_checked if account.credits else None,
            credits_reset_at=account.credits.credits_reset_at if account.credits else None,
            token_status=account.session.token_status if account.session else "pending",
            token_captured_at=account.session.token_captured_at if account.session else None,
            login_mode=account.auth.login_mode if account.auth else "auto"
        )


class CreditsResponse(BaseModel):
    """Schema for credits response"""
    ok: bool
    credits_remaining: Optional[int]
    credits_last_checked: Optional[str]


# ========== Endpoints ==========
@router.post("/", response_model=AccountResponse)
async def create_account(
    data: AccountCreate,
    service: AccountService = Depends(get_account_service)
):
    """
    Create a new account

    Args:
        data: Account creation data (platform, email, password, proxy)
        service: AccountService instance (injected)

    Returns:
        Created account details

    Raises:
        HTTPException 400: If email already exists or validation fails
    """
    try:
        account = await service.create_account(
            platform=data.platform,
            email=data.email,
            password=data.password,
            proxy=data.proxy
        )
        return AccountResponse.from_domain(account)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/", response_model=List[AccountResponse])
async def list_accounts(
    skip: int = 0,
    limit: int = 100,
    service: AccountService = Depends(get_account_service)
):
    """
    List all accounts

    Args:
        skip: Number of accounts to skip (pagination)
        limit: Maximum number of accounts to return
        service: AccountService instance (injected)

    Returns:
        List of accounts
    """
    accounts = await service.list_accounts(skip, limit)
    return [AccountResponse.from_domain(acc) for acc in accounts]


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: int,
    service: AccountService = Depends(get_account_service)
):
    """
    Get account by ID

    Args:
        account_id: Account ID
        service: AccountService instance (injected)

    Returns:
        Account details

    Raises:
        HTTPException 404: If account not found
    """
    account = await service.get_account(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return AccountResponse.from_domain(account)


@router.delete("/{account_id}")
async def delete_account(
    account_id: int,
    service: AccountService = Depends(get_account_service)
):
    """
    Delete account

    Args:
        account_id: Account ID
        service: AccountService instance (injected)

    Returns:
        Success status

    Raises:
        HTTPException 404: If account not found
    """
    success = await service.delete_account(account_id)
    if not success:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"ok": True}


@router.patch("/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: int,
    data: AccountUpdate,
    service: AccountService = Depends(get_account_service)
):
    """
    Update account details
    
    Args:
        account_id: Account ID
        data: Fields to update
        service: AccountService
        
    Returns:
        Updated account
        
    Raises:
        HTTPException 404: If account not found
    """
    account = await service.update_account(
        account_id,
        **data.dict(exclude_unset=True)
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return AccountResponse.from_domain(account)


@router.post("/{account_id}/refresh_credits", response_model=CreditsResponse)
async def refresh_credits(
    account_id: int,
    service: AccountService = Depends(get_account_service)
):
    """
    Refresh credits for a specific account

    Uses the account's access token to fetch current credits from the API.
    Updates the account's credits in the database.

    Args:
        account_id: Account ID
        service: AccountService instance (injected)

    Returns:
        Updated credits information

    Raises:
        HTTPException 400: If refresh fails (no token, API error, etc.)
    """
    try:
        credits = await service.refresh_credits(account_id)
        if not credits:
            raise HTTPException(status_code=400, detail="Failed to refresh credits")

        return CreditsResponse(
            ok=True,
            credits_remaining=credits.credits_remaining,
            credits_last_checked=credits.credits_last_checked.isoformat() if credits.credits_last_checked else None
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ========== Complex Endpoints (TODO) ==========
# These endpoints require more complex logic and will be implemented later
# based on the existing endpoints.py implementation


@router.post("/{account_id}/login", response_model=AccountResponse)
async def login_account(
    account_id: int,
    service: AccountService = Depends(get_account_service)
):
    """
    Manual login for account
    
    Opens a visible browser, allows user to login manually,
    captures token and saves to DB for headless operation.
    """
    try:
        account = await service.login_account(account_id)
        if not account:
            raise HTTPException(status_code=404, detail="Account not found or login failed")
        return AccountResponse.from_domain(account)
    except TimeoutError:
         raise HTTPException(status_code=408, detail="Login timed out")
    except ValueError as e:
         raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
         logger.error(f"Login failed: {e}", exc_info=True)
         raise HTTPException(status_code=500, detail=str(e))


@router.post("/global_manual_login", response_model=AccountResponse)
async def global_manual_login(
    service: AccountService = Depends(get_account_service)
):
    """
    Global manual login
    
    Opens browser without specific account, waits for user to login,
    detects email from token, creates/updates account in DB.
    """
    try:
        account = await service.global_manual_login()
        if not account:
            raise HTTPException(status_code=400, detail="Login failed")
        return AccountResponse.from_domain(account)
    except TimeoutError:
        raise HTTPException(status_code=408, detail="Login timed out")
    except Exception as e:
        logger.error(f"Global manual login failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/check_credits")
async def check_all_credits(
    service: AccountService = Depends(get_account_service)
):
    """
    Check credits for all accounts
    
    Uses existing tokens only, does not trigger login/browser.
    """
    return await service.check_all_credits()


@router.post("/refresh_all")
async def refresh_all_accounts(
    service: AccountService = Depends(get_account_service)
):
    """
    Refresh all accounts
    
    Validates tokens via API, updates credits and reset time.
    """
    return await service.refresh_all_accounts()
