from sqlalchemy.orm import Session
from sqlalchemy import func
from .. import models
import random
from typing import Optional, Set
from datetime import datetime, timedelta
import logging
import asyncio
import time
from collections import defaultdict

logger = logging.getLogger(__name__)

# Track accounts currently being used by workers (in-memory)
_busy_accounts: Set[int] = set()
_busy_accounts_lock: Optional[asyncio.Lock] = None

# Track actual asyncio locks for profile directory access
# Key: account_id, Value: asyncio.Lock
_account_file_locks: dict[int, asyncio.Lock] = {}
# Track actual asyncio locks for profile directory access
# Key: account_id, Value: asyncio.Lock
_account_file_locks: dict[int, asyncio.Lock] = {}
_account_file_locks_mutex = asyncio.Lock()

# Rate limiting tracking
SUBMIT_RATE_LIMIT_SECONDS = 30
_account_submit_times: dict[int, float] = {}  # account_id -> timestamp

def get_cooldown_remaining(account_id: int) -> float:
    """Get remaining cooldown seconds for an account"""
    last = _account_submit_times.get(account_id, 0)
    elapsed = time.time() - last
    return max(0.0, SUBMIT_RATE_LIMIT_SECONDS - elapsed)

def record_submit_time(account_id: int):
    """Record a submit event for rate limiting"""
    _account_submit_times[account_id] = time.time()
    logger.debug(f"Recorded submit time for Account #{account_id}")

def is_account_ready(account_id: int) -> bool:
    """Check if account is ready for submit (rate limit check)"""
    return get_cooldown_remaining(account_id) <= 0

async def get_account_lock(account_id: int) -> asyncio.Lock:
    """Get or create an execution lock for a specific account (prevents chrome profile conflicts)"""
    async with _account_file_locks_mutex:
        if account_id not in _account_file_locks:
            _account_file_locks[account_id] = asyncio.Lock()
        return _account_file_locks[account_id]


def _get_lock():
    """Lazy-init lock to avoid event loop issues"""
    global _busy_accounts_lock
    if _busy_accounts_lock is None:
        _busy_accounts_lock = asyncio.Lock()
    return _busy_accounts_lock


def get_available_account(db: Session, platform: str, exclude_ids: list[int] = None) -> Optional[models.Account]:
    """
    Get an account with credits available and not currently busy.
    No more status column - only credits matter.
    exclude_ids: Optional list of account IDs to ignore (e.g. recently failed).
    """
    from sqlalchemy import or_

    query = db.query(models.Account).filter(
        models.Account.platform == platform,
        # Only check if account has credits
        # Allow if credits_remaining is None (not checked yet) OR credits_remaining > 0
        or_(
            models.Account.credits_remaining == None,
            models.Account.credits_remaining > 0
        )
    )

    if exclude_ids:
        query = query.filter(models.Account.id.notin_(exclude_ids))

    # Also exclude currently busy accounts
    if _busy_accounts:
        query = query.filter(models.Account.id.notin_(list(_busy_accounts)))

    accounts = query.all()

    # Filter by Rate Limit (30s cooldown)
    # Only pick accounts that are ready NOW
    accounts = [acc for acc in accounts if is_account_ready(acc.id)]

    if not accounts:
        return None

    # Prefer accounts that haven't been used recently
    accounts_sorted = sorted(accounts, key=lambda a: a.last_used or datetime.min)

    # Return the least recently used account
    return accounts_sorted[0]


async def mark_account_busy(account_id: int):
    """Mark an account as currently in use (thread-safe)"""
    async with _get_lock():
        _busy_accounts.add(account_id)
        logger.debug(f"Account #{account_id} marked as busy. Busy accounts: {_busy_accounts}")


async def mark_account_free(account_id: int):
    """Mark an account as no longer in use (thread-safe)"""
    async with _get_lock():
        _busy_accounts.discard(account_id)
        logger.debug(f"Account #{account_id} marked as free. Busy accounts: {_busy_accounts}")


# REMOVED: mark_account_quota_exhausted() - No more status column
# Account availability is purely based on credits_remaining

# REMOVED: mark_account_verification_needed() - No more status column
# If account needs verification, it should be handled in worker runtime

# REMOVED: reset_quota_exhausted_accounts() - No more status column
# Credits are checked/updated in real-time via API


def has_usable_account(db: Session, platform: str, specific_account_id: int = None) -> bool:
    """
    Check if there is at least one usable account with credits.
    No more status column - only credits matter.
    """
    from sqlalchemy import or_

    query = db.query(models.Account).filter(models.Account.platform == platform)

    # Only check credits
    # Allow if credits_remaining is None (not checked yet) OR credits_remaining > 0
    query = query.filter(or_(
        models.Account.credits_remaining == None,
        models.Account.credits_remaining > 0
    ))

    if specific_account_id:
        query = query.filter(models.Account.id == specific_account_id)

    return query.count() > 0


def get_busy_account_ids() -> Set[int]:
    """Get the set of currently busy account IDs"""
    return _busy_accounts.copy()


def force_reset():
    """Force clear all busy states and locks (Emergency use)"""
    global _busy_accounts, _account_file_locks
    logger.warning(f"[WARNING]  FORCE RESET: Clearing {_busy_accounts} from busy list.")
    _busy_accounts.clear()
    
    # Also clear lock instances to prevent deadlock if old worker is stuck holding one
    logger.warning(f"[WARNING]  FORCE RESET: Clearing {len(_account_file_locks)} account locks.")
    _account_file_locks.clear()
