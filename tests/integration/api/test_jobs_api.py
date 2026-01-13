"""
Integration Tests for Jobs API Endpoints

Tests the full HTTP request/response cycle for job operations
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, AsyncMock

from app.main import app
from app.api.dependencies import get_job_service, get_task_service
from app.core.services.job_service import JobService
from app.core.services.task_service import TaskService
from app.core.domain.job import (
    Job,
    JobId,
    JobSpec,
    JobProgress,
    JobResult,
    JobStatus
)
from datetime import datetime


@pytest.fixture
def mock_job_service():
    """Mock JobService for integration tests"""
    service = Mock(spec=JobService)
    service.create_job = AsyncMock()
    service.get_job = AsyncMock()
    service.list_jobs = AsyncMock()
    service.delete_job = AsyncMock()
    service.update_job = AsyncMock()
    return service


@pytest.fixture
def mock_task_service():
    """Mock TaskService for integration tests"""
    service = Mock(spec=TaskService)
    service.start_job = AsyncMock()
    service.retry_job = AsyncMock()
    service.cancel_job = AsyncMock()
    return service


@pytest.fixture
def client(mock_job_service, mock_task_service):
    """FastAPI TestClient with mocked services"""
    app.dependency_overrides[get_job_service] = lambda: mock_job_service
    app.dependency_overrides[get_task_service] = lambda: mock_task_service
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def sample_job():
    """Sample job for testing"""
    return Job(
        id=JobId(1),
        spec=JobSpec(
            prompt="A beautiful sunset",
            image_path=None,
            duration=5,
            aspect_ratio="16:9"
        ),
        progress=JobProgress(
            status=JobStatus.DRAFT,
            progress=0,
            max_retries=3
        ),
        result=JobResult(),
        account_id=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )


class TestCreateJob:
    """Test POST /jobs endpoint"""

    def test_create_job_success(self, client, mock_job_service, sample_job):
        """Test successfully creating a job"""
        mock_job_service.create_job.return_value = sample_job

        response = client.post(
            "/jobs/",
            json={
                "prompt": "A beautiful sunset",
                "duration": 5,
                "aspect_ratio": "16:9"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["prompt"] == "A beautiful sunset"
        assert data["duration"] == 5
        assert data["status"] == "draft"
        mock_job_service.create_job.assert_called_once()

    def test_create_job_with_image(self, client, mock_job_service, sample_job):
        """Test creating job with image"""
        mock_job_service.create_job.return_value = sample_job

        response = client.post(
            "/jobs/",
            json={
                "prompt": "Test prompt",
                "duration": 10,
                "aspect_ratio": "9:16",
                "image_path": "/path/to/image.png"
            }
        )

        assert response.status_code == 200
        mock_job_service.create_job.assert_called_once_with(
            prompt="Test prompt",
            duration=10,
            aspect_ratio="9:16",
            image_path="/path/to/image.png"
        )

    def test_create_job_default_values(self, client, mock_job_service, sample_job):
        """Test creating job with default values"""
        mock_job_service.create_job.return_value = sample_job

        response = client.post(
            "/jobs/",
            json={
                "prompt": "Test prompt"
                # duration and aspect_ratio should use defaults
            }
        )

        assert response.status_code == 200
        mock_job_service.create_job.assert_called_once_with(
            prompt="Test prompt",
            duration=5,  # default
            aspect_ratio="16:9",  # default
            image_path=None
        )

    def test_create_job_invalid_duration(self, client, mock_job_service):
        """Test creating job with invalid duration"""
        mock_job_service.create_job.side_effect = ValueError("Duration must be 5, 10, or 15 seconds")

        response = client.post(
            "/jobs/",
            json={
                "prompt": "Test prompt",
                "duration": 7,  # Invalid
                "aspect_ratio": "16:9"
            }
        )

        assert response.status_code == 400
        assert "duration" in response.json()["detail"].lower()

    def test_create_job_empty_prompt(self, client, mock_job_service):
        """Test creating job with empty prompt"""
        mock_job_service.create_job.side_effect = ValueError("Prompt cannot be empty")

        response = client.post(
            "/jobs/",
            json={
                "prompt": "",
                "duration": 5,
                "aspect_ratio": "16:9"
            }
        )

        assert response.status_code == 400

    def test_create_job_missing_prompt(self, client):
        """Test creating job without prompt"""
        response = client.post(
            "/jobs/",
            json={
                "duration": 5,
                "aspect_ratio": "16:9"
            }
        )

        assert response.status_code == 422  # Validation error


class TestGetJob:
    """Test GET /jobs/{job_id} endpoint"""

    def test_get_job_found(self, client, mock_job_service, sample_job):
        """Test getting job when found"""
        mock_job_service.get_job.return_value = sample_job

        response = client.get("/jobs/1")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["prompt"] == "A beautiful sunset"
        mock_job_service.get_job.assert_called_once_with(1)

    def test_get_job_not_found(self, client, mock_job_service):
        """Test getting job when not found"""
        mock_job_service.get_job.return_value = None

        response = client.get("/jobs/999")

        assert response.status_code == 404

    def test_get_job_invalid_id(self, client):
        """Test getting job with invalid ID"""
        response = client.get("/jobs/invalid")

        assert response.status_code == 422


class TestListJobs:
    """Test GET /jobs endpoint"""

    def test_list_jobs_empty(self, client, mock_job_service):
        """Test listing jobs when none exist"""
        mock_job_service.list_jobs.return_value = []

        response = client.get("/jobs/")

        assert response.status_code == 200
        assert response.json() == []

    def test_list_jobs_with_data(self, client, mock_job_service, sample_job):
        """Test listing jobs with data"""
        mock_job_service.list_jobs.return_value = [sample_job]

        response = client.get("/jobs/")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["prompt"] == "A beautiful sunset"

    def test_list_jobs_with_category_filter(self, client, mock_job_service, sample_job):
        """Test listing jobs with category filter"""
        mock_job_service.list_jobs.return_value = [sample_job]

        response = client.get("/jobs/?category=active")

        assert response.status_code == 200
        mock_job_service.list_jobs.assert_called_once_with(
            skip=0,
            limit=100,
            category="active"
        )

    def test_list_jobs_with_pagination(self, client, mock_job_service):
        """Test listing jobs with pagination"""
        mock_job_service.list_jobs.return_value = []

        response = client.get("/jobs/?skip=10&limit=20")

        assert response.status_code == 200
        mock_job_service.list_jobs.assert_called_once_with(
            skip=10,
            limit=20,
            category=None
        )


class TestUpdateJob:
    """Test PUT /jobs/{job_id} endpoint"""

    def test_update_job_prompt(self, client, mock_job_service, sample_job):
        """Test updating job prompt"""
        updated_job = Job(
            id=sample_job.id,
            spec=JobSpec(
                prompt="Updated prompt",
                image_path=None,
                duration=5,
                aspect_ratio="16:9"
            ),
            progress=sample_job.progress,
            result=sample_job.result,
            created_at=sample_job.created_at,
            updated_at=datetime.utcnow()
        )
        mock_job_service.update_job.return_value = updated_job

        response = client.put(
            "/jobs/1",
            json={"prompt": "Updated prompt"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["prompt"] == "Updated prompt"

    def test_update_job_not_found(self, client, mock_job_service):
        """Test updating non-existent job"""
        mock_job_service.update_job.side_effect = ValueError("Job not found")

        response = client.put(
            "/jobs/999",
            json={"prompt": "New prompt"}
        )

        assert response.status_code == 404


class TestDeleteJob:
    """Test DELETE /jobs/{job_id} endpoint"""

    def test_delete_job_success(self, client, mock_job_service):
        """Test successfully deleting job"""
        mock_job_service.delete_job.return_value = True

        response = client.delete("/jobs/1")

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True

    def test_delete_job_not_found(self, client, mock_job_service):
        """Test deleting non-existent job"""
        mock_job_service.delete_job.return_value = False

        response = client.delete("/jobs/999")

        assert response.status_code == 404


class TestStartJob:
    """Test POST /jobs/{job_id}/start endpoint"""

    def test_start_job_success(self, client, mock_task_service):
        """Test successfully starting a job"""
        mock_task_service.start_job.return_value = True

        response = client.post("/jobs/1/start")

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        mock_task_service.start_job.assert_called_once_with(1)

    def test_start_job_not_found(self, client, mock_task_service):
        """Test starting non-existent job"""
        mock_task_service.start_job.side_effect = ValueError("Job not found")

        response = client.post("/jobs/999/start")

        assert response.status_code == 404

    def test_start_job_already_running(self, client, mock_task_service):
        """Test starting already running job"""
        mock_task_service.start_job.side_effect = ValueError("Job already running")

        response = client.post("/jobs/1/start")

        assert response.status_code == 400


class TestRetryJob:
    """Test POST /jobs/{job_id}/retry endpoint"""

    def test_retry_job_success(self, client, mock_task_service):
        """Test successfully retrying a job"""
        mock_task_service.retry_job.return_value = True

        response = client.post("/jobs/1/retry")

        assert response.status_code == 200
        mock_task_service.retry_job.assert_called_once_with(1)

    def test_retry_job_not_found(self, client, mock_task_service):
        """Test retrying non-existent job"""
        mock_task_service.retry_job.side_effect = ValueError("Job not found")

        response = client.post("/jobs/999/retry")

        assert response.status_code == 404


class TestCancelJob:
    """Test POST /jobs/{job_id}/cancel endpoint"""

    def test_cancel_job_success(self, client, mock_task_service):
        """Test successfully canceling a job"""
        mock_task_service.cancel_job.return_value = True

        response = client.post("/jobs/1/cancel")

        assert response.status_code == 200

    def test_cancel_job_not_found(self, client, mock_task_service):
        """Test canceling non-existent job"""
        mock_task_service.cancel_job.side_effect = ValueError("Job not found")

        response = client.post("/jobs/999/cancel")

        assert response.status_code == 404


class TestJobAPISchema:
    """Test API schema validation"""

    def test_job_response_schema_fields(self, client, mock_job_service, sample_job):
        """Test JobResponse has all expected fields"""
        mock_job_service.get_job.return_value = sample_job

        response = client.get("/jobs/1")

        assert response.status_code == 200
        data = response.json()

        # Check all expected fields
        required_fields = [
            "id", "prompt", "duration", "aspect_ratio",
            "status", "progress", "retry_count",
            "created_at", "updated_at"
        ]
        for field in required_fields:
            assert field in data

    def test_job_create_schema_validation(self, client, mock_job_service, sample_job):
        """Test JobCreate schema validation"""
        mock_job_service.create_job.return_value = sample_job

        # Valid with all fields
        response = client.post(
            "/jobs/",
            json={
                "prompt": "Test",
                "duration": 10,
                "aspect_ratio": "9:16",
                "image_path": "/path/to/image.png"
            }
        )
        assert response.status_code == 200


class TestJobAPIIntegration:
    """Test full integration flows"""

    def test_create_and_start_job_flow(self, client, mock_job_service, mock_task_service, sample_job):
        """Test creating and starting a job"""
        # Create job
        mock_job_service.create_job.return_value = sample_job
        create_response = client.post(
            "/jobs/",
            json={
                "prompt": "Test prompt",
                "duration": 5,
                "aspect_ratio": "16:9"
            }
        )
        assert create_response.status_code == 200
        job_id = create_response.json()["id"]

        # Start job
        mock_task_service.start_job.return_value = True
        start_response = client.post(f"/jobs/{job_id}/start")
        assert start_response.status_code == 200

    def test_full_job_lifecycle(self, client, mock_job_service, mock_task_service, sample_job):
        """Test complete job lifecycle"""
        # Create
        mock_job_service.create_job.return_value = sample_job
        create_response = client.post(
            "/jobs/",
            json={"prompt": "Test", "duration": 5, "aspect_ratio": "16:9"}
        )
        assert create_response.status_code == 200
        job_id = create_response.json()["id"]

        # Get
        mock_job_service.get_job.return_value = sample_job
        get_response = client.get(f"/jobs/{job_id}")
        assert get_response.status_code == 200

        # Start
        mock_task_service.start_job.return_value = True
        start_response = client.post(f"/jobs/{job_id}/start")
        assert start_response.status_code == 200

        # List
        mock_job_service.list_jobs.return_value = [sample_job]
        list_response = client.get("/jobs/")
        assert list_response.status_code == 200

        # Delete
        mock_job_service.delete_job.return_value = True
        delete_response = client.delete(f"/jobs/{job_id}")
        assert delete_response.status_code == 200
