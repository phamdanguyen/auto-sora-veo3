"""
Dependency Injection Container

Implements Dependency Inversion Principle (DIP):
- Central place to configure dependencies
- Easy to swap implementations
- Easy to test (can override providers)

Uses dependency-injector library for IoC container
"""

from dependency_injector import containers, providers
from sqlalchemy.orm import Session
from ..database import SessionLocal

# Repositories
from .repositories.account_repo import AccountRepository
from .repositories.job_repo import JobRepository

# NOTE: Services và Workers sẽ được add ở Phase 2 và Phase 3
# from .services.account_service import AccountService
# from .services.job_service import JobService
# from .workers.generate_worker import GenerateWorker


class Container(containers.DeclarativeContainer):
    """
    Main DI Container

    Manages all dependencies in the application:
    - Database sessions
    - Repositories
    - Services (Phase 2)
    - Workers (Phase 3)
    - Drivers (Phase 1 Task 1.4)

    Benefits:
    - Single source of truth for dependencies
    - Easy to test (mock providers)
    - Easy to reconfigure (override providers)
    """

    # ========== Configuration ==========
    config = providers.Configuration()

    # ========== Database ==========
    db_session = providers.Factory(
        SessionLocal
    )

    # ========== Repositories ==========
    account_repository = providers.Factory(
        AccountRepository,
        session=db_session
    )

    job_repository = providers.Factory(
        JobRepository,
        session=db_session
    )

    # ========== Drivers (Phase 1 Task 1.4) ==========
    # driver_factory = providers.Singleton(
    #     DriverFactory
    # )

    # ========== Services (Phase 2) ==========
    # account_service = providers.Factory(
    #     AccountService,
    #     account_repo=account_repository,
    #     driver_factory=driver_factory
    # )

    # job_service = providers.Factory(
    #     JobService,
    #     job_repo=job_repository,
    #     account_repo=account_repository
    # )

    # task_service = providers.Factory(
    #     TaskService,
    #     job_repo=job_repository,
    #     account_repo=account_repository
    # )

    # ========== Workers (Phase 3) ==========
    # generate_worker = providers.Factory(
    #     GenerateWorker,
    #     job_repo=job_repository,
    #     account_repo=account_repository,
    #     driver_factory=driver_factory
    # )

    # poll_worker = providers.Factory(
    #     PollWorker,
    #     job_repo=job_repository,
    #     driver_factory=driver_factory
    # )

    # download_worker = providers.Factory(
    #     DownloadWorker,
    #     job_repo=job_repository
    # )

    # worker_manager = providers.Singleton(
    #     WorkerManager,
    #     job_repo=job_repository,
    #     account_repo=account_repository,
    #     driver_factory=driver_factory
    # )


# Global container instance
container = Container()


def init_container():
    """
    Initialize container

    Call this on app startup
    """
    # Can set config values here if needed
    # container.config.from_dict({
    #     "database": {
    #         "url": "sqlite:///./data/db/univideo.db"
    #     }
    # })
    pass


def reset_container():
    """
    Reset container

    Useful for testing
    """
    container.reset_singletons()
