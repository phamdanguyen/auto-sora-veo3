"""
Pytest configuration và shared fixtures
"""
import pytest
import sys
import os
from pathlib import Path
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from fastapi.testclient import TestClient

# Add app to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import Base
from app.main import app
from app.api.dependencies import get_db
from app.core.container import Container


@pytest.fixture(scope="session")
def test_db_path(tmp_path_factory) -> str:
    """Tạo test database path"""
    db_dir = tmp_path_factory.mktemp("test_db")
    return str(db_dir / "test.db")


@pytest.fixture(scope="function")
def test_engine(test_db_path):
    """Tạo test database engine"""
    engine = create_engine(
        f"sqlite:///{test_db_path}",
        connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def test_session(test_engine) -> Generator[Session, None, None]:
    """Tạo test database session"""
    SessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=test_engine
    )
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def test_container(test_session) -> Container:
    """Tạo test DI container"""
    container = Container()
    container.db.override(lambda: test_session)
    container.wire(modules=[
        "app.api.routers.accounts",
        "app.api.routers.jobs",
        "app.api.routers.system"
    ])
    yield container
    container.unwire()


@pytest.fixture(scope="function")
def client(test_session) -> Generator[TestClient, None, None]:
    """Tạo FastAPI test client"""
    def override_get_db():
        try:
            yield test_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def sample_account_data():
    """Sample account data for testing"""
    return {
        "email": "test@example.com",
        "password": "Test123!@#",
        "login_mode": "auto",
        "status": "active"
    }


@pytest.fixture
def sample_job_data():
    """Sample job data for testing"""
    return {
        "prompt": "A beautiful sunset over the ocean",
        "duration": 5,
        "account_id": 1
    }


@pytest.fixture
def sample_task_data():
    """Sample task data for testing"""
    return {
        "job_id": 1,
        "task_type": "generate",
        "status": "pending"
    }


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singleton instances between tests"""
    # Add logic to reset singletons if needed
    yield
    # Cleanup after test
