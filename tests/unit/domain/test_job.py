"""
Unit tests for Job Domain Models

Tests:
- JobId validation
- JobStatus enum
- JobSpec validation and methods
- JobProgress validation and methods
- JobResult validation and methods
- Job aggregate root
"""
import pytest
from datetime import datetime
from app.core.domain.job import (
    JobId,
    JobStatus,
    JobSpec,
    JobProgress,
    JobResult,
    Job
)


class TestJobId:
    """Test JobId value object"""

    def test_valid_job_id(self):
        """Test creating valid JobId"""
        job_id = JobId(value=1)
        assert job_id.value == 1
        assert str(job_id) == "1"

    def test_job_id_zero_allowed(self):
        """Test JobId can be zero for new jobs"""
        job_id = JobId(value=0)
        assert job_id.value == 0

    def test_job_id_cannot_be_negative(self):
        """Test JobId cannot be negative"""
        with pytest.raises(ValueError, match="Job ID cannot be negative"):
            JobId(value=-1)

    def test_job_id_immutable(self):
        """Test JobId is immutable"""
        job_id = JobId(value=1)
        with pytest.raises(Exception):  # FrozenInstanceError
            job_id.value = 2


class TestJobStatus:
    """Test JobStatus enum"""

    def test_terminal_statuses(self):
        """Test terminal status check"""
        assert JobStatus.DONE.is_terminal()
        assert JobStatus.FAILED.is_terminal()
        assert JobStatus.CANCELLED.is_terminal()
        assert not JobStatus.PENDING.is_terminal()
        assert not JobStatus.PROCESSING.is_terminal()

    def test_active_statuses(self):
        """Test active status check"""
        assert JobStatus.PENDING.is_active()
        assert JobStatus.PROCESSING.is_active()
        assert JobStatus.SENT_PROMPT.is_active()
        assert JobStatus.GENERATING.is_active()
        assert JobStatus.DOWNLOAD.is_active()
        assert not JobStatus.DONE.is_active()
        assert not JobStatus.FAILED.is_active()


class TestJobSpec:
    """Test JobSpec value object"""

    def test_valid_job_spec(self):
        """Test creating valid JobSpec"""
        spec = JobSpec(
            prompt="A beautiful sunset",
            image_path=None,
            duration=5,
            aspect_ratio="16:9"
        )
        assert spec.prompt == "A beautiful sunset"
        assert spec.duration == 5
        assert spec.aspect_ratio == "16:9"
        assert spec.get_orientation() == "landscape"
        assert spec.get_n_frames() == 150  # 5 * 30fps

    def test_prompt_cannot_be_empty(self):
        """Test prompt validation"""
        with pytest.raises(ValueError, match="Prompt cannot be empty"):
            JobSpec(
                prompt="",
                image_path=None,
                duration=5,
                aspect_ratio="16:9"
            )

        with pytest.raises(ValueError, match="Prompt cannot be empty"):
            JobSpec(
                prompt="   ",
                image_path=None,
                duration=5,
                aspect_ratio="16:9"
            )

    def test_invalid_duration(self):
        """Test duration validation"""
        with pytest.raises(ValueError, match="Duration must be 5, 10, or 15 seconds"):
            JobSpec(
                prompt="Test prompt",
                image_path=None,
                duration=7,
                aspect_ratio="16:9"
            )

    def test_valid_durations(self):
        """Test all valid durations"""
        for duration in [5, 10, 15]:
            spec = JobSpec(
                prompt="Test prompt",
                image_path=None,
                duration=duration,
                aspect_ratio="16:9"
            )
            assert spec.duration == duration
            assert spec.get_n_frames() == duration * 30

    def test_invalid_aspect_ratio(self):
        """Test aspect ratio validation"""
        with pytest.raises(ValueError, match="aspect_ratio must be one of"):
            JobSpec(
                prompt="Test prompt",
                image_path=None,
                duration=5,
                aspect_ratio="4:3"
            )

    def test_all_aspect_ratios(self):
        """Test all valid aspect ratios and orientations"""
        test_cases = [
            ("16:9", "landscape"),
            ("9:16", "portrait"),
            ("1:1", "square")
        ]
        for ratio, expected_orientation in test_cases:
            spec = JobSpec(
                prompt="Test prompt",
                image_path=None,
                duration=5,
                aspect_ratio=ratio
            )
            assert spec.get_orientation() == expected_orientation

    def test_job_spec_with_image(self):
        """Test JobSpec with image path"""
        spec = JobSpec(
            prompt="Test prompt",
            image_path="/path/to/image.png",
            duration=10,
            aspect_ratio="9:16"
        )
        assert spec.image_path == "/path/to/image.png"

    def test_job_spec_immutable(self):
        """Test JobSpec is immutable"""
        spec = JobSpec(
            prompt="Test",
            image_path=None,
            duration=5,
            aspect_ratio="16:9"
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            spec.prompt = "New prompt"


class TestJobProgress:
    """Test JobProgress value object"""

    def test_valid_job_progress(self):
        """Test creating valid JobProgress"""
        progress = JobProgress(
            status=JobStatus.PENDING,
            progress=0,
            error_message=None,
            retry_count=0,
            max_retries=3
        )
        assert progress.status == JobStatus.PENDING
        assert progress.progress == 0
        assert progress.can_retry() is False  # Not failed yet

    def test_progress_validation(self):
        """Test progress percentage validation"""
        with pytest.raises(ValueError, match="Progress must be between 0 and 100"):
            JobProgress(
                status=JobStatus.PROCESSING,
                progress=-1,
                max_retries=3
            )

        with pytest.raises(ValueError, match="Progress must be between 0 and 100"):
            JobProgress(
                status=JobStatus.PROCESSING,
                progress=101,
                max_retries=3
            )

    def test_retry_count_validation(self):
        """Test retry count validation"""
        with pytest.raises(ValueError, match="retry_count cannot be negative"):
            JobProgress(
                status=JobStatus.PENDING,
                progress=0,
                retry_count=-1,
                max_retries=3
            )

    def test_can_retry_when_failed(self):
        """Test can retry when failed and within limit"""
        progress = JobProgress(
            status=JobStatus.FAILED,
            progress=50,
            error_message="Test error",
            retry_count=1,
            max_retries=3
        )
        assert progress.can_retry()

    def test_cannot_retry_when_max_retries_reached(self):
        """Test cannot retry when max retries reached"""
        progress = JobProgress(
            status=JobStatus.FAILED,
            progress=50,
            error_message="Test error",
            retry_count=3,
            max_retries=3
        )
        assert not progress.can_retry()

    def test_increment_retry(self):
        """Test incrementing retry count"""
        progress = JobProgress(
            status=JobStatus.FAILED,
            progress=50,
            error_message="Test error",
            retry_count=1,
            max_retries=3
        )
        new_progress = progress.increment_retry()
        assert new_progress.retry_count == 2
        assert new_progress.status == JobStatus.PENDING
        assert new_progress.progress == 0
        assert new_progress.error_message is None

    def test_mark_failed(self):
        """Test marking job as failed"""
        progress = JobProgress(
            status=JobStatus.PROCESSING,
            progress=50,
            retry_count=0,
            max_retries=3
        )
        failed_progress = progress.mark_failed("Connection error")
        assert failed_progress.status == JobStatus.FAILED
        assert failed_progress.error_message == "Connection error"
        assert failed_progress.progress == 50
        assert failed_progress.retry_count == 0

    def test_update_progress(self):
        """Test updating progress percentage"""
        progress = JobProgress(
            status=JobStatus.PROCESSING,
            progress=0,
            max_retries=3
        )
        updated = progress.update_progress(50)
        assert updated.progress == 50
        assert updated.status == JobStatus.PROCESSING

        updated2 = updated.update_progress(100, "Complete")
        assert updated2.progress == 100
        assert updated2.error_message == "Complete"


class TestJobResult:
    """Test JobResult value object"""

    def test_empty_job_result(self):
        """Test empty JobResult"""
        result = JobResult()
        assert not result.is_complete()
        assert not result.has_url()

    def test_job_result_with_url(self):
        """Test JobResult with video URL"""
        result = JobResult(
            video_url="https://example.com/video.mp4",
            video_id="abc123"
        )
        assert result.has_url()
        assert not result.is_complete()  # No local path yet

    def test_job_result_complete(self):
        """Test complete JobResult"""
        result = JobResult(
            video_url="https://example.com/video.mp4",
            video_id="abc123",
            local_path="/downloads/video.mp4"
        )
        assert result.is_complete()
        assert result.has_url()


class TestJob:
    """Test Job aggregate root"""

    @pytest.fixture
    def valid_job(self):
        """Create a valid job for testing"""
        return Job(
            id=JobId(1),
            spec=JobSpec(
                prompt="A beautiful sunset",
                image_path=None,
                duration=5,
                aspect_ratio="16:9"
            ),
            progress=JobProgress(
                status=JobStatus.PENDING,
                progress=0,
                max_retries=3
            ),
            result=JobResult(),
            account_id=1
        )

    def test_valid_job_creation(self, valid_job):
        """Test creating a valid job"""
        assert valid_job.id.value == 1
        assert valid_job.spec.prompt == "A beautiful sunset"
        assert valid_job.progress.status == JobStatus.PENDING
        assert valid_job.account_id == 1

    def test_can_start_draft_job(self, valid_job):
        """Test can start draft job"""
        job = Job(
            id=valid_job.id,
            spec=valid_job.spec,
            progress=JobProgress(
                status=JobStatus.DRAFT,
                progress=0,
                max_retries=3
            ),
            result=valid_job.result
        )
        assert job.can_start()

    def test_can_start_pending_job(self, valid_job):
        """Test can start pending job"""
        assert valid_job.can_start()

    def test_cannot_start_processing_job(self, valid_job):
        """Test cannot start processing job"""
        job = Job(
            id=valid_job.id,
            spec=valid_job.spec,
            progress=JobProgress(
                status=JobStatus.PROCESSING,
                progress=25,
                max_retries=3
            ),
            result=valid_job.result
        )
        assert not job.can_start()

    def test_can_cancel_active_job(self, valid_job):
        """Test can cancel active job"""
        job = Job(
            id=valid_job.id,
            spec=valid_job.spec,
            progress=JobProgress(
                status=JobStatus.PROCESSING,
                progress=25,
                max_retries=3
            ),
            result=valid_job.result
        )
        assert job.can_cancel()

    def test_cannot_cancel_completed_job(self, valid_job):
        """Test cannot cancel completed job"""
        job = Job(
            id=valid_job.id,
            spec=valid_job.spec,
            progress=JobProgress(
                status=JobStatus.DONE,
                progress=100,
                max_retries=3
            ),
            result=valid_job.result
        )
        assert not job.can_cancel()

    def test_can_retry_failed_job(self, valid_job):
        """Test can retry failed job"""
        job = Job(
            id=valid_job.id,
            spec=valid_job.spec,
            progress=JobProgress(
                status=JobStatus.FAILED,
                progress=50,
                error_message="Error",
                max_retries=3
            ),
            result=valid_job.result
        )
        assert job.can_retry()

    def test_can_retry_cancelled_job(self, valid_job):
        """Test can retry cancelled job"""
        job = Job(
            id=valid_job.id,
            spec=valid_job.spec,
            progress=JobProgress(
                status=JobStatus.CANCELLED,
                progress=50,
                max_retries=3
            ),
            result=valid_job.result
        )
        assert job.can_retry()

    def test_to_orm_dict(self, valid_job):
        """Test converting to ORM dict"""
        orm_dict = valid_job.to_orm_dict()
        assert orm_dict["prompt"] == "A beautiful sunset"
        assert orm_dict["duration"] == 5
        assert orm_dict["aspect_ratio"] == "16:9"
        assert orm_dict["status"] == "pending"
        assert orm_dict["progress"] == 0
        assert orm_dict["account_id"] == 1
        assert "updated_at" in orm_dict

    def test_job_str_repr(self, valid_job):
        """Test string representation"""
        str_repr = str(valid_job)
        assert "Job" in str_repr
        assert "pending" in str_repr
        assert "0%" in str_repr
