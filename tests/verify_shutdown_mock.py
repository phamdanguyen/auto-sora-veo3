
import sys
import os
import asyncio
from unittest.mock import AsyncMock, patch
from fastapi import FastAPI

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

async def run_check():
    # Mock the worker module BEFORE importing app.main
    with patch("app.core.worker_v2.stop_worker", new_callable=AsyncMock) as mock_stop:
        with patch("app.core.worker_v2.start_worker", new_callable=AsyncMock) as mock_start:
            with patch("app.core.worker_download.start_worker", new_callable=AsyncMock) as mock_dl_start:
                # Import app after mocking
                try:
                    from app.main import app
                except ImportError as e:
                    print(f"❌ ImportError: {e}")
                    return

                print("🚀 Starting Lifespan Check...")
                
                # Manually trigger lifespan
                # FastAPI stores lifespan in router.lifespan_context
                try:
                    async with app.router.lifespan_context(app):
                        print("✅ Startup complete (Context entered)")
                except Exception as e:
                    print(f"❌ Lifespan Error: {e}")
                    import traceback
                    traceback.print_exc()

                print("🛑 Shutdown complete (Context exited)")
                
                # Verify stop_worker was called
                if mock_stop.called:
                    print("✅ PASSED: worker.stop_worker() was called!")
                else:
                    print("❌ FAILED: worker.stop_worker() was NOT called.")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(run_check())
