"""
Repository Pattern Implementation

Implements Dependency Inversion Principle (DIP):
- High-level code (services, workers) depend on repository abstractions
- Low-level code (SQLAlchemy) implements these abstractions

Benefits:
- Easy to test (can mock repositories)
- Easy to swap database (just implement new repository)
- Domain layer independent of infrastructure
"""

from .base import BaseRepository
from .account_repo import AccountRepository
from .job_repo import JobRepository

__all__ = [
    "BaseRepository",
    "AccountRepository",
    "JobRepository"
]
