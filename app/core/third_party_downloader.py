
"""
Third-party video downloader module
Downloads Sora videos from public links using external services (dyysy.com, soravdl.com)
to remove watermark and ensure correct video is downloaded
"""
import os
import time
import logging
import asyncio
import uuid
import datetime
from typing import Optional, Tuple
from playwright.async_api import Page, Download

logger = logging.getLogger(__name__)

# Enable debug screenshots
DEBUG_SCREENSHOTS = True
DEBUG_DIR = "data/debug_download"

class PublicLinkNotFoundException(Exception):
    """Raised when public link cannot be found or obtained"""
    pass

class ThirdPartyDownloaderError(Exception):
    """Raised when all third-party services fail"""
    pass

class ThirdPartyDownloader:
    """
    Downloads Sora videos from public links using third-party services
    Supports: dyysy.com (primary), soravdl.com (fallback)
    
    Concurrency: Uses class-level semaphore to limit concurrent requests
    """
    
    # Class-level semaphore (lazy-initialized)
    _semaphore = None
    _max_concurrent = 2 # Lower concurrency for downloads
    
    def __init__(self):
        # Configure logging to file
        fh = logging.FileHandler('data/downloader.log')
        fh.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        logger.addHandler(fh)
        logger.setLevel(logging.INFO)

        self.services = [
            {
                "name": "soravdl",
                "url": "https://soravdl.com/",
                "download_method": self._download_via_soravdl
            },
            {
                "name": "dyysy",
                "url": "https://dyysy.com/",
                "download_method": self._download_via_dyysy
            }
        ]

    async def _debug_screenshot(self, page: Page, name: str):
        """Take debug screenshot with timestamp."""
        if not DEBUG_SCREENSHOTS:
            return
        try:
            os.makedirs(DEBUG_DIR, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%H%M%S")
            path = f"{DEBUG_DIR}/{timestamp}_{name}.png"
            await page.screenshot(path=path)
            logger.info(f"📸 Debug download screenshot: {path}")
        except Exception as e:
            logger.warning(f"Failed to take screenshot: {e}")

    @classmethod
    def _get_semaphore(cls):
        """Lazy-init semaphore to avoid event loop issues"""
        if cls._semaphore is None:
            cls._semaphore = asyncio.Semaphore(cls._max_concurrent)
        return cls._semaphore
    
    async def download_from_public_link(
        self,
        page: Page,
        public_link: str,
        output_dir: str = "data/downloads"
    ) -> Tuple[str, int]:
        """
        Download video from Sora public link via third-party services
        """
        os.makedirs(output_dir, exist_ok=True)
        
        logger.info(f"⬇️ Starting download for: {public_link}")

        # Use class-level semaphore
        async with self._get_semaphore():
            # Try each service in order
            last_error = None
            for service in self.services:
                try:
                    logger.info(f"Attempting download via {service['name']}...")
                    local_path, file_size = await service["download_method"](
                        page, public_link, output_dir
                    )
                    logger.info(f"✅ Successfully downloaded via {service['name']}: {local_path}")
                    return local_path, file_size

                except Exception as e:
                    logger.warning(f"❌ {service['name']} failed: {e}")
                    last_error = e
                    continue

            # All services failed
            raise ThirdPartyDownloaderError(
                f"All third-party services failed. Last error: {last_error}"
            )

    async def _download_via_dyysy(
        self,
        page: Page,
        public_link: str,
        output_dir: str
    ) -> Tuple[str, int]:
        """Download video using dyysy.com"""
        try:
            logger.info("Navigating to dyysy.com...")
            await page.goto("https://dyysy.com/", wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(2)
            await self._debug_screenshot(page, "dyysy_00_loaded")

            # Find and fill input field (Verified: input#urlInput)
            input_selector = "input#urlInput"
            if not await page.is_visible(input_selector):
                 # Fallback just in case
                 input_selector = "#url"
            
            await page.fill(input_selector, public_link)
            logger.info(f"Filled public link into input: {input_selector}")
            await self._debug_screenshot(page, "dyysy_01_filled")

            # Click download/submit button (Verified: button#parseBtn)
            submit_selector = "button#parseBtn"
            await page.click(submit_selector)
            logger.info(f"Clicked button: {submit_selector}")

            # Wait for processing and download link
            logger.info("Waiting for processing (dyysy)...")
            await asyncio.sleep(3)
            await self._debug_screenshot(page, "dyysy_02_processing")
            
            # Look for download button/link
            # Dyysy usually shows a new download button after processing
            # We look for the specific result container or download button
            try:
                 # Wait for the download group to appear
                 await page.wait_for_selector(".download-group", timeout=15000)
            except:
                 pass

            # Try to find the download link
            dl_selectors = [
                "a[href*='.mp4']", 
                "a:has-text('Download Video')",
                ".download-group a"
            ]
            
            download_trigger = None
            for sel in dl_selectors:
                if await page.is_visible(sel):
                    download_trigger = sel
                    break
            
            if not download_trigger:
                 await self._debug_screenshot(page, "dyysy_failed_no_link")
                 raise Exception("Download link not found after processing")

            # Setup download handler
            logger.info(f"Found download trigger: {download_trigger}")
            download_path = await self._handle_download(
                page, 
                output_dir, 
                timeout=60, 
                trigger_fn=lambda: page.click(download_trigger)
            )
            
            if not download_path:
                 raise Exception("Download failed to start")

            file_size = os.path.getsize(download_path)
            return download_path, file_size

        except Exception as e:
            await self._debug_screenshot(page, "dyysy_exception")
            raise Exception(f"dyysy.com download failed: {e}")

    async def _download_via_soravdl(
        self,
        page: Page,
        public_link: str,
        output_dir: str
    ) -> Tuple[str, int]:
        """
        Download video using soravdl.com
        """
        try:
            logger.info("Navigating to soravdl.com...")
            await page.goto("https://soravdl.com/", wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(2)
            await self._debug_screenshot(page, "soravdl_00_loaded")

            # Find and fill input field (Verified: input#video-url)
            input_selector = "input#video-url"
            await page.fill(input_selector, public_link)
            logger.info(f"Filled public link into input: {input_selector}")
            await self._debug_screenshot(page, "soravdl_01_filled")

            # Click download button (Verified: button#download-btn)
            submit_selector = "button#download-btn"
            await page.click(submit_selector)
            logger.info(f"Clicked button: {submit_selector}")

            # Wait for processing
            await asyncio.sleep(5)
            await self._debug_screenshot(page, "soravdl_02_processing")

            # Handle download
            # For soravdl, often the button becomes "Download Video" or new element appears
            download_path = None
            
            # Try to find the result download button
            result_selectors = [
                "a[download]", 
                "a:has-text('Download Video')", 
                ".download-result a",
                "button:has-text('Download Video')"
            ]
            
            download_trigger = None
            for sel in result_selectors:
                if await page.is_visible(sel, timeout=5000):
                    download_trigger = sel
                    break
            
            if not download_trigger:
                 await self._debug_screenshot(page, "soravdl_failed_no_link")
                 raise Exception("Download link not found after processing")

            logger.info(f"Found download trigger: {download_trigger}")
            download_path = await self._handle_download(
                page, 
                output_dir, 
                timeout=60, 
                trigger_fn=lambda: page.click(download_trigger)
            )

            if not download_path:
                 # Check if it auto-downloads or we missed it
                 await self._debug_screenshot(page, "soravdl_failed_no_link")
                 raise Exception("Download did not start within timeout")

            file_size = os.path.getsize(download_path)
            return download_path, file_size

        except Exception as e:
            await self._debug_screenshot(page, "soravdl_exception")
            raise Exception(f"soravdl.com download failed: {e}")

    async def _handle_download(
        self,
        page: Page,
        output_dir: str,
        timeout: int = 60,
        trigger_fn: callable = None
    ) -> Optional[str]:
        """
        Handle browser download event and save file
        """
        download_path = None
        download_obj = None

        async def on_download(download: Download):
            nonlocal download_path, download_obj
            download_obj = download
            
            # Use timestamp + UUID to prevent filename collision
            timestamp = int(time.time())
            unique_id = uuid.uuid4().hex[:8]
            filename = f"video_{timestamp}_{unique_id}.mp4"
            save_path = os.path.join(output_dir, filename)

            logger.info(f"📥 Download started: {download.suggested_filename}")
            try:
                await download.save_as(save_path)
                logger.info(f"✅ Download saved to: {save_path}")
                download_path = save_path
            except Exception as e:
                logger.error(f"❌ Failed to save download: {e}")

        page.on("download", on_download)

        try:
            # Trigger the download action if provided
            if trigger_fn:
                if asyncio.iscoroutinefunction(trigger_fn):
                    await trigger_fn()
                else:
                    await trigger_fn
            
            # Wait for download to start and complete
            start_time = time.time()
            while not download_path and (time.time() - start_time) < timeout:
                await asyncio.sleep(1)
                
        finally:
            page.remove_listener("download", on_download)
            
        return download_path
