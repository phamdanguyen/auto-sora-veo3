"""
Integration Tests for Accounts API Endpoints

Tests the full HTTP request/response cycle với real FastAPI app
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, AsyncMock, patch

from app.main import app
from app.api.dependencies import get_account_service
from app.core.services.account_service import AccountService
from app.core.domain.account import (
    Account,
    AccountId,
    AccountAuth,
    AccountSession,
    AccountCredits
)
from datetime import datetime, timedelta


@pytest.fixture
def mock_account_service():
    """Mock AccountService for integration tests"""
    service = Mock(spec=AccountService)
    service.create_account = AsyncMock()
    service.get_account = AsyncMock()
    service.list_accounts = AsyncMock()
    service.delete_account = AsyncMock()
    service.refresh_credits = AsyncMock()
    return service


@pytest.fixture
def client(mock_account_service):
    """FastAPI TestClient with mocked service"""
    app.dependency_overrides[get_account_service] = lambda: mock_account_service
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def sample_account():
    """Sample account for testing"""
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


class TestCreateAccount:
    """Test POST /accounts endpoint"""

    def test_create_account_success(self, client, mock_account_service, sample_account):
        """Test successfully creating an account"""
        mock_account_service.create_account.return_value = sample_account

        response = client.post(
            "/accounts/",
            json={
                "platform": "sora",
                "email": "test@example.com",
                "password": "password123",
                "proxy": None
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "test@example.com"
        assert data["platform"] == "sora"
        assert data["id"] == 1
        mock_account_service.create_account.assert_called_once()

    def test_create_account_duplicate_email(self, client, mock_account_service):
        """Test creating account with duplicate email"""
        mock_account_service.create_account.side_effect = ValueError("Email already exists")

        response = client.post(
            "/accounts/",
            json={
                "platform": "sora",
                "email": "duplicate@example.com",
                "password": "password123"
            }
        )

        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    def test_create_account_with_proxy(self, client, mock_account_service, sample_account):
        """Test creating account with proxy"""
        mock_account_service.create_account.return_value = sample_account

        response = client.post(
            "/accounts/",
            json={
                "platform": "sora",
                "email": "test@example.com",
                "password": "password123",
                "proxy": "http://proxy:8080"
            }
        )

        assert response.status_code == 200
        mock_account_service.create_account.assert_called_once_with(
            platform="sora",
            email="test@example.com",
            password="password123",
            proxy="http://proxy:8080"
        )

    def test_create_account_missing_fields(self, client):
        """Test creating account with missing required fields"""
        response = client.post(
            "/accounts/",
            json={
                "platform": "sora",
                # Missing email and password
            }
        )

        assert response.status_code == 422  # Validation error

    def test_create_account_invalid_json(self, client):
        """Test creating account with invalid JSON"""
        response = client.post(
            "/accounts/",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 422


class TestGetAccount:
    """Test GET /accounts/{account_id} endpoint"""

    def test_get_account_found(self, client, mock_account_service, sample_account):
        """Test getting account when found"""
        mock_account_service.get_account.return_value = sample_account

        response = client.get("/accounts/1")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["email"] == "test@example.com"
        mock_account_service.get_account.assert_called_once_with(1)

    def test_get_account_not_found(self, client, mock_account_service):
        """Test getting account when not found"""
        mock_account_service.get_account.return_value = None

        response = client.get("/accounts/999")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_account_invalid_id(self, client):
        """Test getting account with invalid ID"""
        response = client.get("/accounts/invalid")

        assert response.status_code == 422  # Validation error


class TestListAccounts:
    """Test GET /accounts endpoint"""

    def test_list_accounts_empty(self, client, mock_account_service):
        """Test listing accounts when none exist"""
        mock_account_service.list_accounts.return_value = []

        response = client.get("/accounts/")

        assert response.status_code == 200
        data = response.json()
        assert data == []

    def test_list_accounts_with_data(self, client, mock_account_service, sample_account):
        """Test listing accounts with data"""
        mock_account_service.list_accounts.return_value = [sample_account]

        response = client.get("/accounts/")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["email"] == "test@example.com"

    def test_list_accounts_with_pagination(self, client, mock_account_service, sample_account):
        """Test listing accounts with pagination"""
        mock_account_service.list_accounts.return_value = [sample_account]

        response = client.get("/accounts/?skip=10&limit=20")

        assert response.status_code == 200
        mock_account_service.list_accounts.assert_called_once_with(skip=10, limit=20)

    def test_list_accounts_default_pagination(self, client, mock_account_service):
        """Test listing accounts with default pagination"""
        mock_account_service.list_accounts.return_value = []

        response = client.get("/accounts/")

        assert response.status_code == 200
        mock_account_service.list_accounts.assert_called_once_with(skip=0, limit=100)


class TestDeleteAccount:
    """Test DELETE /accounts/{account_id} endpoint"""

    def test_delete_account_success(self, client, mock_account_service):
        """Test successfully deleting account"""
        mock_account_service.delete_account.return_value = True

        response = client.delete("/accounts/1")

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        mock_account_service.delete_account.assert_called_once_with(1)

    def test_delete_account_not_found(self, client, mock_account_service):
        """Test deleting non-existent account"""
        mock_account_service.delete_account.return_value = False

        response = client.delete("/accounts/999")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_delete_account_invalid_id(self, client):
        """Test deleting account with invalid ID"""
        response = client.delete("/accounts/invalid")

        assert response.status_code == 422  # Validation error


class TestRefreshCredits:
    """Test POST /accounts/{account_id}/refresh-credits endpoint"""

    def test_refresh_credits_success(self, client, mock_account_service):
        """Test successfully refreshing credits"""
        mock_credits = AccountCredits(
            id=AccountId(1),
            credits_remaining=15,
            credits_last_checked=datetime.utcnow(),
            credits_reset_at=None
        )
        mock_account_service.refresh_credits.return_value = mock_credits

        response = client.post("/accounts/1/refresh-credits")

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["credits_remaining"] == 15
        mock_account_service.refresh_credits.assert_called_once_with(1)

    def test_refresh_credits_not_found(self, client, mock_account_service):
        """Test refreshing credits for non-existent account"""
        mock_account_service.refresh_credits.side_effect = ValueError("Account not found")

        response = client.post("/accounts/999/refresh-credits")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_refresh_credits_no_token(self, client, mock_account_service):
        """Test refreshing credits when account has no token"""
        mock_account_service.refresh_credits.return_value = None

        response = client.post("/accounts/1/refresh-credits")

        assert response.status_code == 400
        assert "no access token" in response.json()["detail"].lower()


class TestAccountAPISchema:
    """Test API schema validation and serialization"""

    def test_account_response_schema(self, client, mock_account_service, sample_account):
        """Test AccountResponse schema fields"""
        mock_account_service.get_account.return_value = sample_account

        response = client.get("/accounts/1")

        assert response.status_code == 200
        data = response.json()

        # Check all expected fields
        assert "id" in data
        assert "email" in data
        assert "platform" in data
        assert "proxy" in data
        assert "credits_remaining" in data
        assert "token_status" in data
        assert "login_mode" in data

    def test_account_create_schema_validation(self, client):
        """Test AccountCreate schema validation"""
        # Test with all fields
        response = client.post(
            "/accounts/",
            json={
                "platform": "sora",
                "email": "test@example.com",
                "password": "password123",
                "proxy": "http://proxy:8080"
            }
        )
        # Will fail service call but schema is valid
        assert response.status_code in [200, 400, 500]

        # Test with optional proxy omitted
        response = client.post(
            "/accounts/",
            json={
                "platform": "sora",
                "email": "test@example.com",
                "password": "password123"
            }
        )
        assert response.status_code in [200, 400, 500]


class TestAccountAPIErrorHandling:
    """Test error handling in accounts API"""

    def test_internal_server_error(self, client, mock_account_service):
        """Test handling of unexpected errors"""
        mock_account_service.create_account.side_effect = Exception("Unexpected error")

        response = client.post(
            "/accounts/",
            json={
                "platform": "sora",
                "email": "test@example.com",
                "password": "password123"
            }
        )

        assert response.status_code == 500

    def test_validation_error_empty_string(self, client):
        """Test validation for empty strings"""
        response = client.post(
            "/accounts/",
            json={
                "platform": "",  # Empty platform
                "email": "test@example.com",
                "password": "password123"
            }
        )

        assert response.status_code in [400, 422]


class TestAccountAPIIntegration:
    """Test full integration flows"""

    def test_create_and_get_account_flow(self, client, mock_account_service, sample_account):
        """Test creating and then getting an account"""
        # Create account
        mock_account_service.create_account.return_value = sample_account
        create_response = client.post(
            "/accounts/",
            json={
                "platform": "sora",
                "email": "test@example.com",
                "password": "password123"
            }
        )
        assert create_response.status_code == 200
        created_id = create_response.json()["id"]

        # Get the created account
        mock_account_service.get_account.return_value = sample_account
        get_response = client.get(f"/accounts/{created_id}")
        assert get_response.status_code == 200
        assert get_response.json()["id"] == created_id

    def test_create_list_delete_flow(self, client, mock_account_service, sample_account):
        """Test full CRUD flow"""
        # Create
        mock_account_service.create_account.return_value = sample_account
        create_response = client.post(
            "/accounts/",
            json={
                "platform": "sora",
                "email": "test@example.com",
                "password": "password123"
            }
        )
        assert create_response.status_code == 200
        account_id = create_response.json()["id"]

        # List
        mock_account_service.list_accounts.return_value = [sample_account]
        list_response = client.get("/accounts/")
        assert list_response.status_code == 200
        assert len(list_response.json()) == 1

        # Delete
        mock_account_service.delete_account.return_value = True
        delete_response = client.delete(f"/accounts/{account_id}")
        assert delete_response.status_code == 200
