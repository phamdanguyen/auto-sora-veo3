"""
Driver Abstractions

Abstract interfaces for video generation drivers

Implements:
- LSP (Liskov Substitution Principle): All drivers can be substituted
- DIP (Dependency Inversion): Workers depend on abstractions, not concrete drivers
- OCP (Open/Closed): Easy to add new drivers without modifying existing code

Data Classes for driver responses
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from dataclasses import dataclass


# ========== Data Classes ==========

@dataclass
class VideoResult:
    """
    Result từ video generation request

    Attributes:
        success: Whether generation was successful
        task_id: Task ID for polling (if success)
        error: Error message (if failed)
        error_code: Parsed error code from API response (e.g., 'heavy_load', 'too_many_concurrent_tasks')
    """
    success: bool
    task_id: Optional[str] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    generation_id: Optional[str] = None


@dataclass
class CreditsInfo:
    """
    Credits information

    Attributes:
        credits: Number of credits remaining
        reset_seconds: Seconds until credits reset
        error_code: Error code if API call failed
        error: Error message if failed
    """
    credits: Optional[int]
    reset_seconds: Optional[int] = None
    error_code: Optional[str] = None
    error: Optional[str] = None

    def has_credits(self) -> bool:
        """Check if account has credits"""
        return self.credits is not None and self.credits > 0


@dataclass
class UploadResult:
    """
    Result từ image upload

    Attributes:
        success: Whether upload was successful
        file_id: Uploaded file ID (if success)
        error: Error message (if failed)
    """
    success: bool
    file_id: Optional[str] = None
    error: Optional[str] = None


@dataclass
class VideoData:
    """
    Video data khi generation complete

    Attributes:
        id: Video ID
        download_url: URL to download video
        status: Video status ("completed", "failed", etc.)
        progress_pct: Progress percentage (0.0 - 1.0)
    """
    id: str
    download_url: str
    status: str
    progress_pct: Optional[float] = None
    error: Optional[str] = None
    generation_id: Optional[str] = None

    def is_complete(self) -> bool:
        """Check if video generation is complete"""
        return self.status == "completed"


@dataclass
class PendingTask:
    """
    Pending task information

    Attributes:
        id: Task ID
        status: Task status
        progress_pct: Progress percentage (0.0 - 1.0)
        created_at: Task creation timestamp
    """
    id: str
    status: str
    progress_pct: Optional[float] = None
    created_at: Optional[str] = None


# ========== Abstract Driver Interface ==========

class VideoGenerationDriver(ABC):
    """
    Abstract base class cho video generation drivers

    All drivers (Sora, VEO3, Runway, etc.) must implement this interface

    Implements:
    - LSP: All subclasses can be substituted without breaking code
    - ISP: Focused interface for video generation
    - DIP: High-level code depends on this abstraction

    Methods:
    - start/stop: Lifecycle management
    - generate_video: Main generation method
    - get_credits: Check account credits
    - upload_image: Upload image for image-to-video
    - wait_for_completion: Poll for video completion
    - get_pending_tasks: List pending tasks
    """

    @abstractmethod
    async def start(self) -> None:
        """
        Start driver (initialize browser/API client)

        Called before any operations

        Raises:
            Exception: If startup fails
        """
        pass

    @abstractmethod
    async def stop(self) -> None:
        """
        Stop driver and cleanup resources

        Called after all operations complete

        Should:
        - Close browser (if applicable)
        - Cleanup temporary files
        - Release resources
        """
        pass

    @abstractmethod
    async def generate_video(
        self,
        prompt: str,
        duration: int,
        aspect_ratio: str,
        image_path: Optional[str] = None
    ) -> VideoResult:
        """
        Generate video

        Args:
            prompt: Text prompt for video generation
            duration: Duration in seconds (5, 10, or 15)
            aspect_ratio: Aspect ratio ("16:9", "9:16", "1:1")
            image_path: Optional path to image for image-to-video

        Returns:
            VideoResult with task_id if successful

        Raises:
            Exception: If generation request fails
        """
        pass

    @abstractmethod
    async def get_credits(self) -> CreditsInfo:
        """
        Get credits information

        Returns:
            CreditsInfo with credits remaining

        Raises:
            Exception: If API call fails
        """
        pass

    @abstractmethod
    async def upload_image(self, image_path: str) -> UploadResult:
        """
        Upload image for video generation

        Args:
            image_path: Path to image file

        Returns:
            UploadResult with file_id if successful

        Raises:
            Exception: If upload fails
        """
        pass

    @abstractmethod
    async def wait_for_completion(
        self,
        task_id: str,
        timeout: int = 300,
        poll_interval: int = 10
    ) -> Optional[VideoData]:
        """
        Wait for video generation to complete

        Args:
            task_id: Task ID to wait for
            timeout: Max wait time in seconds
            poll_interval: Seconds between polls

        Returns:
            VideoData when complete, None if timeout

        Raises:
            Exception: If polling fails
        """
        pass

    @abstractmethod
    async def get_pending_tasks(self) -> List[PendingTask]:
        """
        Get list of pending generation tasks

        Returns:
            List of PendingTask objects

        Useful for:
        - Batch checking multiple jobs
        - Resume interrupted jobs
        - Monitor progress

        Raises:
            Exception: If API call fails
        """
        pass


# ========== Browser-based Driver Base ==========

class BrowserBasedDriver(VideoGenerationDriver):
    """
    Base class cho drivers sử dụng browser automation

    Provides common browser initialization logic

    Subclasses:
    - Must call super().__init__() in __init__
    - Can override start() to customize browser setup
    - Must implement all abstract methods from VideoGenerationDriver
    """

    def __init__(
        self,
        headless: bool = True,
        proxy: Optional[str] = None,
        user_data_dir: Optional[str] = None,
        channel: str = "chrome"
    ):
        """
        Initialize browser-based driver

        Args:
            headless: Run browser in headless mode
            proxy: Proxy string (ip:port:user:pass)
            user_data_dir: Browser profile directory
            channel: Browser channel ("chrome", "msedge", etc.)
        """
        self.headless = headless
        self.proxy = proxy
        self.user_data_dir = user_data_dir
        self.channel = channel

        # Will be set in start()
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None


# ========== API-Only Driver Base ==========

class APIOnlyDriver(VideoGenerationDriver):
    """
    Base class cho drivers chỉ sử dụng API (no browser)

    Provides common API client logic

    Subclasses:
    - Must call super().__init__() in __init__
    - No browser overhead
    - Faster and more reliable
    - Must implement all abstract methods from VideoGenerationDriver
    """

    def __init__(
        self,
        access_token: str,
        device_id: Optional[str] = None,
        user_agent: Optional[str] = None
    ):
        """
        Initialize API-only driver

        Args:
            access_token: API access token
            device_id: Device ID for API calls
            user_agent: User agent string
        """
        self.access_token = access_token
        self.device_id = device_id
        self.user_agent = user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

    async def start(self) -> None:
        """
        No-op for API-only drivers

        Override if you need to initialize HTTP client
        """
        pass

    async def stop(self) -> None:
        """
        No-op for API-only drivers

        Override if you need to cleanup HTTP client
        """
        pass
