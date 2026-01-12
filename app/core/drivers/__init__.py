"""
Video Generation Drivers Package

Provides abstraction layer for video generation platforms

Implements SOLID principles:
- SRP: Each driver one responsibility
- OCP: Easy to add new drivers
- LSP: All drivers substitutable
- ISP: Focused interfaces
- DIP: Depend on abstractions

Usage:
    from app.core.drivers import driver_factory

    # Create driver
    driver = driver_factory.create_driver(
        "sora",
        access_token="...",
        device_id="..."
    )

    # Use driver
    await driver.start()
    result = await driver.generate_video(
        prompt="A cat playing piano",
        duration=5,
        aspect_ratio="16:9"
    )
    await driver.stop()
"""

from .abstractions import (
    VideoGenerationDriver,
    BrowserBasedDriver,
    APIOnlyDriver,
    VideoResult,
    CreditsInfo,
    UploadResult,
    VideoData,
    PendingTask
)
from .factory import (
    DriverFactory,
    driver_factory,
    register_default_drivers
)

# Auto-register default drivers
register_default_drivers()

__all__ = [
    # Abstractions
    "VideoGenerationDriver",
    "BrowserBasedDriver",
    "APIOnlyDriver",

    # Data classes
    "VideoResult",
    "CreditsInfo",
    "UploadResult",
    "VideoData",
    "PendingTask",

    # Factory
    "DriverFactory",
    "driver_factory",
    "register_default_drivers"
]
