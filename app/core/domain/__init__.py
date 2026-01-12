"""
Domain Models Package

This package contains domain models (value objects and aggregates)
that represent core business entities, independent of infrastructure.

Following Domain-Driven Design (DDD) principles:
- Value Objects: Immutable, identified by their attributes
- Entities: Mutable, identified by ID
- Aggregates: Clusters of entities with a root entity

Implements SOLID principles:
- SRP: Each model has single responsibility
- ISP: Small, focused interfaces
"""

from .account import (
    AccountId,
    AccountAuth,
    AccountSession,
    AccountCredits,
    Account
)

from .job import (
    JobId,
    JobStatus,
    JobSpec,
    JobProgress,
    JobResult,
    Job
)

from .task import (
    TaskContext,
    TaskType
)

__all__ = [
    # Account
    "AccountId",
    "AccountAuth",
    "AccountSession",
    "AccountCredits",
    "Account",

    # Job
    "JobId",
    "JobStatus",
    "JobSpec",
    "JobProgress",
    "JobResult",
    "Job",

    # Task
    "TaskContext",
    "TaskType"
]
