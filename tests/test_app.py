"""
Test app without lifespan for testing
"""
from fastapi import FastAPI

def create_test_app():
    """Create FastAPI app for testing without lifespan"""
    test_app = FastAPI(title="Uni-Video Test App")

    # Import and include routers WITHOUT /api prefix for easier testing
    from app.api.routers import accounts, jobs, system
    test_app.include_router(accounts.router)
    test_app.include_router(jobs.router)
    test_app.include_router(system.router)

    return test_app

# Export test app
app = create_test_app()
