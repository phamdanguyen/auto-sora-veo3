"""
Task Domain Models

Value Objects for task execution context

Implements:
- SRP: Single responsibility (task context)
- OCP: Can extend with new task types
"""

from dataclasses import dataclass, field
from typing import Dict, Any
from enum import Enum


class TaskType(str, Enum):
    """
    Task type enum
    Defines available task types

    Implements OCP: Easy to add new types
    """
    GENERATE = "generate"
    POLL = "poll"
    DOWNLOAD = "download"
    VERIFY = "verify"


@dataclass
class TaskContext:
    """
    Value Object cho Task execution context

    Lightweight context passed between workers
    No DB access - just data

    Implements:
    - SRP: Single responsibility (carry task data)
    - ISP: Minimal interface
    """
    job_id: int
    task_type: TaskType
    input_data: Dict[str, Any] = field(default_factory=dict)
    retry_count: int = 0

    def __post_init__(self):
        # Validate job_id
        if self.job_id <= 0:
            raise ValueError("job_id must be positive")

        # Validate task_type
        if isinstance(self.task_type, str):
            # Convert string to enum if needed
            self.task_type = TaskType(self.task_type)

        # Validate retry_count
        if self.retry_count < 0:
            raise ValueError("retry_count cannot be negative")

    def with_retry(self) -> 'TaskContext':
        """
        Create new TaskContext with incremented retry count

        Returns:
            New TaskContext instance
        """
        return TaskContext(
            job_id=self.job_id,
            task_type=self.task_type,
            input_data=self.input_data.copy(),
            retry_count=self.retry_count + 1
        )

    def with_data(self, **kwargs) -> 'TaskContext':
        """
        Create new TaskContext with updated input_data

        Returns:
            New TaskContext instance
        """
        new_data = self.input_data.copy()
        new_data.update(kwargs)

        return TaskContext(
            job_id=self.job_id,
            task_type=self.task_type,
            input_data=new_data,
            retry_count=self.retry_count
        )

    def get_data(self, key: str, default: Any = None) -> Any:
        """
        Get value from input_data

        Args:
            key: Key to lookup
            default: Default value if key not found

        Returns:
            Value or default
        """
        return self.input_data.get(key, default)

    def __str__(self) -> str:
        return f"TaskContext(job_id={self.job_id}, type={self.task_type.value}, retry={self.retry_count})"

    def __repr__(self) -> str:
        return self.__str__()
