
import logging
import asyncio
import os
import time
import uuid
import aiohttp
from .base import BasePage
from ..selectors import SoraSelectors
from ..exceptions import PublicLinkNotFoundException

logger = logging.getLogger(__name__)

class SoraDownloadPage(BasePage):
    """
    [DEPRECATED] UI automation for Sora download functionality.

    [WARNING]  WARNING: This class uses Playwright UI automation and is DEPRECATED.
    The main workflow now downloads videos directly via URL using aiohttp
    after getting the download URL from API responses.

    This class is kept for backwards compatibility and debug purposes.
    For new code, download videos directly using the URL from get_drafts_api().
    """

    async def extract_video_url(self) -> str:
        """
        Extract video source URL from video element.
        Prioritizes 'raw' quality (full quality) over 'md' (medium).
        
        Returns:
            str: Video URL from videos.openai.com
            
        Raises:
            Exception: If no video element found
        """
        logger.info("Extracting video URL from video element...")
        
        # Get all video src URLs using JavaScript
        video_urls = await self.page.evaluate("""
            () => {
                const videos = document.querySelectorAll('video[src]');
                return Array.from(videos).map(v => v.src).filter(src => src && src.includes('videos.openai.com'));
            }
        """)
        
        if not video_urls:
            await self._snapshot("no_video_element")
            raise Exception("No video element with openai URL found")
        
        logger.info(f"Found {len(video_urls)} video URLs")
        
        # Prioritize raw quality (full quality without /drvs/md/)
        raw_url = None
        md_url = None
        
        for url in video_urls:
            if '/drvs/md/' not in url and '/raw' in url:
                raw_url = url
                logger.info(f"Found RAW quality URL: {url[:100]}...")
            elif '/drvs/md/' in url:
                md_url = url
                logger.info(f"Found MD quality URL: {url[:100]}...")
        
        # Use raw if available, otherwise md
        best_url = raw_url or md_url or video_urls[0]
        logger.info(f"Selected best video URL: {best_url[:100]}...")
        
        return best_url

    async def download_video_direct(self, output_dir: str = "data/downloads") -> tuple:
        """
        Download video directly from video element src.
        Uses browser cookies for authenticated download.
        
        Args:
            output_dir: Directory to save downloaded video
            
        Returns:
            tuple: (local_path, file_size)
            
        Raises:
            Exception: If download fails
        """
        os.makedirs(output_dir, exist_ok=True)
        
        # Extract video URL
        video_url = await self.extract_video_url()
        
        # Get cookies from browser context
        context = self.page.context
        cookies = await context.cookies()
        
        # Build cookie dict for aiohttp
        cookie_jar = aiohttp.CookieJar()
        for cookie in cookies:
            cookie_jar.update_cookies({cookie['name']: cookie['value']})
        
        # Generate unique filename
        timestamp = int(time.time())
        unique_id = uuid.uuid4().hex[:8]
        filename = f"video_{timestamp}_{unique_id}.mp4"
        save_path = os.path.join(output_dir, filename)
        
        logger.info(f"[DOWNLOAD]  Starting direct download: {video_url[:80]}...")
        
        try:
            # Download using aiohttp with cookies
            async with aiohttp.ClientSession() as session:
                # Set cookies from browser
                cookie_header = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
                
                headers = {
                    "Cookie": cookie_header,
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Referer": "https://sora.chatgpt.com/"
                }
                
                async with session.get(video_url, headers=headers) as response:
                    if response.status != 200:
                        raise Exception(f"Download failed with status {response.status}")
                    
                    # Stream download
                    total_size = 0
                    with open(save_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            f.write(chunk)
                            total_size += len(chunk)
            
            file_size = os.path.getsize(save_path)
            
            if file_size < 10000:  # Less than 10KB is probably an error
                os.remove(save_path)
                raise Exception(f"Downloaded file too small ({file_size} bytes), likely an error response")
            
            logger.info(f"[OK]  Direct download successful: {save_path} ({file_size:,} bytes)")
            return save_path, file_size
            
        except Exception as e:
            logger.error(f"[ERROR]  Direct download failed: {e}")
            # Clean up partial file
            if os.path.exists(save_path):
                os.remove(save_path)
            raise Exception(f"Direct download failed: {e}")

    async def get_public_link(self) -> str:
        """
        Click Public/Share button and retrieve the public link
        
        Returns:
            str: Public link (e.g., https://sora.chatgpt.com/share/xxx)
            
        Raises:
            PublicLinkNotFoundException: If public button not found or link not retrieved
        """
        logger.info("Attempting to get public link...")
        
        # Retry logic: Try to click and get link up to 3 times
        max_retries = 3
        for attempt in range(max_retries):
            logger.info(f"Attempt {attempt+1}/{max_retries} to retrieve public link...")
            
            # Close blocking stuff
            try:
                await self.page.keyboard.press("Escape")
                await asyncio.sleep(1)
            except:
                pass
            
            # TODO: We might need to import handle_blocking_overlays from base or verification page
            # Ideally base page should have this, or duplicate logic for now (KISS)
            
            # Find and click Public/Share button
            found = await self.find_first_visible(SoraSelectors.PUBLIC_BUTTON)
            if not found:
                if attempt == max_retries - 1:
                    await self._snapshot("public_button_not_found")
                    raise PublicLinkNotFoundException("Public/Share button not found")
                logger.warning("Public button not found, retrying...")
                await asyncio.sleep(2)
                continue
            
            _, btn = found
            
            if not await btn.is_enabled():
                logger.warning(f"Public/Share button found but DISABLED. Attempt {attempt+1}...")
                await asyncio.sleep(2)
                continue

            try:
                await btn.dispatch_event('click')
            except:
                await btn.evaluate("element => element.click()")
                 
            logger.info("Clicked Public/Share button (via dispatch_event)")
            
            # Check clipboard
            try:
                clipboard_text = await self.page.evaluate("async () => { try { return await navigator.clipboard.readText(); } catch (e) { return null; } }")
                if clipboard_text and "/share/" in clipboard_text:
                    return clipboard_text.strip()
            except:
                pass
            
            await asyncio.sleep(5)
            
            # Method 1: Input field
            for selector in SoraSelectors.PUBLIC_LINK_INPUT:
                try:
                    element = await self.page.query_selector(selector)
                    if element:
                        value = await element.get_attribute("value")
                        if value and "/share/" in value:
                             return value.strip()
                except:
                    continue
            
            # Method 2: Page content
            try:
                page_content = await self.page.content()
                import re
                match = re.search(r'https://sora\.chatgpt\.com/share/[a-zA-Z0-9-]+', page_content)
                if match:
                    return match.group(0).strip()
            except Exception:
                pass
            
            # End of attempt
            try:
                await self.page.keyboard.press("Escape")
                await asyncio.sleep(1)
            except:
                pass
        
        await self._snapshot("public_link_not_found")
        raise PublicLinkNotFoundException("Could not retrieve public link from UI after retries")
