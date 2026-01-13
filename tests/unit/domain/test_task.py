"""
Unit tests for Task Domain Models

Tests:
- TaskType enum
- TaskContext validation and methods
"""
import pytest
from app.core.domain.task import TaskType, TaskContext


class TestTaskType:
    """Test TaskType enum"""

    def test_all_task_types(self):
        """Test all defined task types"""
        assert TaskType.GENERATE.value == "generate"
        assert TaskType.POLL.value == "poll"
        assert TaskType.DOWNLOAD.value == "download"
        assert TaskType.VERIFY.value == "verify"

    def test_task_type_from_string(self):
        """Test creating TaskType from string"""
        assert TaskType("generate") == TaskType.GENERATE
        assert TaskType("poll") == TaskType.POLL
        assert TaskType("download") == TaskType.DOWNLOAD
        assert TaskType("verify") == TaskType.VERIFY


class TestTaskContext:
    """Test TaskContext value object"""

    def test_valid_task_context(self):
        """Test creating valid TaskContext"""
        context = TaskContext(
            job_id=1,
            task_type=TaskType.GENERATE,
            input_data={"prompt": "Test prompt"},
            retry_count=0
        )
        assert context.job_id == 1
        assert context.task_type == TaskType.GENERATE
        assert context.input_data == {"prompt": "Test prompt"}
        assert context.retry_count == 0

    def test_task_context_with_string_task_type(self):
        """Test TaskContext converts string to TaskType"""
        context = TaskContext(
            job_id=1,
            task_type="generate",
            input_data={}
        )
        assert context.task_type == TaskType.GENERATE

    def test_job_id_must_be_positive(self):
        """Test job_id validation"""
        with pytest.raises(ValueError, match="job_id must be positive"):
            TaskContext(
                job_id=0,
                task_type=TaskType.GENERATE,
                input_data={}
            )

        with pytest.raises(ValueError, match="job_id must be positive"):
            TaskContext(
                job_id=-1,
                task_type=TaskType.GENERATE,
                input_data={}
            )

    def test_retry_count_cannot_be_negative(self):
        """Test retry_count validation"""
        with pytest.raises(ValueError, match="retry_count cannot be negative"):
            TaskContext(
                job_id=1,
                task_type=TaskType.GENERATE,
                input_data={},
                retry_count=-1
            )

    def test_with_retry(self):
        """Test creating new context with incremented retry"""
        context = TaskContext(
            job_id=1,
            task_type=TaskType.GENERATE,
            input_data={"key": "value"},
            retry_count=0
        )
        new_context = context.with_retry()

        assert new_context.retry_count == 1
        assert new_context.job_id == context.job_id
        assert new_context.task_type == context.task_type
        assert new_context.input_data == context.input_data
        # Original unchanged
        assert context.retry_count == 0

    def test_with_data(self):
        """Test creating new context with updated data"""
        context = TaskContext(
            job_id=1,
            task_type=TaskType.GENERATE,
            input_data={"key1": "value1"},
            retry_count=0
        )
        new_context = context.with_data(key2="value2", key3="value3")

        assert new_context.input_data == {
            "key1": "value1",
            "key2": "value2",
            "key3": "value3"
        }
        # Original unchanged
        assert context.input_data == {"key1": "value1"}

    def test_with_data_overwrites_existing(self):
        """Test with_data overwrites existing keys"""
        context = TaskContext(
            job_id=1,
            task_type=TaskType.GENERATE,
            input_data={"key": "old_value"},
            retry_count=0
        )
        new_context = context.with_data(key="new_value")

        assert new_context.input_data == {"key": "new_value"}

    def test_get_data(self):
        """Test getting data from input_data"""
        context = TaskContext(
            job_id=1,
            task_type=TaskType.GENERATE,
            input_data={"key1": "value1", "key2": 123},
            retry_count=0
        )

        assert context.get_data("key1") == "value1"
        assert context.get_data("key2") == 123
        assert context.get_data("missing_key") is None
        assert context.get_data("missing_key", "default") == "default"

    def test_default_input_data(self):
        """Test TaskContext with default empty input_data"""
        context = TaskContext(
            job_id=1,
            task_type=TaskType.GENERATE
        )
        assert context.input_data == {}
        assert context.retry_count == 0

    def test_task_context_str_repr(self):
        """Test string representation"""
        context = TaskContext(
            job_id=123,
            task_type=TaskType.GENERATE,
            input_data={},
            retry_count=2
        )
        str_repr = str(context)
        assert "TaskContext" in str_repr
        assert "123" in str_repr
        assert "generate" in str_repr
        assert "2" in str_repr

    def test_multiple_retries(self):
        """Test multiple retry increments"""
        context = TaskContext(
            job_id=1,
            task_type=TaskType.GENERATE,
            input_data={}
        )

        context1 = context.with_retry()
        assert context1.retry_count == 1

        context2 = context1.with_retry()
        assert context2.retry_count == 2

        context3 = context2.with_retry()
        assert context3.retry_count == 3

    def test_complex_input_data(self):
        """Test TaskContext with complex input_data"""
        complex_data = {
            "prompt": "Test prompt",
            "duration": 5,
            "options": {
                "aspect_ratio": "16:9",
                "quality": "high"
            },
            "tags": ["tag1", "tag2"]
        }

        context = TaskContext(
            job_id=1,
            task_type=TaskType.GENERATE,
            input_data=complex_data
        )

        assert context.get_data("prompt") == "Test prompt"
        assert context.get_data("duration") == 5
        assert context.get_data("options") == {
            "aspect_ratio": "16:9",
            "quality": "high"
        }
        assert context.get_data("tags") == ["tag1", "tag2"]
