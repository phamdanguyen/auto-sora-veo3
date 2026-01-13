"""
Unit tests for Account Domain Models

Tests:
- AccountId validation
- AccountAuth validation and methods
- AccountSession validation and methods
- AccountCredits validation and methods
- Account aggregate root
"""
import pytest
from datetime import datetime, timedelta
from app.core.domain.account import (
    AccountId,
    AccountAuth,
    AccountSession,
    AccountCredits,
    Account
)


class TestAccountId:
    """Test AccountId value object"""

    def test_valid_account_id(self):
        """Test creating valid AccountId"""
        account_id = AccountId(value=1)
        assert account_id.value == 1
        assert str(account_id) == "1"

    def test_account_id_zero_allowed(self):
        """Test AccountId can be zero for new accounts"""
        account_id = AccountId(value=0)
        assert account_id.value == 0

    def test_account_id_cannot_be_negative(self):
        """Test AccountId cannot be negative"""
        with pytest.raises(ValueError, match="Account ID cannot be negative"):
            AccountId(value=-1)

    def test_account_id_immutable(self):
        """Test AccountId is immutable"""
        account_id = AccountId(value=1)
        with pytest.raises(Exception):  # FrozenInstanceError
            account_id.value = 2


class TestAccountAuth:
    """Test AccountAuth value object"""

    def test_valid_account_auth_auto(self):
        """Test creating valid AccountAuth with auto login"""
        auth = AccountAuth(
            id=AccountId(1),
            email="test@example.com",
            password="encrypted_password",
            login_mode="auto"
        )
        assert auth.email == "test@example.com"
        assert auth.login_mode == "auto"
        assert not auth.is_manual_login()

    def test_valid_account_auth_manual(self):
        """Test creating valid AccountAuth with manual login"""
        auth = AccountAuth(
            id=AccountId(1),
            email="test@example.com",
            password="encrypted_password",
            login_mode="manual"
        )
        assert auth.login_mode == "manual"
        assert auth.is_manual_login()

    def test_email_cannot_be_empty(self):
        """Test email validation"""
        with pytest.raises(ValueError, match="Email cannot be empty"):
            AccountAuth(
                id=AccountId(1),
                email="",
                password="password",
                login_mode="auto"
            )

    def test_invalid_login_mode(self):
        """Test login_mode validation"""
        with pytest.raises(ValueError, match="login_mode must be 'auto' or 'manual'"):
            AccountAuth(
                id=AccountId(1),
                email="test@example.com",
                password="password",
                login_mode="invalid"
            )

    def test_account_auth_immutable(self):
        """Test AccountAuth is immutable"""
        auth = AccountAuth(
            id=AccountId(1),
            email="test@example.com",
            password="password",
            login_mode="auto"
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            auth.email = "new@example.com"


class TestAccountSession:
    """Test AccountSession value object"""

    def test_valid_session_pending(self):
        """Test creating session with pending token"""
        session = AccountSession(
            id=AccountId(1),
            cookies=None,
            access_token=None,
            device_id=None,
            user_agent=None,
            token_status="pending"
        )
        assert session.token_status == "pending"
        assert not session.has_valid_token()

    def test_valid_session_with_token(self):
        """Test creating session with valid token"""
        future = datetime.utcnow() + timedelta(hours=1)
        session = AccountSession(
            id=AccountId(1),
            cookies={"session": "abc123"},
            access_token="token123",
            device_id="device123",
            user_agent="Mozilla/5.0",
            token_status="valid",
            token_captured_at=datetime.utcnow(),
            token_expires_at=future
        )
        assert session.has_valid_token()
        assert not session.is_expired()

    def test_session_expired_token(self):
        """Test session with expired token"""
        past = datetime.utcnow() - timedelta(hours=1)
        session = AccountSession(
            id=AccountId(1),
            cookies=None,
            access_token="token123",
            device_id=None,
            user_agent=None,
            token_status="valid",
            token_expires_at=past
        )
        assert not session.has_valid_token()
        assert session.is_expired()

    def test_session_no_expiry(self):
        """Test session with no expiry time"""
        session = AccountSession(
            id=AccountId(1),
            cookies=None,
            access_token="token123",
            device_id=None,
            user_agent=None,
            token_status="valid",
            token_expires_at=None
        )
        assert session.has_valid_token()
        assert not session.is_expired()

    def test_invalid_token_status(self):
        """Test token_status validation"""
        with pytest.raises(ValueError, match="token_status must be"):
            AccountSession(
                id=AccountId(1),
                cookies=None,
                access_token=None,
                device_id=None,
                user_agent=None,
                token_status="invalid_status"
            )


class TestAccountCredits:
    """Test AccountCredits value object"""

    def test_credits_not_checked_yet(self):
        """Test credits when not checked yet"""
        credits = AccountCredits(
            id=AccountId(1),
            credits_remaining=None,
            credits_last_checked=None,
            credits_reset_at=None
        )
        assert credits.has_credits()  # Assume has credits if not checked
        assert not credits.is_exhausted()
        assert credits.needs_refresh()

    def test_credits_available(self):
        """Test when credits are available"""
        credits = AccountCredits(
            id=AccountId(1),
            credits_remaining=10,
            credits_last_checked=datetime.utcnow(),
            credits_reset_at=None
        )
        assert credits.has_credits()
        assert not credits.is_exhausted()

    def test_credits_exhausted(self):
        """Test when credits are exhausted"""
        credits = AccountCredits(
            id=AccountId(1),
            credits_remaining=0,
            credits_last_checked=datetime.utcnow(),
            credits_reset_at=None
        )
        assert not credits.has_credits()
        assert credits.is_exhausted()

    def test_credits_needs_refresh_old_data(self):
        """Test credits need refresh with old data"""
        old_time = datetime.utcnow() - timedelta(hours=2)
        credits = AccountCredits(
            id=AccountId(1),
            credits_remaining=10,
            credits_last_checked=old_time,
            credits_reset_at=None
        )
        assert credits.needs_refresh(max_age_minutes=60)

    def test_credits_no_refresh_needed_recent_data(self):
        """Test credits don't need refresh with recent data"""
        recent_time = datetime.utcnow() - timedelta(minutes=30)
        credits = AccountCredits(
            id=AccountId(1),
            credits_remaining=10,
            credits_last_checked=recent_time,
            credits_reset_at=None
        )
        assert not credits.needs_refresh(max_age_minutes=60)


class TestAccount:
    """Test Account aggregate root"""

    @pytest.fixture
    def valid_account(self):
        """Create a valid account for testing"""
        return Account(
            id=AccountId(1),
            email="test@example.com",
            platform="sora",
            auth=AccountAuth(
                id=AccountId(1),
                email="test@example.com",
                password="encrypted",
                login_mode="auto"
            ),
            session=AccountSession(
                id=AccountId(1),
                cookies={"session": "abc"},
                access_token="token123",
                device_id="device123",
                user_agent="Mozilla",
                token_status="valid",
                token_expires_at=datetime.utcnow() + timedelta(hours=1)
            ),
            credits=AccountCredits(
                id=AccountId(1),
                credits_remaining=10,
                credits_last_checked=datetime.utcnow(),
                credits_reset_at=None
            )
        )

    def test_valid_account_creation(self, valid_account):
        """Test creating a valid account"""
        assert valid_account.id.value == 1
        assert valid_account.email == "test@example.com"
        assert valid_account.platform == "sora"

    def test_account_email_cannot_be_empty(self):
        """Test email validation"""
        with pytest.raises(ValueError, match="Email cannot be empty"):
            Account(
                id=AccountId(1),
                email="",
                platform="sora",
                auth=AccountAuth(
                    id=AccountId(1),
                    email="test@example.com",
                    password="password",
                    login_mode="auto"
                ),
                session=AccountSession(
                    id=AccountId(1),
                    cookies=None,
                    access_token=None,
                    device_id=None,
                    user_agent=None,
                    token_status="pending"
                ),
                credits=AccountCredits(
                    id=AccountId(1),
                    credits_remaining=None,
                    credits_last_checked=None,
                    credits_reset_at=None
                )
            )

    def test_account_platform_cannot_be_empty(self, valid_account):
        """Test platform validation"""
        with pytest.raises(ValueError, match="Platform cannot be empty"):
            Account(
                id=valid_account.id,
                email=valid_account.email,
                platform="",
                auth=valid_account.auth,
                session=valid_account.session,
                credits=valid_account.credits
            )

    def test_account_available_for_job(self, valid_account):
        """Test account is available for job"""
        assert valid_account.is_available_for_job()

    def test_account_not_available_no_credits(self, valid_account):
        """Test account not available when no credits"""
        account = Account(
            id=valid_account.id,
            email=valid_account.email,
            platform=valid_account.platform,
            auth=valid_account.auth,
            session=valid_account.session,
            credits=AccountCredits(
                id=AccountId(1),
                credits_remaining=0,
                credits_last_checked=datetime.utcnow(),
                credits_reset_at=None
            )
        )
        assert not account.is_available_for_job()

    def test_account_not_available_expired_token(self, valid_account):
        """Test account not available with expired token"""
        account = Account(
            id=valid_account.id,
            email=valid_account.email,
            platform=valid_account.platform,
            auth=valid_account.auth,
            session=AccountSession(
                id=AccountId(1),
                cookies=None,
                access_token="token",
                device_id=None,
                user_agent=None,
                token_status="expired",
                token_expires_at=datetime.utcnow() - timedelta(hours=1)
            ),
            credits=valid_account.credits
        )
        assert not account.is_available_for_job()

    def test_manual_login_account_available_without_token(self, valid_account):
        """Test manual login account available even without valid token"""
        account = Account(
            id=valid_account.id,
            email=valid_account.email,
            platform=valid_account.platform,
            auth=AccountAuth(
                id=AccountId(1),
                email="test@example.com",
                password="password",
                login_mode="manual"
            ),
            session=AccountSession(
                id=AccountId(1),
                cookies=None,
                access_token=None,
                device_id=None,
                user_agent=None,
                token_status="pending"
            ),
            credits=valid_account.credits
        )
        assert account.is_available_for_job()
        assert not account.needs_login()

    def test_account_needs_login(self, valid_account):
        """Test account needs login check"""
        account = Account(
            id=valid_account.id,
            email=valid_account.email,
            platform=valid_account.platform,
            auth=AccountAuth(
                id=AccountId(1),
                email="test@example.com",
                password="password",
                login_mode="auto"
            ),
            session=AccountSession(
                id=AccountId(1),
                cookies=None,
                access_token=None,
                device_id=None,
                user_agent=None,
                token_status="pending"
            ),
            credits=valid_account.credits
        )
        assert account.needs_login()

    def test_account_str_repr(self, valid_account):
        """Test string representation"""
        str_repr = str(valid_account)
        assert "Account" in str_repr
        assert "test@example.com" in str_repr
        assert "sora" in str_repr
