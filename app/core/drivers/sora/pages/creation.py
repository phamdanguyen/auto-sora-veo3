import logging
import asyncio
import sys
import re
from typing import Optional, List, Tuple
from playwright.async_api import Page, ElementHandle
from .base import BasePage
from ..selectors import SoraSelectors
from ..exceptions import QuotaExhaustedException

logger = logging.getLogger(__name__)

class SoraCreationPage(BasePage):
    """
    [DEPRECATED] UI automation for Sora video creation page.

    [WARNING]  WARNING: This class uses Playwright UI automation and is DEPRECATED.
    The main workflow now uses API-only methods in SoraDriver:
    - generate_video_api() for video generation
    - wait_for_completion_api() for polling
    - get_drafts_api() for checking drafts

    This class is kept for:
    - Backwards compatibility
    - Debug/testing purposes
    - Login flow support (which still requires browser)

    For new code, use SoraDriver.api_only() mode instead.
    """

    async def _snapshot(self, name: str):
        try:
            path = f"data/debug_login/{name}.png"
            await self.page.screenshot(path=path)
        except Exception as e:
            logger.warning(f"Failed to take snapshot {name}: {e}")

    async def _dump_html(self, name: str):
        try:
            path = f"data/debug_login/{name}.html"
            content = await self.page.content()
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            logger.warning(f"Failed to dump HTML {name}: {e}")

    async def handle_blocking_popups(self):
        """
        Aggressively closes known blocking popups.
        """
        # CSS/JS Suppression
        await self._suppress_popups_js()
        
        # Check specific popup text
        for txt_ind in SoraSelectors.POPUP_TEXTS:
            if await self.page.is_visible(txt_ind, timeout=1000):
                logger.info(f"Popup detected ({txt_ind}). Attempting to close...")
                
                # Try close buttons
                found = await self.find_first_visible(SoraSelectors.POPUP_CLOSE_BTNS)
                if found:
                    _, btn = found
                    await btn.click()
                    await asyncio.sleep(1)
                else:
                    # Click outside or Escape
                    await self.page.keyboard.press("Escape")
    
    async def _suppress_popups_js(self):
        try:
            # We inject keywords to nuke elements containing them
            js_code = """(keywords) => {
                try {
                    function nuke(text) {
                        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
                        let node;
                        while (node = walker.nextNode()) {
                            if (node.textContent.includes(text)) {
                                let current = node.parentElement;
                                let depth = 0;
                                while (current && depth < 10) {
                                    const style = window.getComputedStyle(current);
                                    if (style.position === 'fixed' || style.position === 'absolute' || current.getAttribute('role') === 'dialog') {
                                        console.log('Nuking popup with text:', text);
                                        current.style.display = 'none';
                                        current.style.visibility = 'hidden';
                                        // Also try to remove pointer-events to prevent blocking
                                        current.style.pointerEvents = 'none';
                                        break;
                                    }
                                    current = current.parentElement;
                                    depth++;
                                }
                            }
                        }
                    }
                    keywords.forEach(k => nuke(k));
                } catch (e) {
                     console.error("Popup nuke failed", e);
                }
            }"""
            await self.page.evaluate(js_code, SoraSelectors.POPUP_KEYWORDS)
        except Exception as e:
            logger.debug(f"JS Popup suppression benign error: {e}")

    async def human_type(self, selector: str, text: str):
        """Simulate human typing with random delays"""
        import random
        try:
            # Focus element
            await self.page.click(selector)
            
            # Clear existing content using keyboard (more robust than fill(""))
            # Mac matches 'Meta', Windows/Linux uses 'Control'
            modifier = "Meta" if sys.platform == "darwin" else "Control"
            await self.page.keyboard.press(f"{modifier}+A")
            await self.page.keyboard.press("Backspace")
            
            # Type characters with varying delays
            for char in text:
                await self.page.keyboard.type(char)
                # Random delay 20ms to 100ms
                delay = random.uniform(0.02, 0.1) 
                await asyncio.sleep(delay)
                
            return True
        except Exception as e:
            logger.warning(f"Human type failed: {e}")
            return False

    async def fill_prompt(self, prompt: str):
        logger.info("Attempting to fill prompt...")
        await self.handle_blocking_popups()
        
        found = await self.find_first_visible(SoraSelectors.PROMPT_INPUT)
        if not found:
             # Retry once with aggressive cleanup
             logger.warning("Prompt input not found initially. Retrying with popup cleanup...")
             await self.handle_blocking_popups()
             await asyncio.sleep(2)
             found = await self.find_first_visible(SoraSelectors.PROMPT_INPUT)
             
        if found:
            sel, el = found
            logger.info(f"Found prompt input: {sel}")
            
            # Instant JS Injection (Ninja V2)
            # This bypasses typing simulation for near-instant submission while keeping PoW valid
            try:
                logger.info("⚡ Executing Instant Prompt Injection...")
                await self.page.evaluate("""(data) => {
                    const textarea = document.querySelector(data.selector);
                    if (textarea) {
                        // React often tracks value via setter override
                        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
                        nativeInputValueSetter.call(textarea, data.prompt);
                        
                        textarea.dispatchEvent(new Event('input', { bubbles: true }));
                        textarea.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                }""", {"selector": sel, "prompt": prompt})
                
                # Double check with Playwright fill if JS failed (Safety Net)
                await asyncio.sleep(0.3)
                if await el.input_value() != prompt:
                    logger.warning("JS Injection partial fail, using fill() fallback...")
                    await el.fill(prompt)
                
                logger.info("[OK]  Prompt injected successfully.")
            except Exception as e:
                logger.warning(f"JS Injection failed: {e}. Falling back to fill...")
                await el.fill(prompt)
            
            # Wait a bit for validation to trigger
            await asyncio.sleep(0.5)
        else:
            await self._snapshot("no_prompt_input")
            raise Exception("Could not find prompt input field")



    async def handle_blocking_overlay(self):
        """Detect and close blocking overlays/dialogs"""
        try:
            # Common overlay selectors
            overlays = [
                ".z-dialog", 
                "[role='dialog']", 
                "div[class*='overlay']",
                "div[class*='modal']"
            ]
            
            for selector in overlays:
                if await self.page.is_visible(selector, timeout=500):
                    logger.warning(f"Blocking overlay detected: {selector}")
                    await self._snapshot("blocking_overlay_detected")
                    
                    # Try to get text content to understand what it is
                    try:
                        el = await self.page.query_selector(selector)
                        text = await el.text_content()
                        logger.info(f"Overlay text: {text[:100]}...")
                    except:
                        pass

                    # Attempt 1: Press Escape
                    logger.info("Attempting to close overlay via Escape key...")
                    await self.page.keyboard.press("Escape")
                    await asyncio.sleep(1)
                    
                    if not await self.page.is_visible(selector, timeout=500):
                        logger.info("Overlay closed via Escape.")
                        return

                    # Attempt 2: Click Close button
                    close_btns = [
                        f"{selector} button[aria-label='Close']",
                        f"{selector} button:has-text('Close')",
                        f"{selector} button:has-text('Maybe later')",
                        f"{selector} button:has-text('X')",
                        "button[class*='close']"
                    ]
                    
                    for btn_sel in close_btns:
                        if await self.click_if_visible(btn_sel):
                            logger.info(f"Clicked close button: {btn_sel}")
                            await asyncio.sleep(1)
                            if not await self.page.is_visible(selector, timeout=500):
                                return

                    logger.warning("Failed to dismiss overlay.")
                    await self._snapshot("overlay_dismiss_fail")
        except Exception as e:
            logger.warning(f"Error handling overlay: {e}")

    async def check_is_generating(self) -> bool:
        """
        Check if any video is currently generating/processing in the list.
        Returns true if indicators found.
        """
        try:
            for ind in SoraSelectors.VIDEO_GENERATING_INDICATORS:
                if await self.page.is_visible(ind, timeout=1000):
                    logger.info(f"[OK]  Found generating video indicator: {ind}")
                    return True
        except Exception as e:
            logger.debug(f"Generation check failed (benign): {e}")
        return False

    async def click_generate(self, prompt: str = "") -> bool:
        """
        Robustly click Generate button.
        Returns:
            bool: True if submission was successful (based on UI state change).
        """
        await self.handle_blocking_popups()
        await self.handle_blocking_overlay()

        found = await self.find_first_visible(SoraSelectors.GENERATE_BTN)
        if found:
            _, btn = found
            await self._snapshot("debug_before_submission")

            if await btn.is_disabled():
                logger.info("Generate button is disabled, waiting...")
                try:
                    await btn.wait_for_element_state("enabled", timeout=10000)
                except Exception:
                    logger.warning("Generate button remained disabled after wait.")
                    await self._snapshot("generate_btn_disabled")
                    raise Exception("Generate button is disabled (invalid prompt?)")

            # === FAIL FAST: Check for Verification Dialog BEFORE Action ===
            # User specifically requested this strategy for "Verify your phone number"
            for indicator in SoraSelectors.VERIFICATION_INDICATORS:
                if await self.page.is_visible(indicator, timeout=500):
                     logger.error(f"[ERROR]  FAIL FAST: Verification verification detected: {indicator}")
                     await self._snapshot("fail_fast_verification_start")
                     from ..exceptions import VerificationRequiredException
                     raise VerificationRequiredException(f"Verification required (Fail Fast): {indicator}")

            # === PRIMARY METHOD: ENTER KEY ===
            logger.info("Attempting submission via ENTER key (Primary)...")
            try:
                prompt_input = await self.find_first_visible(SoraSelectors.PROMPT_INPUT)
                if prompt_input:
                    _, el = prompt_input
                    await el.click() # Focus
                    await asyncio.sleep(0.5)
                    await self.page.keyboard.press("Enter")
                    logger.info("Sent ENTER key.")
                    await asyncio.sleep(1)
                    await self._snapshot("debug_after_enter_1s")

                    # Verify
                    for _ in range(5):
                        await asyncio.sleep(1)
                        if not await btn.is_visible():
                             logger.info("[OK]  ENTER key success: Generate button disappeared")
                             return True
                        if await btn.is_disabled():
                             logger.info("[OK]  ENTER key success: Generate button disabled")
                             return True
                        btn_text = await btn.text_content()
                        if btn_text and ("generat" in btn_text.lower() or "creating" in btn_text.lower()):
                             logger.info("[OK]  ENTER key success: Button text changed")
                             return True
                    logger.warning("ENTER key did not trigger generation.")
                else:
                    logger.warning("Prompt input not found for Enter key.")
            except Exception as e:
                logger.warning(f"Enter key submission failed: {e}")

            # === FAIL FAST: Check verification after Enter ===
            for indicator in SoraSelectors.VERIFICATION_INDICATORS:
                if await self.page.is_visible(indicator, timeout=500):
                     logger.error(f"[ERROR]  FAIL FAST: Verification detected after Enter: {indicator}")
                     await self._snapshot("fail_fast_verification_enter")
                     from ..exceptions import VerificationRequiredException
                     raise VerificationRequiredException(f"Verification required (After Enter): {indicator}")

            # === FALLBACK METHOD: CLICKING ===
            logger.info("Falling back to Click method...")
            try:
                if await self.check_is_generating():
                     logger.info("[OK]  Generation already in progress.")
                     return True

                await self.handle_blocking_overlay()
                found_retry = await self.find_first_visible(SoraSelectors.GENERATE_BTN)
                if not found_retry:
                    raise Exception("Generate button not found")
                _, btn_current = found_retry

                await btn_current.click(timeout=3000)
                logger.info("Clicked Generate button.")
                await asyncio.sleep(5)
                await self._snapshot("debug_after_click")

                if await self.check_is_generating():
                     logger.info("[OK]  Generation confirmed.")
                     return True

                # Check errors (Quota/etc handled by caller primarily, but good to check)
                
                # Check button state change
                try:
                    if not await btn_current.is_visible() or await btn_current.is_disabled():
                         logger.info("[OK]  Click success: Button state changed.")
                         return True
                except:
                    pass

                logger.warning("[WARNING]  Click did not produce clear success indicators. Assuming success.")
                return True

            except Exception as e:
                logger.error(f"Click method failed: {e}")
                raise Exception(f"Failed to submit video request: {e}")
        else:
            await self._snapshot("debug_no_gen_btn")
            try:
                # Focus prompt input
                prompt_input = await self.find_first_visible(SoraSelectors.PROMPT_INPUT)
                if prompt_input:
                    _, el = prompt_input
                    await el.click() # Focus
                    await asyncio.sleep(0.5)
                    await self.page.keyboard.press("Enter")
                    logger.info("Sent ENTER key.")
                    
                    # Snapshot after Enter
                    await asyncio.sleep(1)
                    await self._snapshot("debug_after_enter_1s")

                    # Verify if it worked (wait up to 5s for state change)
                    for _ in range(5):
                        await asyncio.sleep(1)
                        
                        # Check button state
                        if not await btn.is_visible():
                             logger.info("[OK]  ENTER key success: Generate button disappeared")
                             return True
                        
                        if await btn.is_disabled():
                             logger.info("[OK]  ENTER key success: Generate button disabled")
                             return True

                        # Check button text
                        btn_text = await btn.text_content()
                        if btn_text and ("generat" in btn_text.lower() or "creating" in btn_text.lower()):
                             logger.info("[OK]  ENTER key success: Button text changed to 'Generating'")
                             return True
                             
                    logger.warning("ENTER key did not trigger generation (no state change).")
                    await self._snapshot("debug_enter_failed")
                else:
                    logger.warning("Prompt input not found for Enter key submission.")
            except Exception as e:
                logger.warning(f"Enter key submission failed: {e}")

            # === FALLBACK METHOD: CLICKING ===
            logger.info("Falling back to Click method...")

            # Single click attempt - no aggressive retry to prevent double generation
            try:
                # SAFETY: Check if generation already started (from delayed Enter)
                if await self.check_is_generating():
                     logger.info("[OK]  Generation already in progress (detected indicator).")
                     return True

                # Check for overlay FIRST
                await self.handle_blocking_overlay()

                # Find button
                found_retry = await self.find_first_visible(SoraSelectors.GENERATE_BTN)
                if not found_retry:
                    logger.warning("Generate button not found for click fallback.")
                    raise Exception("Generate button not found")
                _, btn_current = found_retry

                # Check if button is disabled (might mean already generating)
                try:
                    is_disabled = await btn_current.is_disabled()
                    if is_disabled:
                        # Check if already generating
                        if await self.check_is_generating():
                             logger.info("[OK]  Generation confirmed (button disabled, indicators visible).")
                             return True
                        # Otherwise button might be disabled for other reasons, wait briefly
                        try:
                            await btn_current.wait_for_element_state("enabled", timeout=3000)
                        except:
                            logger.warning("Button disabled and could not enable. May already be processing.")
                            return True
                except Exception as e:
                    logger.debug(f"Disabled check failed: {e}")

                # Click button
                await btn_current.click(timeout=3000)
                logger.info("Clicked Generate button.")

                # Wait for UI to update
                await asyncio.sleep(5)
                await self._snapshot("debug_after_click")

                # Check for success indicators
                if await self.check_is_generating():
                     logger.info("[OK]  Generation confirmed (indicator visible after click).")
                     return True

                # Check for errors
                error_el = await self.page.query_selector("div[class*='error'], [role='alert'], .text-red-500")
                if error_el and await error_el.is_visible():
                    text = await error_el.text_content()
                    if text and text.strip():
                        logger.warning(f"Error after generate: {text}")
                        if "quota" in text.lower() or "limit" in text.lower():
                            raise QuotaExhaustedException(f"Quota exhausted: {text}")
                        raise Exception(f"Submission error: {text}")

                # Check for verification requirements
                from ..exceptions import VerificationRequiredException
                for indicator in SoraSelectors.VERIFICATION_INDICATORS:
                    if await self.page.is_visible(indicator):
                         logger.warning(f"Verification required after submit: {indicator}")
                         await self._snapshot("verification_after_submit")
                         raise VerificationRequiredException(f"Verification required: {indicator}")

                # Check button state change
                try:
                    is_disabled = await btn_current.is_disabled()
                    is_visible = await btn_current.is_visible()

                    if not is_visible or is_disabled:
                         logger.info("[OK]  Click success: Button state changed (hidden or disabled).")
                         return True

                    btn_text = await btn_current.text_content()
                    if btn_text and ("generat" in btn_text.lower() or "creating" in btn_text.lower()):
                         logger.info("[OK]  Click success: Button text indicates generating.")
                         return True
                except:
                    # Button detached/gone likely means success
                    logger.info("[OK]  Click success: Button element detached.")
                    return True

                # If we reach here, click might have failed but avoid retry
                logger.warning("[WARNING]  Click did not produce clear success indicators. Assuming success to prevent double-generation.")
                return True

            except QuotaExhaustedException:
                raise
            except Exception as e:
                logger.error(f"Click method failed: {e}")
                await self._snapshot("debug_click_failure")
                raise Exception(f"Failed to submit video request: {e}")
            


    async def wait_for_video_completion(self, max_wait: int = 300) -> bool:
        """
        Wait for video generation to complete by checking UI indicators
        
        Args:
            max_wait: Maximum seconds to wait
            
        Returns:
            bool: True if video completed, False if timeout
        """
        logger.info(f"Waiting for video completion (max {max_wait}s)...")
        start_time = asyncio.get_event_loop().time()
        
        check_interval = 4  # Check every 4 seconds
        
        while (asyncio.get_event_loop().time() - start_time) < max_wait:
            # Check for completion indicators
            for indicator in SoraSelectors.VIDEO_COMPLETION_INDICATORS:
                try:
                    if await self.page.is_visible(indicator, timeout=1000):
                        logger.info(f"[OK]  Video completion detected: {indicator}")
                        return True
                except:
                    continue
            
            await asyncio.sleep(check_interval)
        
        logger.warning(f"⏱️ Video completion timeout after {max_wait}s")
        return False

    async def get_public_link(self, max_retries=10) -> str:
        """
        Click Public/Share button and retrieve the public link
        
        Returns:
            str: Public link (e.g., https://sora.chatgpt.com/share/xxx)
            
        Raises:
            PublicLinkNotFoundException: If public button not found or link not retrieved
        """
        from app.core.third_party_downloader import PublicLinkNotFoundException
        
        check_interval = 4  # Check every 4 seconds
        
        logger.info("Attempting to get public link...")
        
        # Refresh page to ensure UI is interactive (fix for stale Share button)
        try:
            logger.info("Refreshing page to ensure fresh UI state...")
            await self.page.reload(wait_until="domcontentloaded")
            await asyncio.sleep(3)
        except Exception as e:
             logger.warning(f"Page reload failed (benign): {e}")

        # Retry logic: Try to click and get link up to max_retries times
        # max_retries is now an argument
        for attempt in range(max_retries):
            # Refresh every 3 attempts (starting from attempt 3, e.g. 3, 6, 9)
            if attempt > 0 and attempt % 3 == 0:
                 logger.info(f"[MONITOR]  Reloading page to refresh UI state (Attempt {attempt+1})...")
                 try:
                     await self.page.reload(wait_until="domcontentloaded")
                     await asyncio.sleep(4)
                 except:
                     pass
            
            logger.info(f"Attempt {attempt+1}/{max_retries} to retrieve public link...")
            
            # Close blocking stuff
            try:
                await self.page.keyboard.press("Escape")
                await asyncio.sleep(1)
            except:
                pass
                
            await self.handle_blocking_popups()
            await self.handle_blocking_overlay()
            
            # Find and click Share button
            found = await self.find_first_visible(SoraSelectors.SHARE_BUTTON)
            
            # FALLBACK: Check for Menu -> Share
            if not found:
                 logger.info("Share button not found directly. Checking Menu...")
                 found_menu = await self.find_first_visible(SoraSelectors.MENU_BTN)
                 if found_menu:
                      _, menu_btn = found_menu
                      await menu_btn.click()
                      await asyncio.sleep(1)
                      # Now look for Share in menu
                      found = await self.find_first_visible(SoraSelectors.SHARE_BUTTON)
                      if found:
                          logger.info("Found Share button inside Menu.")
            
            if found:
                _, btn = found
                
                # Log what we found
                try:
                    html = await btn.evaluate("el => el.outerHTML")
                    logger.info(f"Found Public/Share button: {html[:200]}...")
                except:
                    pass

                # Check if enabled (Extended Check)
                is_disabled = False
                if not await btn.is_enabled():
                    is_disabled = True
                else:
                    # Check custom attributes that Playwright might miss
                    try:
                        cls = await btn.get_attribute("class")
                        if cls and ("disabled=true" in cls or "pointer-events-none" in cls):
                            is_disabled = True
                        
                        aria_dis = await btn.get_attribute("aria-disabled")
                        if aria_dis and aria_dis == "true":
                            is_disabled = True
                            
                        data_dis = await btn.get_attribute("data-disabled")
                        if data_dis and data_dis == "true":
                            is_disabled = True
                    except:
                        pass
                
                if is_disabled:
                    logger.warning(f"Public/Share button found but DISABLED/LOCKED. Attempt {attempt+1}...")
                
                else:
                    public_link = None # Initialize to prevent UnboundLocalError
                    
                    # Rotational Click Strategy
                    # Attempt 0: Standard Click (Best for React)
                    # Attempt 1: Dispatch Click (Bypasses some listeners)
                    # Attempt 2: JS Click (Direct DOM)
                    try:
                        if attempt == 0:
                             logger.info("Strategy: Standard Click")
                             await btn.click(timeout=3000, force=True)
                        elif attempt == 1:
                             logger.info("Strategy: Dispatch Click")
                             await btn.dispatch_event('click')
                        else:
                             logger.info("Strategy: JS Method Click")
                             await btn.evaluate("element => element.click()")
                             
                        logger.info(f"Click action completed (Strategy {attempt}).")
                    except Exception as e:
                        logger.warning(f"Click strategy {attempt} failed: {e}")
            
            else:
                logger.warning("Share button not found. Checking fallbacks...")
            

            
            # Strategy: Click Video Item if Share Button didn't work (User suggestion)
            if attempt == 2 and not public_link:
                 logger.info("Strategy: Share button failed. Trying click on Video Item itself...")
                 try:
                     # Find video item (assuming we are in Profile or Drafts)
                     video_item = await self.find_first_visible(SoraSelectors.GRID_ITEM)
                     if video_item:
                         _, v_el = video_item
                         # Click video to open modal/copy link
                         await v_el.click()
                         await asyncio.sleep(1)
                         # Check clipboard again
                         clipboard_text = await self.page.evaluate("async () => { try { return await navigator.clipboard.readText(); } catch (e) { return null; } }")
                         if clipboard_text and "/share/" in clipboard_text:
                             public_link = clipboard_text.strip()
                             logger.info(f"[OK]  Found public link from clipboard (After Video Click): {public_link}")
                             return public_link
                 except Exception as e:
                     logger.warning(f"Video Item click strategy failed: {e}")

            # Wait for share dialog to appear (Fallback)
            await asyncio.sleep(3)
            
            await self._dump_html(f"share_dialog_attempt_{attempt}")
            
            # Try to find the public link in various ways
            public_link = None
            
            # Method 1: Look for input field with link
            for selector in SoraSelectors.PUBLIC_LINK_INPUT:
                try:
                    element = await self.page.query_selector(selector)
                    if element:
                        value = await element.get_attribute("value")
                        if value and "/share/" in value:
                            public_link = value
                            logger.info(f"Found public link in input: {public_link}")
                            break
                except:
                    continue
            
            if public_link:
                return public_link.strip()
                
            # Method 2: Look for text containing the link
            if not public_link:
                try:
                    # Get all text content
                    page_content = await self.page.content()
                    import re
                    match = re.search(r'https://sora\.chatgpt\.com/share/[a-zA-Z0-9-]+', page_content)
                    if match:
                        public_link = match.group(0)
                        logger.info(f"Found public link in page content: {public_link}")
                        return public_link.strip()
                except Exception as e:
                    logger.debug(f"Regex search failed: {e}")
            
            # Method 3: Try to copy from clipboard (if copy button exists)
            if not public_link:
                try:
                    # Generic copy button selector (often just an icon)
                    # Look for button that is NOT the Close button
                    copy_btn_selector = "button:has(svg):not([aria-label='Close'])"
                    
                    # Or specific SVG path for Copy icon (common one)
                    # But safer to try finding button by position or label if available
                    
                    # Try aria-label first
                    copy_btn = await self.page.query_selector("button[aria-label='Copy link']")
                    if not copy_btn:
                         copy_btn = await self.page.query_selector("button[aria-label='Copy']")
                    
                    if copy_btn:
                        await copy_btn.click()
                        logger.info("Clicked Copy Link button (via aria-label)")
                    else:
                        # Fallback: Find the button next to the input?
                        # Or just all buttons in dialog
                        pass

                    await asyncio.sleep(1)
                    
                    # Ensure focus for clipboard access
                    try:
                        await self.page.bring_to_front()
                        await self.page.evaluate("window.focus()")
                    except:
                        pass

                    # Debug Clipboard
                    clipboard_text = await self.page.evaluate("async () => { try { return await navigator.clipboard.readText(); } catch (e) { return 'ACCESS_DENIED: ' + e.message; } }")
                    logger.info(f"📋 RAW CLIPBOARD CONTENT: '{clipboard_text}'")
                    
                    if clipboard_text and clipboard_text != "ACCESS_DENIED" and "/share/" in clipboard_text:
                        public_link = clipboard_text
                        logger.info(f"Found public link from clipboard: {public_link}")
                        return public_link.strip()
                        
                except Exception as e:
                    logger.debug(f"Clipboard method failed: {e}")

            # Method 4: Look for any anchor tag with /share/
            try:
                share_link = await self.page.query_selector("a[href*='/share/']")
                if share_link:
                    href = await share_link.get_attribute("href")
                    if href:
                        public_link = href
                        logger.info(f"Found public link via anchor tag: {public_link}")
                        return public_link.strip()
            except:
                pass

            # Method 5: Aggressive Regex on Body Text (Client Side)
            try:
                # Execute JS to find link in body text
                js_link = await self.page.evaluate("""() => {
                    const match = document.body.innerText.match(/https:\/\/sora\.chatgpt\.com\/share\/[\w-]+/);
                    return match ? match[0] : null;
                }""")
                if js_link:
                     public_link = js_link
                     logger.info(f"Found public link via Body Text Regex: {public_link}")
                     return public_link.strip()
            except:
                pass

            # End of attempt
            logger.warning(f"Attempt {attempt+1} failed to find link. Retrying...")
            try:
                await self.page.keyboard.press("Escape")
                await asyncio.sleep(1)
            except:
                pass
        
        
        # FINAL FALLBACK: Construct link from Video ID if possible
        # If UI is disabled/glitchy but we have the ID, we can guess the link.
        try:
             logger.info("[WARNING]  UI extraction failed. Attempting to construct link from Video ID...")
             vid = await self._extract_video_id()
             
             # If simple extraction failed, try waiting for the anchor (maybe it loads late?)
             if not vid:
                 logger.info("Waiting for /p/ anchor (fallback deep scan)...")
                 try:
                     # Wait for any anchor with /p/
                     el = await self.page.wait_for_selector("a[href*='/p/']", timeout=5000)
                     if el:
                         href = await el.get_attribute("href")
                         if href and "/p/" in href:
                             vid = href.split("/p/")[1].split("?")[0]
                             logger.info(f"🆔 Extracted Video ID from waited anchor: {vid}")
                 except:
                     pass

             if vid:
                 fallback_link = f"https://sora.chatgpt.com/share/{vid}"
                 logger.warning(f"[WARNING]  Constructed fallback link (UNVERIFIED): {fallback_link}")
                 return fallback_link
        except Exception as e:
            logger.warning(f"Fallback ID construction failed: {e}")

        await self._snapshot("public_link_not_found")
        await self._dump_html("public_link_not_found")
        raise PublicLinkNotFoundException("Could not retrieve public link from UI after retries")
            # ... (rest of function) ...

    async def _extract_video_id(self) -> Optional[str]:
        """
        Extract internal Video ID from current URL or Grid Item data.
        Useful for consistent mapping.
        """
        try:
            # 1. Check URL (if viewing specific video)
            # URL format: https://sora.chatgpt.com/sora/video_id_string
            url = self.page.url
            if "/sora/" in url and len(url.split("/sora/")[1]) > 5:
                vid = url.split("/sora/")[1].split("?")[0]
                logger.info(f"🆔 Extracted Video ID from URL: {vid}")
                return vid
            
            # 2. Check First Grid Item Data Attribute
            from .selectors import SoraSelectors
            item = await self.page.query_selector(SoraSelectors.GRID_ITEM)
            if item:
                # Try common data attributes
                # e.g. href="/sora/xyz" or "/p/xyz"
                href = await item.get_attribute("href")
                
                # If item is not the anchor, look inside
                if not href:
                    anchor = await item.query_selector("a[href]")
                    if anchor:
                        href = await anchor.get_attribute("href")

                if href:
                    if "/sora/" in href:
                        vid = href.split("/sora/")[1].split("?")[0]
                        logger.info(f"🆔 Extracted Video ID from Grid Item (/sora/): {vid}")
                        return vid
                    if "/p/" in href:
                        vid = href.split("/p/")[1].split("?")[0]
                        logger.info(f"🆔 Extracted Video ID from Grid Item (/p/): {vid}")
                        return vid

            # 3. Check specific anchor pattern from dump
            # /p/s_6960a21c807081918274097bea2ec683
            id_link = await self.page.query_selector("a[href*='/p/']")
            if id_link:
                 href = await id_link.get_attribute("href")
                 if href and "/p/" in href:
                     vid = href.split("/p/")[1].split("?")[0]
                     logger.info(f"🆔 Extracted Video ID from /p/ anchor: {vid}")
                     return vid
            
            return None
        except Exception as e:
            logger.warning(f"Failed to extract video ID: {e}")
            return None


    async def check_credits(self) -> int:
        """
        Check available video credits by navigating to settings or scanning page.
        Returns:
            int: Number of credits remaining, or -1 if could not determine.
        """
        import re
        logger.info("Checking credits...")
        
        credits = -1
        
        # Method 1: Check via Settings UI (Proven flow from test_direct.py)
        try:
             # Step 1: Click Settings button
             logger.info("Clicking Settings button...")
             await self.page.click("button[aria-label='Settings']")
             await asyncio.sleep(2)
             
             # Step 2: Click Settings menu item inside dropdown
             logger.info("Clicking Settings menu item...")
             await self.page.click("div[role='menuitem']:has-text('Settings')")
             await asyncio.sleep(3)
             
             # Step 3: Click Usage tab
             logger.info("Clicking Usage tab...")
             usage_btn = await self.page.query_selector("button[role='tab'][id*='trigger-usage']")
             if usage_btn:
                 await usage_btn.click()
                 await asyncio.sleep(2)
             else:
                 # Fallback: text match
                 await self.page.click("button:has-text('Usage')")
                 await asyncio.sleep(2)
             
             # Step 4: Get page content and search for credits
             content = await self.page.content()
             
             # Scan for patterns (prioritize "N free" pattern)
             for pattern in SoraSelectors.CREDIT_TEXT_PATTERNS:
                 match = re.search(pattern, content, re.IGNORECASE)
                 if match:
                     credits = int(match.group(1))
                     logger.info(f"[CREDITS]  Found credits UI: {credits}")
                     break
                     
             # Close dialog
             await self.page.keyboard.press("Escape")
             await asyncio.sleep(0.5)
             
        except Exception as e:
            logger.warning(f"UI Credit check failed: {e}")
            
        # Method 2: Direct URL Fallback (as per automation script)
        if credits == -1:
            try:
                logger.info("Trying direct Settings URL...")
                # Open new tab or reuse? Reuse is safer for session
                await self.page.goto("https://sora.chatgpt.com/settings")
                await asyncio.sleep(3)
                
                content = await self.page.content()
                for pattern in SoraSelectors.CREDIT_TEXT_PATTERNS:
                     match = re.search(pattern, content, re.IGNORECASE)
                     if match:
                         credits = int(match.group(1))
                         logger.info(f"[CREDITS]  Found credits DirectURL: {credits}")
                         break
                         
                # Go back to home
                await self.page.goto("https://sora.chatgpt.com")
                
            except Exception as e:
                 logger.error(f"Direct URL Credit check failed: {e}")

        if credits == -1:
            logger.warning("Could not determine credits.")
            
        return credits

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
        import os
        import time
        import uuid
        import aiohttp
        
        os.makedirs(output_dir, exist_ok=True)
        
        # Extract video URL
        video_url = await self.extract_video_url()
        
        # Get cookies from browser context
        context = self.page.context
        cookies = await context.cookies()
        
        # Build cookie dict for aiohttp
        cookie_jar = aiohttp.CookieJar()
        for cookie in cookies:
            # Create morsel for each cookie
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

    async def verify_video_by_prompt(self, expected_prompt: str, similarity_threshold: float = 0.5) -> bool:
        """
        Verify video belongs to current account by matching prompt/description.
        
        Args:
            expected_prompt: The prompt used to generate the video
            similarity_threshold: Minimum ratio of matching words (0.0-1.0)
            
        Returns:
            bool: True if video description matches expected prompt
        """
        logger.info("🔍 Verifying video ownership by prompt matching...")
        
        try:
            # Get video description/prompt from page
            # Look for common selectors that might contain the prompt text
            video_text = await self.page.evaluate("""
                () => {
                    // Try various selectors for video description
                    const selectors = [
                        '[class*="description"]',
                        '[class*="prompt"]',
                        '[class*="caption"]',
                        'h1', 'h2', 'h3',
                        'p',
                        '[data-testid*="description"]',
                        '[data-testid*="prompt"]'
                    ];
                    
                    let allText = '';
                    for (const sel of selectors) {
                        const elements = document.querySelectorAll(sel);
                        elements.forEach(el => {
                            if (el.innerText) {
                                allText += ' ' + el.innerText;
                            }
                        });
                    }
                    return allText.toLowerCase();
                }
            """)
            
            if not video_text:
                logger.warning("[WARNING]  Could not extract video description text")
                return False
            
            # Simple word matching
            expected_words = set(expected_prompt.lower().split())
            matching_words = sum(1 for word in expected_words if word in video_text)
            
            if len(expected_words) == 0:
                logger.warning("[WARNING]  Empty expected prompt")
                return False
            
            match_ratio = matching_words / len(expected_words)
            
            logger.info(f"[STATS]  Prompt match ratio: {match_ratio:.2f} ({matching_words}/{len(expected_words)} words)")
            
            if match_ratio >= similarity_threshold:
                logger.info("[OK]  Video ownership verified!")
                return True
            else:
                logger.warning(f"[WARNING]  Video may not match expected prompt (ratio: {match_ratio:.2f})")
                return False
                
        except Exception as e:
            logger.error(f"[ERROR]  Verification failed: {e}")
            return False

    async def get_video_count_in_drafts(self) -> int:
        """
        Count number of videos in drafts page.
        Useful for tracking before/after video creation.
        
        Returns:
            int: Number of draft videos, or -1 if error
        """
        try:
            await self.page.goto("https://sora.chatgpt.com/drafts", wait_until="networkidle")
            await asyncio.sleep(2)
            
            # Count grid items
            count = await self.page.evaluate("""
                () => {
                    const items = document.querySelectorAll(
                        'a[href*="/drafts/"], a[href*="/d/"], div[class*="card"], div[class*="Card"]'
                    );
                    return items.length;
                }
            """)
            
            logger.info(f"[STATS]  Draft count: {count}")
            return count
            
        except Exception as e:
            logger.error(f"Failed to count drafts: {e}")
            return -1


