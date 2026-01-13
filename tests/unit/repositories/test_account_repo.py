"""
Unit tests for AccountRepository

Tests all account repository methods with mocked database
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch
from sqlalchemy.orm import Session

from app.core.repositories.account_repo import AccountRepository
from app.core.domain.account import (
    Account,
    AccountId,
    AccountAuth,
    AccountSession,
    AccountCredits
)
from app.models import Account as AccountModel


@pytest.fixture
def mock_session():
    """Create a mock database session"""
    return Mock(spec=Session)


@pytest.fixture
def account_repo(mock_session):
    """Create AccountRepository with mock session"""
    repo = AccountRepository(mock_session)
    repo.flush = Mock()  # Mock the flush method
    return repo


@pytest.fixture
def sample_orm_account():
    """Create a sample ORM account"""
    account = Mock(spec=AccountModel)
    account.id = 1
    account.email = "test@example.com"
    account.platform = "sora"
    account.password = "encrypted_password"
    account.login_mode = "auto"
    account.cookies = {"session": "abc"}
    account.access_token = "token123"
    account.device_id = "device123"
    account.user_agent = "Mozilla/5.0"
    account.token_status = "valid"
    account.token_captured_at = datetime.utcnow()
    account.token_expires_at = datetime.utcnow() + timedelta(hours=1)
    account.credits_remaining = 10
    account.credits_last_checked = datetime.utcnow()
    account.credits_reset_at = None
    account.last_used = None
    account.proxy = None
    return account


@pytest.fixture
def sample_domain_account():
    """Create a sample domain account"""
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
            cookies={"session": "abc"},
            access_token="token123",
            device_id="device123",
            user_agent="Mozilla/5.0",
            token_status="valid",
            token_captured_at=datetime.utcnow(),
            token_expires_at=datetime.utcnow() + timedelta(hours=1)
        ),
        credits=AccountCredits(
            id=AccountId(1),
            credits_remaining=10,
            credits_last_checked=datetime.utcnow(),
            credits_reset_at=None
        )
    )


class TestAccountRepositoryGet:
    """Test get operations"""

    @pytest.mark.asyncio
    async def test_get_by_id_found(self, account_repo, mock_session, sample_orm_account):
        """Test getting account by ID when found"""
        mock_query = Mock()
        mock_session.query.return_value = mock_query
        mock_query.filter_by.return_value.first.return_value = sample_orm_account

        result = await account_repo.get_by_id(1)

        assert result is not None
        assert result.id.value == 1
        assert result.email == "test@example.com"
        mock_session.query.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, account_repo, mock_session):
        """Test getting account by ID when not found"""
        mock_query = Mock()
        mock_session.query.return_value = mock_query
        mock_query.filter_by.return_value.first.return_value = None

        result = await account_repo.get_by_id(999)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_email_found(self, account_repo, mock_session, sample_orm_account):
        """Test getting account by email when found"""
        mock_query = Mock()
        mock_session.query.return_value = mock_query
        mock_query.filter_by.return_value.first.return_value = sample_orm_account

        result = await account_repo.get_by_email("test@example.com")

        assert result is not None
        assert result.email == "test@example.com"

    @pytest.mark.asyncio
    async def test_get_by_email_not_found(self, account_repo, mock_session):
        """Test getting account by email when not found"""
        mock_query = Mock()
        mock_session.query.return_value = mock_query
        mock_query.filter_by.return_value.first.return_value = None

        result = await account_repo.get_by_email("notfound@example.com")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_all(self, account_repo, mock_session, sample_orm_account):
        """Test getting all accounts"""
        mock_query = Mock()
        mock_session.query.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [sample_orm_account]

        result = await account_repo.get_all(skip=0, limit=10)

        assert len(result) == 1
        assert result[0].id.value == 1

    @pytest.mark.asyncio
    async def test_get_available_accounts(self, account_repo, mock_session, sample_orm_account):
        """Test getting available accounts"""
        mock_query = Mock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [sample_orm_account]

        result = await account_repo.get_available_accounts(platform="sora")

        assert len(result) == 1
        assert result[0].platform == "sora"

    @pytest.mark.asyncio
    async def test_get_available_accounts_with_exclusions(
        self, account_repo, mock_session, sample_orm_account
    ):
        """Test getting available accounts with exclusions"""
        mock_query = Mock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []

        result = await account_repo.get_available_accounts(
            platform="sora",
            exclude_ids=[1, 2, 3]
        )

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_get_credits(self, account_repo, mock_session, sample_orm_account):
        """Test getting credits info only"""
        mock_query = Mock()
        mock_session.query.return_value = mock_query
        mock_query.filter_by.return_value.first.return_value = sample_orm_account

        result = await account_repo.get_credits(1)

        assert result is not None
        assert isinstance(result, AccountCredits)
        assert result.credits_remaining == 10

    @pytest.mark.asyncio
    async def test_get_credits_not_found(self, account_repo, mock_session):
        """Test getting credits when account not found"""
        mock_query = Mock()
        mock_session.query.return_value = mock_query
        mock_query.filter_by.return_value.first.return_value = None

        result = await account_repo.get_credits(999)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_session(self, account_repo, mock_session, sample_orm_account):
        """Test getting session info only"""
        mock_query = Mock()
        mock_session.query.return_value = mock_query
        mock_query.filter_by.return_value.first.return_value = sample_orm_account

        result = await account_repo.get_session(1)

        assert result is not None
        assert isinstance(result, AccountSession)
        assert result.access_token == "token123"

    @pytest.mark.asyncio
    async def test_get_session_not_found(self, account_repo, mock_session):
        """Test getting session when account not found"""
        mock_query = Mock()
        mock_session.query.return_value = mock_query
        mock_query.filter_by.return_value.first.return_value = None

        result = await account_repo.get_session(999)

        assert result is None


class TestAccountRepositoryCreate:
    """Test create operations"""

    @pytest.mark.asyncio
    async def test_create_account(self, account_repo, mock_session, sample_domain_account):
        """Test creating a new account"""
        mock_session.add = Mock()
        mock_session.flush = Mock()

        # Mock the AccountModel creation
        with patch('app.core.repositories.account_repo.AccountModel') as MockAccountModel:
            mock_orm = Mock(spec=AccountModel)
            mock_orm.id = 1
            mock_orm.email = sample_domain_account.email
            mock_orm.platform = sample_domain_account.platform
            mock_orm.password = sample_domain_account.auth.password
            mock_orm.login_mode = sample_domain_account.auth.login_mode
            mock_orm.cookies = None
            mock_orm.access_token = None
            mock_orm.device_id = None
            mock_orm.user_agent = None
            mock_orm.token_status = "pending"
            mock_orm.token_captured_at = None
            mock_orm.token_expires_at = None
            mock_orm.credits_remaining = None
            mock_orm.credits_last_checked = None
            mock_orm.credits_reset_at = None
            mock_orm.last_used = None
            mock_orm.proxy = None

            MockAccountModel.return_value = mock_orm

            result = await account_repo.create(sample_domain_account)

            assert result is not None
            assert result.email == sample_domain_account.email
            mock_session.add.assert_called_once()
            account_repo.flush.assert_called_once()


class TestAccountRepositoryUpdate:
    """Test update operations"""

    @pytest.mark.asyncio
    async def test_update_account(self, account_repo, mock_session, sample_orm_account, sample_domain_account):
        """Test updating an account"""
        mock_query = Mock()
        mock_session.query.return_value = mock_query
        mock_query.filter_by.return_value.first.return_value = sample_orm_account
        mock_session.flush = Mock()

        result = await account_repo.update(sample_domain_account)

        assert result is not None
        account_repo.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_account_not_found(self, account_repo, mock_session, sample_domain_account):
        """Test updating non-existent account raises error"""
        mock_query = Mock()
        mock_session.query.return_value = mock_query
        mock_query.filter_by.return_value.first.return_value = None

        with pytest.raises(ValueError, match="Account .* not found"):
            await account_repo.update(sample_domain_account)

    @pytest.mark.asyncio
    async def test_update_credits(self, account_repo, mock_session, sample_orm_account):
        """Test updating credits only"""
        mock_query = Mock()
        mock_session.query.return_value = mock_query
        mock_query.filter_by.return_value.first.return_value = sample_orm_account
        mock_session.flush = Mock()

        new_credits = AccountCredits(
            id=AccountId(1),
            credits_remaining=5,
            credits_last_checked=datetime.utcnow(),
            credits_reset_at=None
        )

        result = await account_repo.update_credits(1, new_credits)

        assert result is not None
        assert sample_orm_account.credits_remaining == 5
        account_repo.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_session(self, account_repo, mock_session, sample_orm_account):
        """Test updating session only"""
        mock_query = Mock()
        mock_session.query.return_value = mock_query
        mock_query.filter_by.return_value.first.return_value = sample_orm_account
        mock_session.flush = Mock()

        new_session = AccountSession(
            id=AccountId(1),
            cookies={"new": "cookies"},
            access_token="new_token",
            device_id="new_device",
            user_agent="New Agent",
            token_status="valid"
        )

        result = await account_repo.update_session(1, new_session)

        assert result is not None
        assert sample_orm_account.access_token == "new_token"
        account_repo.flush.assert_called_once()


class TestAccountRepositoryDelete:
    """Test delete operations"""

    @pytest.mark.asyncio
    async def test_delete_account(self, account_repo, mock_session, sample_orm_account):
        """Test deleting an account"""
        mock_query = Mock()
        mock_session.query.return_value = mock_query
        mock_query.filter_by.return_value.first.return_value = sample_orm_account
        mock_session.delete = Mock()

        result = await account_repo.delete(1)

        assert result is True
        mock_session.delete.assert_called_once_with(sample_orm_account)

    @pytest.mark.asyncio
    async def test_delete_account_not_found(self, account_repo, mock_session):
        """Test deleting non-existent account"""
        mock_query = Mock()
        mock_session.query.return_value = mock_query
        mock_query.filter_by.return_value.first.return_value = None

        result = await account_repo.delete(999)

        assert result is False


class TestAccountRepositoryStats:
    """Test statistics operations"""

    @pytest.mark.asyncio
    async def test_count_by_platform(self, account_repo, mock_session):
        """Test counting accounts by platform"""
        mock_query = Mock()
        mock_session.query.return_value = mock_query
        mock_query.filter_by.return_value.count.return_value = 5

        result = await account_repo.count_by_platform("sora")

        assert result == 5


class TestAccountRepositorySessionMethods:
    """Test session management methods"""

    def test_commit(self, account_repo, mock_session):
        """Test committing changes"""
        mock_session.commit = Mock()

        account_repo.commit()

        mock_session.commit.assert_called_once()

    def test_rollback(self, account_repo, mock_session):
        """Test rolling back changes"""
        mock_session.rollback = Mock()

        account_repo.rollback()

        mock_session.rollback.assert_called_once()

    def test_flush(self, account_repo):
        """Test flushing changes"""
        account_repo.flush()

        account_repo.flush.assert_called_once()
