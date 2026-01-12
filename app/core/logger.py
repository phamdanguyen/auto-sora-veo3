import asyncio
import logging
from collections import deque
from typing import List, Callable

class LogStreamManager:
    _instance = None
    
    def __init__(self):
        # Buffer last 2000 lines
        self.buffer: deque = deque(maxlen=2000)
        self.connected_clients: List[Callable] = []
        self._lock = asyncio.Lock()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = LogStreamManager()
        return cls._instance

    def add_log(self, message: str, level: str = "INFO"):
        """Adds a log message to the buffer and broadcasts it."""
        entry = {
            "message": message,
            "level": level,
        }
        self.buffer.append(entry)
        
        # Broadcast
        if self.connected_clients:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.broadcast_entry(entry))
            except RuntimeError:
                # No running loop (e.g. early startup), buffering is enough
                pass

    async def broadcast_entry(self, entry: dict):
        """Async broadcast method."""
        to_remove = []
        for ws in self.connected_clients:
            try:
                await ws.send_json(entry)
            except Exception:
                to_remove.append(ws)
        
        for ws in to_remove:
            if ws in self.connected_clients:
                self.connected_clients.remove(ws)

# Global instance
log_manager = LogStreamManager.get_instance()

class ListLogHandler(logging.Handler):
    """Custom logging handler to push logs into LogStreamManager."""
    def emit(self, record):
        try:
            msg = self.format(record)
            log_manager.add_log(msg, record.levelname)
        except Exception:
            self.handleError(record)
