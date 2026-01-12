"""
FastAPI Dependencies

Provides dependency injection for FastAPI endpoints

Implements Dependency Inversion Principle (DIP):
- Endpoints depend on abstractions (repositories, services)
- Implementations injected via container

Usage in endpoints:
    @router.get("/accounts/")
    async def list_accounts(
        account_repo: AccountRepository = Depends(get_account_repository)
    ):
        accounts = await account_repo.get_all()
        return accounts
"""

from typing import Generator
from fastapi import Depends
from sqlalchemy.orm import Session
from ..core.container import container
from ..core.repositories.account_repo import AccountRepository
from ..core.repositories.job_repo import JobRepository

# NOTE: Services dependencies sẽ được add ở Phase 2
# from ..core.services.account_service import AccountService
# from ..core.services.job_service import JobService
# from ..core.services.task_service import TaskService


# ========== Database Session ==========
def get_db() -> Generator[Session, None, None]:
    """
    Dependency để lấy database session

    Yields:
        SQLAlchemy Session

    Usage:
        @router.get("/accounts/")
        def list_accounts(db: Session = Depends(get_db)):
            # Use db session
            pass
    """
    db = container.db_session()
    try:
        yield db
    finally:
        db.close()


# ========== Repositories ==========
def get_account_repository(db: Session = Depends(get_db)) -> AccountRepository:
    """
    Dependency để lấy AccountRepository

    Args:
        db: Database session (auto-injected)

    Returns:
        AccountRepository instance

    Usage:
        @router.get("/accounts/")
        async def list_accounts(
            repo: AccountRepository = Depends(get_account_repository)
        ):
            return await repo.get_all()
    """
    return AccountRepository(db)


def get_job_repository(db: Session = Depends(get_db)) -> JobRepository:
    """
    Dependency để lấy JobRepository

    Args:
        db: Database session (auto-injected)

    Returns:
        JobRepository instance

    Usage:
        @router.get("/jobs/")
        async def list_jobs(
            repo: JobRepository = Depends(get_job_repository)
        ):
            return await repo.get_all()
    """
    return JobRepository(db)


# ========== Driver Factory (Phase 1 Task 1.4) ==========
# def get_driver_factory() -> DriverFactory:
#     """Dependency để lấy DriverFactory"""
#     return container.driver_factory()


# ========== Services (Phase 2) ==========
# def get_account_service(
#     account_repo: AccountRepository = Depends(get_account_repository),
#     driver_factory: DriverFactory = Depends(get_driver_factory)
# ) -> AccountService:
#     """Dependency để lấy AccountService"""
#     return AccountService(account_repo, driver_factory)


# def get_job_service(
#     job_repo: JobRepository = Depends(get_job_repository),
#     account_repo: AccountRepository = Depends(get_account_repository)
# ) -> JobService:
#     """Dependency để lấy JobService"""
#     return JobService(job_repo, account_repo)


# def get_task_service(
#     job_repo: JobRepository = Depends(get_job_repository),
#     account_repo: AccountRepository = Depends(get_account_repository)
# ) -> TaskService:
#     """Dependency để lấy TaskService"""
#     return TaskService(job_repo, account_repo)


# ========== Workers (Phase 3) ==========
# def get_worker_manager() -> WorkerManager:
#     """Dependency để lấy WorkerManager"""
#     return container.worker_manager()
