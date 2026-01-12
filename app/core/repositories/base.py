"""
Base Repository

Abstract base class for all repositories
Implements common CRUD operations

Implements:
- DIP: Abstract interface that high-level code depends on
- ISP: Minimal interface, specific repos can extend
"""

from abc import ABC, abstractmethod
from typing import TypeVar, Generic, Optional, List
from sqlalchemy.orm import Session

T = TypeVar('T')


class BaseRepository(ABC, Generic[T]):
    """
    Abstract base repository với CRUD operations cơ bản

    Generic[T]: T là domain model type (Account, Job, etc.)

    Subclasses must implement:
    - get_by_id
    - get_all
    - create
    - update
    - delete
    """

    def __init__(self, session: Session):
        """
        Initialize repository with database session

        Args:
            session: SQLAlchemy session
        """
        self.session = session

    @abstractmethod
    async def get_by_id(self, id: int) -> Optional[T]:
        """
        Lấy entity theo ID

        Args:
            id: Entity ID

        Returns:
            Domain model or None if not found
        """
        pass

    @abstractmethod
    async def get_all(self, skip: int = 0, limit: int = 100) -> List[T]:
        """
        Lấy danh sách entities

        Args:
            skip: Number of records to skip
            limit: Max number of records to return

        Returns:
            List of domain models
        """
        pass

    @abstractmethod
    async def create(self, entity: T) -> T:
        """
        Tạo entity mới

        Args:
            entity: Domain model to create

        Returns:
            Created domain model (with ID populated)
        """
        pass

    @abstractmethod
    async def update(self, entity: T) -> T:
        """
        Cập nhật entity

        Args:
            entity: Domain model to update

        Returns:
            Updated domain model
        """
        pass

    @abstractmethod
    async def delete(self, id: int) -> bool:
        """
        Xóa entity

        Args:
            id: Entity ID to delete

        Returns:
            True if deleted, False if not found
        """
        pass

    def commit(self):
        """
        Commit transaction

        Call this after create/update/delete operations
        """
        self.session.commit()

    def rollback(self):
        """
        Rollback transaction

        Call this on error to undo changes
        """
        self.session.rollback()

    def flush(self):
        """
        Flush changes to database without committing

        Useful to get auto-generated IDs
        """
        self.session.flush()
