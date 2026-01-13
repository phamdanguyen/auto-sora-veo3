"""
Unit tests for AccountService

Tests business logic with mocked repositories
"""
import pytest
from unittest.mock import Mock, AsyncMock, MagicMock
from datetime import datetime, timedelta

from app.core.services.account_service import AccountService
from app.core.repositories.account_repo import AccountRepository
from app.core.drivers.factory import DriverFactory
from app.core.domain.account import (
    Account,
    AccountId,
    AccountAuth,
    AccountSession,
    AccountCredits
)


@pytest.fixture
def mock_account_repo():
    """Create mock AccountRepository"""
    repo = Mock(spec=AccountRepository)
    repo.get_by_email = AsyncMock(return_value=None)
    repo.get_by_id = AsyncMock(return_value=None)
    repo.get_all = AsyncMock(return_value=[])
    repo.create = AsyncMock()
    repo.update = AsyncMock()
    repo.delete = AsyncMock(return_value=True)
    repo.commit = Mock()
    repo.rollback = Mock()
    return repo


@pytest.fixture
def mock_driver_factory():
    """Create mock DriverFactory"""
    return Mock(spec=DriverFactory)


@pytest.fixture
def account_service(mock_account_repo, mock_driver_factory):
    """Create AccountService with mocked dependencies"""
    return AccountService(
        account_repo=mock_account_repo,
        driver_factory=mock_driver_factory
    )


@pytest.fixture
def sample_account():
    """Create a sample account"""
    return Account(
        id=AccountId(1),
        email="test@example.com",
        platform="sora",
        auth=AccountAuth(
            id=AccountId(1),
            email="test@example.com",
            password="encrypted_password",
            login_mode="auto"
        ),
        session=AccountSession(
            id=AccountId(1),
            cookies=None,
            access_token="token123",
            device_id=None,
            user_agent=None,
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


class TestAccountServiceCreate:
    """Test account creation"""

    @pytest.mark.asyncio
    async def test_create_account_success(self, account_service, mock_account_repo, sample_account):
        """Test successfully creating a new account"""
        mock_account_repo.get_by_email.return_value = None
        mock_account_repo.create.return_value = sample_account

        result = await account_service.create_account(
            platform="sora",
            email="test@example.com",
            password="password123",
            proxy=None
        )

        assert result is not None
        assert result.email == "test@example.com"
        mock_account_repo.create.assert_called_once()
        mock_account_repo.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_account_duplicate_email(self, account_service, mock_account_repo, sample_account):
        """Test creating account with duplicate email fails"""
        mock_account_repo.get_by_email.return_value = sample_account

        with pytest.raises(ValueError, match="already exists"):
            await account_service.create_account(
                platform="sora",
                email="test@example.com",
                password="password123"
            )

        mock_account_repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_account_with_proxy(self, account_service, mock_account_repo, sample_account):
        """Test creating account with proxy"""
        mock_account_repo.get_by_email.return_value = None
        mock_account_repo.create.return_value = sample_account

        result = await account_service.create_account(
            platform="sora",
            email="test@example.com",
            password="password123",
            proxy="http://proxy:8080"
        )

        assert result is not None
        mock_account_repo.create.assert_called_once()


class TestAccountServiceGet:
    """Test account retrieval"""

    @pytest.mark.asyncio
    async def test_get_account_found(self, account_service, mock_account_repo, sample_account):
        """Test getting account by ID when found"""
        mock_account_repo.get_by_id.return_value = sample_account

        result = await account_service.get_account(1)

        assert result is not None
        assert result.id.value == 1
        mock_account_repo.get_by_id.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_get_account_not_found(self, account_service, mock_account_repo):
        """Test getting account when not found"""
        mock_account_repo.get_by_id.return_value = None

        result = await account_service.get_account(999)

        assert result is None

    @pytest.mark.asyncio
    async def test_list_accounts(self, account_service, mock_account_repo, sample_account):
        """Test listing accounts"""
        mock_account_repo.get_all.return_value = [sample_account]

        result = await account_service.list_accounts(skip=0, limit=10)

        assert len(result) == 1
        assert result[0].id.value == 1
        mock_account_repo.get_all.assert_called_once_with(0, 10)


class TestAccountServiceDelete:
    """Test account deletion"""

    @pytest.mark.asyncio
    async def test_delete_account_success(self, account_service, mock_account_repo):
        """Test successfully deleting account"""
        mock_account_repo.delete.return_value = True

        result = await account_service.delete_account(1)

        assert result is True
        mock_account_repo.delete.assert_called_once_with(1)
        mock_account_repo.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_account_not_found(self, account_service, mock_account_repo):
        """Test deleting non-existent account"""
        mock_account_repo.delete.return_value = False

        result = await account_service.delete_account(999)

        assert result is False
        mock_account_repo.commit.assert_not_called()


class TestAccountServiceCredits:
    """Test credits management"""

    @pytest.mark.asyncio
    async def test_refresh_credits_no_account(self, account_service, mock_account_repo):
        """Test refreshing credits for non-existent account"""
        mock_account_repo.get_by_id.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await account_service.refresh_credits(999)

    @pytest.mark.asyncio
    async def test_refresh_credits_no_token(self, account_service, mock_account_repo, sample_account):
        """Test refreshing credits when no access token"""
        account_no_token = Account(
            id=sample_account.id,
            email=sample_account.email,
            platform=sample_account.platform,
            auth=sample_account.auth,
            session=AccountSession(
                id=AccountId(1),
                cookies=None,
                access_token=None,  # No token
                device_id=None,
                user_agent=None,
                token_status="pending"
            ),
            credits=sample_account.credits
        )
        mock_account_repo.get_by_id.return_value = account_no_token

        result = await account_service.refresh_credits(1)

        assert result is None
