import logging
import asyncio
from .base import BasePage
from ..selectors import SoraSelectors

logger = logging.getLogger(__name__)

class SoraDraftsPage(BasePage):
    """
    [DEPRECATED] UI automation for Sora drafts page.

    ⚠️ WARNING: This class uses Playwright UI automation and is DEPRECATED.
    The main workflow now uses API-only methods in SoraDriver:
    - get_drafts_api() for retrieving drafts
    - post_video_api() for posting videos

    This class is kept for backwards compatibility and debug purposes.
    For new code, use SoraDriver.api_only() mode instead.
    """

    async def navigate_to_drafts(self):
        """Navigate to the Drafts page."""
        url = "https://sora.chatgpt.com/drafts"
        logger.info(f"📍 Navigating to drafts: {url}")
        await self.page.goto(url)
        await self.page.wait_for_load_state("domcontentloaded")
        await asyncio.sleep(3)

    async def post_latest_draft(self):
        """
        Selects the latest draft video and clicks Post.
        """
        logger.info("📍 Selecting latest draft video...")
        
        # User defined selector for the latest video thumbnail/container in drafts
        # <div class="absolute left-0 top-0 h-full w-full">...</div>
        video_container_sel = "div.absolute.left-0.top-0.h-full.w-full"
        
        try:
            # Wait for grid to load
            await self.page.wait_for_selector(video_container_sel, timeout=10000)
            
            # Click the first one (latest)
            # We might need to be careful if there are multiple, query_selector_all and take first?
            # Usually strict mode might fail if multiple. 
            # Let's use first()
            await self.page.locator(video_container_sel).first.click()
            logger.info("✅ Clicked latest draft video")
            await asyncio.sleep(2)
            
            # Click Post button
            # User provided class: <button ...>Post</button>
            # We can use text selector for robustness
            post_btn_sel = "button:has-text('Post')"
            
            if await self.page.is_visible(post_btn_sel):
                await self.page.click(post_btn_sel)
                logger.info("✅ Clicked Post button")
                await asyncio.sleep(5) # Wait for post action
            else:
                raise Exception("Post button not found after selecting draft")
                
        except Exception as e:
            logger.error(f"❌ Failed to post draft: {e}")
            raise

    async def get_latest_video_id_from_profile(self) -> str:
        """
        Navigates to profile, selects latest video, and extracts ID.
        """
        logger.info("📍 Retrieving video ID from profile...")
        
        # Navigate to profile
        await self.page.goto("https://sora.chatgpt.com/profile")
        await asyncio.sleep(5)
        
        # Select first video in grid
        # Assuming similar grid structure or re-using SoraSelectors.GRID_ITEM
        try:
            grid_item = "a[href*='/video/']"
            await self.page.wait_for_selector(grid_item, timeout=10000)
            
            # Get the href of the first item directly to extract ID
            first_video_link = self.page.locator(grid_item).first
            href = await first_video_link.get_attribute("href")
            
            if href and "/video/" in href:
                # Extract ID: /video/uuid
                video_id = href.split("/video/")[-1]
                logger.info(f"✅ Found Video ID: {video_id}")
                return video_id
            else:
                raise Exception("Could not extract ID from video link")
                
        except Exception as e:
            logger.error(f"❌ Failed to get video ID from profile: {e}")
            raise

    async def count_drafts(self) -> int:
        """
        Counts the number of video items in the Drafts page.
        Returns 0 if no drafts found.
        """
        # Ensure we are on drafts page
        if "sora.chatgpt.com/drafts" not in self.page.url:
            await self.navigate_to_drafts()
        else:
            # Reload to ensure fresh data
            await self.page.reload()
            await self.page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(3)

        # Fallback to Standard Selectors
        from ..selectors import SoraSelectors
        
        max_count = 0
        for selector in SoraSelectors.DRAFT_ITEM:
             items = await self.page.query_selector_all(selector)
             if items:
                 count = len(items)
                 if count > max_count:
                     max_count = count
                     logger.info(f"🔢 Counted {count} drafts using selector: {selector}")
        
        if max_count == 0:
            logger.info("🔢 Counted 0 drafts (no items found)")
            
        return max_count
