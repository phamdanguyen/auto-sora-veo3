import logging
import asyncio
import os
from datetime import datetime
from typing import Optional
from .base import BasePage
from ..selectors import SoraSelectors
from ..exceptions import VerificationRequiredException, LoginFailedException

logger = logging.getLogger(__name__)

# Enable debug screenshots
DEBUG_SCREENSHOTS = True
DEBUG_DIR = "data/debug_login"

class SoraLoginPage(BasePage):
    
    async def _debug_screenshot(self, name: str):
        """Take debug screenshot with timestamp."""
        if not DEBUG_SCREENSHOTS:
            return
        try:
            os.makedirs(DEBUG_DIR, exist_ok=True)
            timestamp = datetime.now().strftime("%H%M%S")
            path = f"{DEBUG_DIR}/{timestamp}_{name}.png"
            await self.page.screenshot(path=path)
            logger.info(f"[IMAGE]  Debug screenshot: {path}")
        except Exception as e:
            logger.warning(f"Failed to take screenshot: {e}")

    async def wait_for_manual_login(self, timeout: int = 300) -> bool:
        """
        Wait for the user to manually log in.
        Polls for login success indicators (e.g., 'Sora' in title, 'explore' in URL).
        """
        logger.info(f"[WAIT]  Waiting {timeout}s for MANUAL login...")
        start_time = asyncio.get_event_loop().time()
        
        while (asyncio.get_event_loop().time() - start_time) < timeout:
            if await self.check_is_logged_in():
                logger.info("[OK]  Manual Login Detected!")
                return True
            await asyncio.sleep(2)
            
        logger.error("[ERROR]  Manual login timed out.")
        return False
    
    async def _debug_page_info(self, step: str):
        """Log current page info for debugging."""
        try:
            url = self.page.url
            title = await self.page.title()
            logger.info(f"🔍 [{step}] URL: {url}")
            logger.info(f"🔍 [{step}] Title: {title}")
        except Exception as e:
            logger.warning(f"Debug info failed: {e}")

    async def login(self, email: str, password: str, base_url: str, headless_mode: bool = False):
        """
        Executes the login flow with enhanced debugging.
        Supports Microsoft OAuth for Hotmail/Outlook accounts.
        """
        logger.info("=" * 60)
        logger.info(f"[START]  Starting login for: {email}")
        logger.info(f"[API]  Target URL: {base_url}")
        logger.info(f"🕶️ Headless Mode: {headless_mode}")
        logger.info("=" * 60)
        
        # Always use standard email/password flow (not OAuth)
        # OAuth (Microsoft/Google) is less stable for automation
        account_type = 'standard'
        logger.info(f"📧 Using: Email/Password flow (not OAuth)")
        
        # Step 0: Navigate
        logger.info("📍 Step 0: Navigating to auth page...")
        try:
            await self.page.goto(base_url, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(3)
            await self._debug_screenshot("00_after_navigate")
            await self._debug_page_info("NAVIGATE")
            logger.info("🚦 DEBUG: Navigation complete. Checking login status...")
        except Exception as e:
            logger.error(f"[ERROR]  Navigation failed: {e}")
            await self._debug_screenshot("00_navigate_error")
        
        # Check if already logged in - AND FORCE LOGOUT if so
        logger.info("🚦 DEBUG: Calling check_is_logged_in()...")
        if await self.check_is_logged_in():
            logger.info("[WARNING]  Session detected! Performing FORCE LOGOUT to ensure fresh token capture...")
            
            # 1. Clear Cookies (Most reliable way to logout)
            if self.page.context:
                await self.page.context.clear_cookies()
                logger.info("[OK]  Cookies cleared.")
            
            # 2. Clear Local Storage (Just in case)
            try:
                await self.page.evaluate("localStorage.clear(); sessionStorage.clear();")
            except:
                pass

            # 3. Reload to apply
            logger.info("[MONITOR]  Reloading page after cleanup...")
            await self.page.reload(wait_until="domcontentloaded")
            await asyncio.sleep(3)
            
            # Double check
            if await self.check_is_logged_in():
                 logger.warning("[WARNING]  Still logged in after cleanup? Attempting navigation to auth...")
                 await self.page.goto(base_url, timeout=30000)
            else:
                 logger.info("[OK]  Logout successful. Proceeding to fresh login.")
        else:
            logger.info("🚦 DEBUG: Not logged in. Proceeding to content checks...")

        # [REMOVED] Cloudflare & Server Overload checks which were causing false positives/delays.
        # User requested to remove "Alert" handling.

        # Attempt Automated Login
        try:
            # Handle native dialogs (Alerts) automatically if they appear
            self.page.on("dialog", lambda dialog: dialog.accept())

            # Handle cookies banner first
            try:
                for cookie_sel in ["button:has-text('Accept all')", "button:has-text('Accept')", "[data-testid='close-button']"]:
                    if await self.page.is_visible(cookie_sel, timeout=2000):
                        await self.page.click(cookie_sel)
                        logger.info(f"[OK]  Clicked cookies button: {cookie_sel}")
                        await asyncio.sleep(1)
                        break
            except:
                pass
            
            # Check if we need to click "Log in" button (auth page)
            try:
                login_btns = [
                    "button:has-text('Log in')",
                    "a:has-text('Log in')",
                    "[data-testid='login-button']"
                ]
                for sel in login_btns:
                    if await self.page.is_visible(sel, timeout=3000):
                        await self.page.click(sel)
                        logger.info(f"[OK]  Clicked Login button: {sel}")
                        await asyncio.sleep(5)
                        await self._debug_screenshot("00_after_login_click")
                        break
            except:
                pass
            
            if account_type == 'microsoft':
                await self._login_with_microsoft(email, password)
            elif account_type == 'google':
                await self._login_with_google(email, password)
            else:
                await self._login_with_email(email, password)
        except Exception as e:
            logger.error(f"[ERROR]  Automated login error: {e}")
            await self._debug_screenshot("login_error")
        
        # Final check
        await asyncio.sleep(3)
        if await self.check_is_logged_in():
            logger.info("🎉 Login Successful!")
            await self._debug_screenshot("login_success")
        else:
            logger.warning("[WARNING]  Auto login may have failed, checking for errors...")
            await self._debug_screenshot("login_may_failed")
            await self.check_login_errors()
            
            if headless_mode:
                logger.error("[STOP]  Headless mode active. Skipping manual fallback wait.")
                # Force cleanup of context if needed? No, driver handles it.
                raise Exception("Headless Login Failed - Manual Intervention Required")
            
            await self.manual_login_fallback()

    async def _login_with_microsoft(self, email: str, password: str):
        """Login using Microsoft OAuth button."""
        logger.info("📍 Using Microsoft OAuth login flow...")
        
        # Step 1: Click "Continue with Microsoft" button
        await asyncio.sleep(2)
        
        microsoft_btn_selectors = [
            "button:has-text('Continue with Microsoft')",
            "button:has-text('Microsoft')",
            "[data-testid='social-auth-button-microsoft']",
            "button >> text=Microsoft"
        ]
        
        clicked = False
        for sel in microsoft_btn_selectors:
            try:
                if await self.page.is_visible(sel, timeout=3000):
                    await self.page.click(sel)
                    logger.info(f"[OK]  Clicked Microsoft button: {sel}")
                    clicked = True
                    break
            except:
                continue
        
        if not clicked:
            logger.error("[ERROR]  Microsoft button not found!")
            await self._debug_screenshot("microsoft_btn_not_found")
            raise Exception("Microsoft login button not found")
        
        await asyncio.sleep(5)
        await self._debug_screenshot("01_after_microsoft_click")
        
        # Step 2: Wait for Microsoft login page
        logger.info("📍 Step 2: Waiting for Microsoft login page...")
        
        try:
            # Wait for Microsoft login page (email input)
            ms_email_selectors = [
                "input[type='email']",
                "input[name='loginfmt']",
                "#i0116"
            ]
            
            email_found = False
            for sel in ms_email_selectors:
                try:
                    await self.page.wait_for_selector(sel, timeout=15000)
                    await self.page.fill(sel, email)
                    logger.info(f"[OK]  Filled Microsoft email: {email}")
                    await self._debug_screenshot("02_ms_email_filled")
                    email_found = True
                    break
                except:
                    continue
            
            if not email_found:
                raise Exception("Microsoft email field not found")
            
            # Click Next
            await asyncio.sleep(1)
            next_btn = await self.page.query_selector("#idSIButton9, input[type='submit']")
            if next_btn:
                await next_btn.click()
                logger.info("[OK]  Clicked Next on Microsoft page")
            else:
                await self.page.keyboard.press("Enter")
            
            await asyncio.sleep(5)
            await self._debug_screenshot("03_after_ms_email_submit")
            
            # Step 3: Enter Microsoft password
            logger.info("📍 Step 3: Entering Microsoft password...")
            
            ms_pass_selectors = [
                "input[type='password']",
                "input[name='passwd']",
                "#i0118"
            ]
            
            pass_found = False
            for sel in ms_pass_selectors:
                try:
                    if await self.page.is_visible(sel, timeout=10000):
                        await self.page.fill(sel, password)
                        logger.info("[OK]  Filled Microsoft password")
                        await self._debug_screenshot("04_ms_password_filled")
                        pass_found = True
                        break
                except:
                    continue
            
            if not pass_found:
                raise Exception("Microsoft password field not found")
            
            # Click Sign In
            await asyncio.sleep(1)
            signin_btn = await self.page.query_selector("#idSIButton9, input[type='submit']")
            if signin_btn:
                await signin_btn.click()
                logger.info("[OK]  Clicked Sign In on Microsoft page")
            else:
                await self.page.keyboard.press("Enter")
            
            await asyncio.sleep(8)
            await self._debug_screenshot("05_after_ms_signin")
            
            # Step 4: Handle "Stay signed in?" prompt
            logger.info("📍 Step 4: Handling 'Stay signed in?' prompt...")
            
            try:
                stay_signed_in = await self.page.is_visible("text='Stay signed in?'", timeout=5000)
                if stay_signed_in:
                    # Click "Yes" to stay signed in
                    yes_btn = await self.page.query_selector("#idSIButton9, button:has-text('Yes')")
                    if yes_btn:
                        await yes_btn.click()
                        logger.info("[OK]  Clicked 'Yes' to stay signed in")
                    await asyncio.sleep(5)
            except:
                pass
            
            await self._debug_screenshot("06_after_stay_signed")
            
            # Wait for redirect back to ChatGPT
            logger.info("📍 Waiting for redirect back to ChatGPT...")
            await asyncio.sleep(10)
            await self._debug_screenshot("07_after_redirect")
            
        except Exception as e:
            logger.error(f"[ERROR]  Microsoft login flow error: {e}")
            await self._debug_screenshot("ms_login_error")
            raise

    async def _login_with_email(self, email: str, password: str):
        """Standard email/password login flow using specific selectors."""
        logger.info("📍 Using STRICT email/password login flow...")
        
        # Step 1: Click "Log in" button on landing page
        # Landing: https://chatgpt.com/auth/login?next=%2Fsora%2Fexplore
        await asyncio.sleep(3)
        
        login_btn_sel = "[data-testid='login-button']" # Primary selector
        login_clicked = False
        
        try:
             # Try primary first
             if await self.page.is_visible(login_btn_sel, timeout=3000):
                 logger.info(f"[OK]  Found Login Button: {login_btn_sel}")
                 await self.page.click(login_btn_sel)
                 login_clicked = True
             else:
                 # Fallback to list
                 logger.warning("[WARNING]  Primary login button not found, checking alternatives...")
                 for sel in SoraSelectors.LOGIN_BTN_INIT:
                     if await self.page.is_visible(sel, timeout=2000):
                         await self.page.click(sel)
                         logger.info(f"[OK]  Clicked alternative Login button: {sel}")
                         login_clicked = True
                         break
        except Exception as e:
             logger.warning(f"Error clicking login button (might already be on auth page): {e}")

        # FALLBACK: If we couldn't click login, FORCE navigate to auth page
        if not login_clicked:
             logger.warning("[WARNING]  Login button not found or not clickable. Forcing navigation to Auth URL...")
             try:
                 # Standard Auth URL
                 auth_url = "https://auth.openai.com/authorize?client_id=pdlLIX2Y72MIl2rhLhTE9VV9bN905kBh&audience=https%3A%2F%2Fapi.openai.com%2Fv1&redirect_uri=https%3A%2F%2Fchatgpt.com%2Fapi%2Fauth%2Fcallback%2Fopenai&scope=openid%20profile%20email%20offline_access%20model.read%20model.request&response_type=code&response_mode=query&state=..."
                 # Actually, better to just let it flow if we are already there. 
                 # But if we are stuck on landing...
                 current_url = self.page.url
                 if "auth.openai.com" not in current_url:
                      logger.info("👉 Navigating directly to login page...")
                      # Simple redirect that usually triggers auth flow
                      await self.page.goto("https://chatgpt.com/api/auth/session", timeout=10000)
                      # Or explicit login link
                      await asyncio.sleep(2)
             except:
                 pass

        await asyncio.sleep(5)
        await self._debug_screenshot("01_after_login_click")

        # Step 2: Email Page
        # URL: https://auth.openai.com/log-in-or-create-account
        logger.info("📍 Step 2: Email Entry")
        
        # Input
        email_sel = "input[name='email']" # Standard input associated with "Email address" label
        try:
            await self.page.wait_for_selector(email_sel, timeout=10000)
            await self.page.fill(email_sel, email)
            logger.info(f"[OK]  Filled email: {email}")
        except Exception as e:
            logger.error(f"[ERROR]  Email input not found: {e}")
            await self._debug_screenshot("email_not_found")
            raise

        # Continue Button (Email)
        # Selector: button[data-dd-action-name='Continue'][value='email']
        continue_email_sel = "button[data-dd-action-name='Continue'][value='email']"
        
        try:
            # Fallback to generic if specific not found
            if await self.page.is_visible(continue_email_sel, timeout=3000):
                await self.page.click(continue_email_sel)
                logger.info(f"[OK]  Clicked Email Continue: {continue_email_sel}")
            else:
                 # Try strict generic "Continue" (EXACT match only)
                 logger.warning("[WARNING]  Specific Email Continue button not found, searching for strict 'Continue'...")
                 strict_sel = "button:text-is('Continue')"
                 if await self.page.is_visible(strict_sel, timeout=3000):
                     await self.page.click(strict_sel)
                     logger.info(f"[OK]  Clicked Strict Continue: {strict_sel}")
                 else:
                     raise Exception("Could not find any safe 'Continue' button.")
                     
        except Exception as e:
            logger.error(f"[ERROR]  Failed to click Continue (Email): {e}")
            raise

        await asyncio.sleep(2) # Short wait for state change
        await self._debug_screenshot("02_after_email_continue")

        # FAIL FAST - Immediate Check for Verification/Block after Email
        # This is the most critical logic update: Check for Block BEFORE checking for Password
        logger.info("⚡ FAIL FAST: Checking for immediate verification blocks...")
        
        # Check Resend Email (2FA)
        resend_sel = "button[value='resend']"
        if await self.page.is_visible(resend_sel, timeout=1000):
            logger.warning("🚨 2FA / Verification Detected (Resend Email button found). Waiting for user...")
            await self.manual_login_fallback()
            return  # User completed 2FA

        # Check other verification indicators
        for ind in SoraSelectors.VERIFICATION_INDICATORS:
             if await self.page.is_visible(ind, timeout=500):
                 logger.warning(f"🚨 Verification Indicator Found: {ind}. Waiting for user...")
                 await self.manual_login_fallback()
                 return  # User completed 2FA

        # Step 3: Password Page
        logger.info("📍 Step 3: Password Entry")
        
        password_sel = "input[name='password']"
        
        pwd_selectors = [
            "input[name='password']",                   
            "input[id*='current-password']",            
            "input[type='password']",                   
            "[data-testid='password-input']"
        ]
        
        pwd_found = False
        start_pwd_time = asyncio.get_event_loop().time()
        
        # Parallel race: Wait for Password OR Verification indicators
        # But for simplicity in this context, we poll briefly
        for _ in range(5): # Try for ~5 seconds total
            # 1. Check for Password
            for sel in pwd_selectors:
                if await self.page.is_visible(sel, timeout=500):
                    await self.page.fill(sel, password)
                    logger.info(f"[OK]  Found Password Input: {sel}")
                    pwd_found = True
                    break
            if pwd_found: break
            
            # 2. Check for Verification Block (FAIL FAST)
            if await self.page.is_visible(resend_sel, timeout=500):
                 logger.warning("🚨 2FA detected during password wait. Waiting for user...")
                 await self.manual_login_fallback()
                 return  # User completed 2FA
            
            await asyncio.sleep(1)

        if not pwd_found:
             # Try finding by Label as last resort
             try:
                logger.info("[WARNING]  Selector lookup failed, trying get_by_label('Password')...")
                await self.page.get_by_label("Password").fill(password)
                pwd_found = True
                logger.info("[OK]  Found Password Input via Label")
             except Exception as e:
                # Final check for 2FA before giving up
                if await self.page.is_visible(resend_sel):
                    logger.warning("🚨 2FA detected (password not found). Waiting for user...")
                    await self.manual_login_fallback()
                    return  # User completed 2FA
                    
                logger.error(f"[ERROR]  Password input not found via any method: {e}")
                await self._debug_screenshot("password_not_found")
                # Don't raise, let global error checker handle it

        # Continue Button (Password/Validate)
        submit_sel = "button[data-dd-action-name='Continue'][value='validate']"
        try:
            if await self.page.is_visible(submit_sel, timeout=3000):
                 await self.page.click(submit_sel)
                 logger.info(f"[OK]  Clicked Password Continue: {submit_sel}")
            else:
                 logger.warning("[WARNING]  Specific Password Continue button not found, using generic...")
                 for s in ["button[type='submit']", "button:has-text('Continue')", "button:has-text('Log in')"]:
                     if await self.page.is_visible(s, timeout=1000):
                         await self.page.click(s)
                         break
        except Exception as e:
            logger.error(f"[ERROR]  Failed to click Submit: {e}")
            raise

        await asyncio.sleep(3)
        await self._debug_screenshot("03_final_submit")

    async def check_is_logged_in(self) -> bool:
        try:
            url = self.page.url
            
            # Still on auth/login page = not logged in
            if "/login" in url or "/auth" in url:
                return False
            
            # Microsoft login page
            if "microsoftonline.com" in url or "live.com" in url:
                return False
            
            # Check for studio indicators
            if await self.page.is_visible(SoraSelectors.LOGIN_SUCCESS_INDICATOR, timeout=2000):
                return True
            
            # Check for textarea (studio)
            if await self.page.is_visible("textarea", timeout=2000):
                logger.info("Found textarea - assuming logged in")
                return True
            
            # Check URL for sora.chatgpt.com (logged in domain)
            if "sora.chatgpt.com" in url and "/auth" not in url and "/login" not in url:
                return True
            
            return False
        except:
            return False

    async def check_login_errors(self):
        logger.info("🔍 Checking for login errors...")
        
        for ind in SoraSelectors.ERROR_INDICATORS:
            try:
                if await self.page.is_visible(ind, timeout=1000):
                    await self._debug_screenshot("error_detected")
                    error_text = await self.page.text_content(ind)
                    logger.error(f"[ERROR]  Error detected: {error_text}")
                    raise Exception(f"Login Failed: {error_text}")
            except:
                pass
        
        for ind in SoraSelectors.VERIFICATION_INDICATORS:
            try:
                if await self.page.is_visible(ind, timeout=1000):
                    await self._debug_screenshot("verification_needed")
                    logger.warning("[WARNING]  2FA/Verification required! Waiting for user to complete...")
                    # Instead of failing, wait for user to complete 2FA manually
                    await self.manual_login_fallback()
                    return  # User completed 2FA, continue
            except VerificationRequiredException:
                raise
            except:
                pass

    async def manual_login_fallback(self):
        if os.environ.get("SKIP_MANUAL_WAIT"):
            logger.warning("[WARNING]  SKIP_MANUAL_WAIT set. Skipping manual login wait.")
            raise Exception("Login Failed: Automated login failed and manual wait skipped.")

        logger.info("=" * 60)
        logger.info("[WARNING]  MANUAL LOGIN REQUIRED")
        logger.info("[WARNING]  Please login in the browser window that opened")
        logger.info("[WARNING]  You have 5 minutes to complete login")
        logger.info("=" * 60)
        
        max_wait = 300  # 5 minutes
        check_interval = 5
        start_time = asyncio.get_event_loop().time()
        
        while (asyncio.get_event_loop().time() - start_time) < max_wait:
            remaining = int(max_wait - (asyncio.get_event_loop().time() - start_time))
            
            if remaining % 30 == 0:
                logger.info(f"[WAIT]  Waiting for manual login... ({remaining}s remaining)")
                await self._debug_screenshot(f"manual_wait_{remaining}s")
            
            if await self.check_is_logged_in():
                logger.info("🎉 Manual Login Success!")
                await self._debug_screenshot("manual_login_success")
                return
                
            await asyncio.sleep(check_interval)

        await self._debug_screenshot("manual_login_timeout")
        raise Exception("Login Timeout: User did not login within 5 minutes")
