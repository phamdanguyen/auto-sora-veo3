"""
Base Worker Class
Implements: Single Responsibility Principle (SRP)
"""
from abc import ABC, abstractmethod
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class BaseWorker(ABC):
    """Abstract base class cho workers"""

    def __init__(
        self,
        max_concurrent: int = 10,
        stop_event: Optional[asyncio.Event] = None
    ):
        self.max_concurrent = max_concurrent
        self.stop_event = stop_event or asyncio.Event()
        self._running = False
        self._tasks = set()

    @abstractmethod
    async def process_task(self, task):
        """Process một task - Must be implemented by subclasses"""
        pass

    @abstractmethod
    def get_queue(self):
        """Get queue để consume - Must be implemented by subclasses"""
        pass

    async def start(self):
        """Start worker loop"""
        if self._running:
            logger.warning(f"{self.__class__.__name__} already running")
            return

        self._running = True
        self.stop_event.clear()

        logger.info(f"[START] {self.__class__.__name__} started (max_concurrent={self.max_concurrent})")

        try:
            await self._worker_loop()
        except Exception as e:
            logger.error(f"[ERROR] {self.__class__.__name__} crashed: {e}", exc_info=True)
        finally:
            self._running = False

    async def stop(self):
        """Stop worker and wait for cleanup"""
        logger.info(f"[STOP] {self.__class__.__name__} stopping...")
        self.stop_event.set()

        # Wait for active tasks
        if self._tasks:
            logger.info(f"[STOP] Waiting for {len(self._tasks)} active tasks...")
            for task in self._tasks:
                task.cancel()
            await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks.clear()

        logger.info(f"[STOP] {self.__class__.__name__} stopped")

    async def _worker_loop(self):
        """Main worker loop"""
        queue = self.get_queue()

        while not self.stop_event.is_set():
            try:
                # Clean up finished tasks
                finished = [t for t in self._tasks if t.done()]
                for task in finished:
                    try:
                        task.result()
                    except asyncio.CancelledError:
                        pass
                    except Exception as e:
                        logger.error(f"[ERROR] Task failed: {e}")
                    self._tasks.discard(task)

                # Check if we can accept more tasks
                if len(self._tasks) >= self.max_concurrent:
                    await asyncio.sleep(1)
                    continue

                # Get task from queue
                try:
                    task = await asyncio.wait_for(queue.get(), timeout=5.0)
                except asyncio.TimeoutError:
                    continue

                # Process task in background
                bg_task = asyncio.create_task(
                    self.process_task(task),
                    name=f"{self.__class__.__name__}_task_{id(task)}"
                )
                self._tasks.add(bg_task)

            except Exception as e:
                logger.error(f"[ERROR] Worker loop error: {e}", exc_info=True)
                await asyncio.sleep(5)
