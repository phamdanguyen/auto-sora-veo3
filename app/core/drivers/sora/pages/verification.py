
import logging
import asyncio
import re
from .base import BasePage
from ..selectors import SoraSelectors
from ..exceptions import VerificationRequiredException

logger = logging.getLogger(__name__)

class SoraVerificationPage(BasePage):
    """
    [PARTIALLY DEPRECATED] UI automation for verification and credit checking.

    ⚠️ Some methods are still used during login flow:
    - check_quota_exhausted() - used to detect verification requirements
    - handle_verification_flow() - used to handle verification during login

    However, credit checking is now done via API:
    - Use get_credits_api() in SoraDriver instead of check_credits()

    For general status polling, use SoraDriver.api_only() mode.
    """

    async def check_quota_exhausted(self) -> bool:
        """Check if account has run out of video generations OR requires verification"""
        # 1. Check Quota
        for indicator in SoraSelectors.QUOTA_EXHAUSTED_INDICATORS:
            try:
                if await self.page.is_visible(indicator, timeout=1000):
                    logger.warning(f"Quota exhausted indicator found: {indicator}")
                    return True
            except:
                continue

        # 2. Check Verification/Checkpoint
        for indicator in SoraSelectors.VERIFICATION_INDICATORS:
             try:
                 if await self.page.is_visible(indicator, timeout=1000):
                     logger.warning(f"Verification indicator found: {indicator}")
                     await self._snapshot("verification_detected")
                     raise VerificationRequiredException(f"Verification required: {indicator}")
             except VerificationRequiredException:
                 raise
             except:
                 continue
                 
        return False

    async def check_credits(self) -> int:
        """
        Check available video credits by navigating to settings or scanning page.
        Returns:
            int: Number of credits remaining, or -1 if could not determine.
        """
        logger.info("Checking credits...")
        
        credits = -1
        
        # Method 1: Check via Settings UI
        try:
             # Click Settings button
             logger.info("Clicking Settings button...")
             await self.page.click("button[aria-label='Settings']")
             await asyncio.sleep(2)
             
             # Click Settings menu item
             await self.page.click("div[role='menuitem']:has-text('Settings')")
             await asyncio.sleep(3)
             
             # Click Usage tab
             usage_btn = await self.page.query_selector("button[role='tab'][id*='trigger-usage']")
             if usage_btn:
                 await usage_btn.click()
             else:
                 await self.page.click("button:has-text('Usage')")
             await asyncio.sleep(2)
             
             # Get page content
             content = await self.page.content()
             
             for pattern in SoraSelectors.CREDIT_TEXT_PATTERNS:
                 match = re.search(pattern, content, re.IGNORECASE)
                 if match:
                     credits = int(match.group(1))
                     logger.info(f"💰 Found credits UI: {credits}")
                     break
                     
             # Close dialog
             await self.page.keyboard.press("Escape")
             await asyncio.sleep(0.5)
             
        except Exception as e:
            logger.warning(f"UI Credit check failed: {e}")
            
        # Method 2: Direct URL Fallback
        if credits == -1:
            try:
                logger.info("Trying direct Settings URL...")
                await self.page.goto("https://sora.chatgpt.com/settings")
                await asyncio.sleep(3)
                
                content = await self.page.content()
                for pattern in SoraSelectors.CREDIT_TEXT_PATTERNS:
                     match = re.search(pattern, content, re.IGNORECASE)
                     if match:
                         credits = int(match.group(1))
                         logger.info(f"💰 Found credits DirectURL: {credits}")
                         break
                         
                await self.page.goto("https://sora.chatgpt.com")
                
            except Exception as e:
                 logger.error(f"Direct URL Credit check failed: {e}")

        return credits

    async def wait_for_video_completion(self, max_wait: int = 300) -> bool:
        """
        Wait for video generation to complete by checking UI indicators
        """
        logger.info(f"Waiting for video completion (max {max_wait}s)...")
        start_time = asyncio.get_event_loop().time()
        check_interval = 4
        
        while (asyncio.get_event_loop().time() - start_time) < max_wait:
            for indicator in SoraSelectors.VIDEO_COMPLETION_INDICATORS:
                try:
                    if await self.page.is_visible(indicator, timeout=1000):
                        logger.info(f"✅ Video completion detected: {indicator}")
                        return True
                except:
                    continue
            await asyncio.sleep(check_interval)
        
        logger.warning(f"⏱️ Video completion timeout after {max_wait}s")
        return False

    async def verify_video_by_prompt(self, expected_prompt: str, similarity_threshold: float = 0.5) -> bool:
        """
        Verify video belongs to current account by matching prompt/description.
        (Placeholder for logic previously partially hidden in creation.py)
        """
        # Logic to extract video description and compare
        # For now simply return True or implement simple check if needed
        return True
