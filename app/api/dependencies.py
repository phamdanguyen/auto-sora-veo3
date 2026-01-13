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

# Services (Phase 2)
from ..core.services.account_service import AccountService
from ..core.services.job_service import JobService
from ..core.services.task_service import TaskService


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


# ========== Driver Factory ==========
def get_driver_factory():
    """
    Dependency để lấy DriverFactory

    Returns:
        Global driver_factory instance

    Usage:
        @router.post("/generate")
        async def generate(
            factory = Depends(get_driver_factory)
        ):
            driver = factory.create_driver("sora", ...)
            return await driver.generate_video(...)
    """
    from ..core.drivers import driver_factory
    return driver_factory


# ========== Services (Phase 2) ==========
def get_account_service(
    account_repo: AccountRepository = Depends(get_account_repository),
    driver_factory = Depends(get_driver_factory)
) -> AccountService:
    """
    Dependency để lấy AccountService

    Args:
        account_repo: AccountRepository (auto-injected)
        driver_factory: DriverFactory (auto-injected)

    Returns:
        AccountService instance

    Usage:
        @router.post("/accounts/refresh-credits")
        async def refresh_credits(
            account_id: int,
            service: AccountService = Depends(get_account_service)
        ):
            return await service.refresh_credits(account_id)
    """
    return AccountService(account_repo, driver_factory)


def get_job_service(
    job_repo: JobRepository = Depends(get_job_repository),
    account_repo: AccountRepository = Depends(get_account_repository)
) -> JobService:
    """
    Dependency để lấy JobService

    Args:
        job_repo: JobRepository (auto-injected)
        account_repo: AccountRepository (auto-injected)

    Returns:
        JobService instance

    Usage:
        @router.post("/jobs/")
        async def create_job(
            prompt: str,
            service: JobService = Depends(get_job_service)
        ):
            return await service.create_job(prompt, ...)
    """
    return JobService(job_repo, account_repo)


def get_task_service(
    job_repo: JobRepository = Depends(get_job_repository),
    account_repo: AccountRepository = Depends(get_account_repository)
) -> TaskService:
    """
    Dependency để lấy TaskService

    Args:
        job_repo: JobRepository (auto-injected)
        account_repo: AccountRepository (auto-injected)

    Returns:
        TaskService instance

    Usage:
        @router.post("/jobs/{job_id}/start")
        async def start_job(
            job_id: int,
            service: TaskService = Depends(get_task_service)
        ):
            return await service.start_job(job_id)
    """
    return TaskService(job_repo, account_repo)


# ========== Workers ==========
# Note: Currently using legacy worker_v2 system
# Future: Migrate to new WorkerManager with dependency injection
# def get_worker_manager() -> WorkerManager:
#     """Dependency để lấy WorkerManager"""
#     return container.worker_manager()
