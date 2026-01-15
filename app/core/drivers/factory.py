"""
Driver Factory

Factory pattern for creating video generation drivers

Implements Open/Closed Principle (OCP):
- Easy to add new drivers without modifying existing code
- Just register new driver class

Usage:
    factory = DriverFactory()
    driver = factory.create_driver("sora", access_token="...")
    driver = factory.create_driver("veo3", access_token="...")
"""

from typing import Dict, Type, Any
from .abstractions import VideoGenerationDriver
import logging

logger = logging.getLogger(__name__)


class DriverFactory:
    """
    Factory để tạo driver phù hợp theo platform

    Implements:
    - OCP: Closed for modification, open for extension
    - DIP: Returns abstraction (VideoGenerationDriver)
    """

    def __init__(self):
        """Initialize factory with empty registry"""
        self._drivers: Dict[str, Type[VideoGenerationDriver]] = {}

    def register(
        self,
        platform: str,
        driver_class: Type[VideoGenerationDriver]
    ):
        """
        Register driver class cho platform

        Args:
            platform: Platform name ("sora", "veo3", etc.)
            driver_class: Driver class (must inherit VideoGenerationDriver)

        Example:
            factory.register("sora", SoraDriver)
            factory.register("veo3", VEO3Driver)
        """
        if not issubclass(driver_class, VideoGenerationDriver):
            raise TypeError(
                f"Driver class {driver_class.__name__} must inherit VideoGenerationDriver"
            )

        self._drivers[platform] = driver_class
        logger.info(f"Registered driver: {platform} -> {driver_class.__name__}")

    def create_driver(
        self,
        platform: str,
        **kwargs: Any
    ) -> VideoGenerationDriver:
        """
        Create driver instance

        Args:
            platform: Platform name ("sora", "veo3", etc.)
            **kwargs: Driver-specific kwargs
                - For API-only: access_token, device_id, user_agent
                - For browser-based: headless, proxy, user_data_dir

        Returns:
            VideoGenerationDriver instance

        Raises:
            ValueError: If platform not registered

        Example:
            # API-only driver
            driver = factory.create_driver(
                "sora",
                access_token="...",
                device_id="...",
                user_agent="..."
            )

            # Browser-based driver
            driver = factory.create_driver(
                "sora",
                headless=False,
                user_data_dir="/path/to/profile"
            )
        """
        # Special handling for Sora API mode
        if platform == "sora" and kwargs.get("api_mode"):
            from app.core.drivers.sora.api_driver import SoraApiDriver
            logger.debug("Creating driver: sora (SoraApiDriver)")
            kwargs.pop("api_mode", None) # Clean kwargs
            kwargs.pop("headless", None) # Clean kwargs
            return SoraApiDriver(**kwargs)

        driver_class = self._drivers.get(platform)
        if not driver_class:
            available = list(self._drivers.keys())
            raise ValueError(
                f"Unknown platform: {platform}. "
                f"Available platforms: {available}"
            )

        logger.debug(f"Creating driver: {platform} ({driver_class.__name__})")
        
        # Clean up api_mode if it was passed but not handled above (e.g. for other drivers)
        kwargs.pop("api_mode", None) 
        return driver_class(**kwargs)

    def is_registered(self, platform: str) -> bool:
        """
        Check if platform is registered

        Args:
            platform: Platform name

        Returns:
            True if registered
        """
        return platform in self._drivers

    def get_registered_platforms(self) -> list[str]:
        """
        Get list of registered platforms

        Returns:
            List of platform names
        """
        return list(self._drivers.keys())


# Global factory instance
# Drivers will register themselves when imported
driver_factory = DriverFactory()


def register_default_drivers():
    """
    Register default drivers

    Call this on app startup to register all available drivers

    Currently supports:
    - Sora (OpenAI)
    - VEO3 (Google) - Coming soon
    """
    try:
        from app.core.drivers.sora.browser_driver import SoraBrowserDriver
        driver_factory.register("sora", SoraBrowserDriver)
        logger.info("Registered default drivers: sora")
    except ImportError as e:
        logger.warning(f"Failed to register SoraBrowserDriver: {e}")

    # Register VEO3 when available
    # try:
    #     from .veo3.driver import VEO3Driver
    #     driver_factory.register("veo3", VEO3Driver)
    # except ImportError:
    #     logger.warning("VEO3Driver not available")
