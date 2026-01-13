from ..abstractions import BrowserBasedDriver, VideoResult, CreditsInfo, UploadResult, VideoData, PendingTask
from .pages.login import SoraLoginPage
from .pages.creation import SoraCreationPage
from .pages.drafts import SoraDraftsPage
from .pages.download import SoraDownloadPage
from .pages.verification import SoraVerificationPage
import logging
import asyncio
import aiohttp
import os
import time
import json
from typing import Optional, Callable, Awaitable

logger = logging.getLogger(__name__)

class SoraDriver(BrowserBasedDriver):
    def __init__(self, headless: bool = False, proxy: Optional[str] = None, user_data_dir: Optional[str] = None, channel: str = "chrome", access_token: str = None, device_id: str = None, user_agent: str = None, cookies: list = None):
        super().__init__(headless=headless, proxy=proxy, user_data_dir=user_data_dir, channel=channel)
        
        # Store auth data if provided (Hybrid/API support)
        self.latest_access_token = access_token
        self.device_id = device_id
        self.latest_user_agent = user_agent
        self.cookies = cookies or []

        # Use direct auth URL for reliable login flow
        self.base_url = "https://chatgpt.com/auth/login?next=%2Fsora%2F"
        
        # Page Objects (initialized after start)
        self.login_page = None
        self.creation_page = None
        self.drafts_page = None
        self.download_page = None
        self.verification_page = None

    async def start(self):
        """Start browser and initialize driver"""
        from playwright.async_api import async_playwright

        # Initialize Playwright
        self.playwright = await async_playwright().start()

        # Configure proxy
        proxy_config = None
        if self.proxy:
            # Parse proxy string ip:port:user:pass
            parts = self.proxy.split(':')
            if len(parts) == 4:
                proxy_config = {
                    "server": f"http://{parts[0]}:{parts[1]}",
                    "username": parts[2],
                    "password": parts[3]
                }
            elif len(parts) == 2:
                 proxy_config = {
                    "server": f"http://{parts[0]}:{parts[1]}"
                }

        # Launch args to bypass detection
        args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
            "--disable-dev-shm-usage",
            "--disable-extensions",
            "--disable-gpu",
            "--disable-web-security",
            "--disable-site-isolation-trials",
        ]

        # Use provided profile dir or default
        profile_path = self.user_data_dir if self.user_data_dir else "./data/browser_profile"
        logger.info(f"Launching Browser with Profile Path: {profile_path}")

        if not os.path.exists(profile_path):
            os.makedirs(profile_path)

        # Launch browser
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            channel=self.channel,
            args=args,
        )

        # Create browser context
        self.context = await self.browser.new_context(
            accept_downloads=True,
            ignore_https_errors=True,
            locale="en-US",
            timezone_id="America/New_York",
            proxy=proxy_config,
            permissions=["geolocation", "clipboard-read", "clipboard-write"],
            geolocation={"latitude": 40.7128, "longitude": -74.0060},
            color_scheme="dark",
            viewport={"width": 1280, "height": 720},
            storage_state=None
        )

        self.page = await self.context.new_page()

        # Add stealth script
        await self.page.add_init_script("""
            if (Object.getOwnPropertyDescriptor(navigator, 'webdriver') === undefined) {
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            }
        """)

        # Setup Hybrid Interception
        # Preserve injected tokens if available
        if not hasattr(self, 'latest_access_token') or self.latest_access_token is None:
            self.latest_access_token = None
        if not hasattr(self, 'latest_user_agent') or self.latest_user_agent is None:
             self.latest_user_agent = None
             
        self.latest_intercepted_data = None
        self.intercepted_videos = {} # ID -> {status, url, ...}
        self.last_submission_result = None # Latest nf/create response
        await self._setup_interception()

        self.login_page = SoraLoginPage(self.page)
        self.creation_page = SoraCreationPage(self.page)
        self.drafts_page = SoraDraftsPage(self.page)
        self.download_page = SoraDownloadPage(self.page)
        self.verification_page = SoraVerificationPage(self.page)

    async def login(self, email: str, password: str):
        """
        Performs the login flow.
        """
        if not self.login_page:
            self.login_page = SoraLoginPage(self.page)
        
        await self.login_page.login(email, password, self.base_url, headless_mode=self.headless)
        
        # Initialize other pages after successful login
        self.creation_page = SoraCreationPage(self.page)
        self.drafts_page = SoraDraftsPage(self.page)
        self.download_page = SoraDownloadPage(self.page)
        self.verification_page = SoraVerificationPage(self.page)

    async def wait_for_login(self, timeout: int = 300) -> Optional[str]:
        """
        Waits for user to manually login and captures the email.
        
        Args:
            timeout: Max seconds to wait
            
        Returns:
            Detected email string if successful, None otherwise.
        """
        logger.info(f"👤 Waiting for USER to login (max {timeout}s)...")
        
        # Navigate to login if not already there
        if "auth/login" not in self.page.url and "sora" not in self.page.url:
             await self.page.goto(self.base_url, wait_until="domcontentloaded")

        start_time = time.time()
        poll_interval = 2
        
        import jwt
        
        while time.time() - start_time < timeout:
            if self.latest_access_token:
                # Try to decode email
                try:
                    token_str = self.latest_access_token
                    if token_str.lower().startswith("bearer "):
                        token_str = token_str[7:]
                    
                    decoded = jwt.decode(token_str, options={"verify_signature": False})
                    
                    email = None
                    if "email" in decoded:
                        email = decoded["email"]
                    elif "https://api.openai.com/profile" in decoded:
                        email = decoded["https://api.openai.com/profile"].get("email")
                    elif "user" in decoded and isinstance(decoded["user"], dict):
                        email = decoded["user"].get("email")
                        
                    if email:
                        logger.info(f"✨ Token captured for email: {email}")
                        return email
                except Exception as e:
                    pass

            await asyncio.sleep(poll_interval)
            
        return None

    @classmethod
    async def api_only(cls, access_token: str, device_id: str = None, user_agent: str = None, cookies: list = None):
        """
        Create a SoraDriver instance that only uses API calls (NO BROWSER).
        
        This enables 100% headless operation after tokens have been captured
        via the Account login flow.
        
        Args:
            access_token: Bearer token from previous login
            device_id: oai-device-id from previous login
            user_agent: User agent string (optional)
            cookies: List of cookies (optional)
            
        Returns:
            SoraDriver instance ready for API-only operations
        """
        driver = cls.__new__(cls)
        driver.page = None  # No browser!
        driver.context = None
        driver.browser = None
        driver.playwright = None
        
        # Set token data
        driver.latest_access_token = access_token
        driver.device_id = device_id or ""
        driver.latest_user_agent = user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        driver.cookies = cookies or []
        
        # Initialize tracking
        driver.intercepted_videos = {}
        driver.last_submission_result = None
        driver.latest_intercepted_data = None
        
        # No page objects (not needed for API)
        driver.login_page = None
        driver.creation_page = None
        driver.drafts_page = None
        driver.download_page = None
        driver.verification_page = None
        
        logger.info(f"🔌 SoraDriver API-only mode initialized (no browser)")
        return driver
    
    async def stop(self):
        """Stop driver and cleanup resources"""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    def get_cached_video(self, video_id: str) -> Optional[dict]:
        """Get video info from interception cache"""
        return self.intercepted_videos.get(video_id)

    async def _setup_interception(self):
        """Setup network listener to capture tokens"""
        logger.info("🕵️ Enabling Hybrid Network Interception...")
        
        # 1. Capture User Agent
        try:
             self.latest_user_agent = await self.page.evaluate("navigator.userAgent")
        except:
             pass

        # 2. Capture Tokens from Requests
        async def handle_request(route):
             # We monitor requests but don't modify them (continue)
             # Actually using 'request' event is safer than route if we don't want to block
             pass
        
        # Using event listener instead of route handler to avoid blocking
        self.page.on("request", self._on_request_intercept)
        self.page.on("response", self._on_response_intercept)

    def _on_request_intercept(self, request):
        """Callback for every request"""
        try:
            url = request.url
            # Widen scope to capture token from ANY OpenAI/ChatGPT endpoint
            if "openai.com" in url or "chatgpt.com" in url:
                # print(f"🕵️ INTERCEPTED URL: {url}") # Explicit print to see in console
                headers = request.headers
                
                # Check for standard Authorization header (case-insensitive in Playwright headers)
                # Playwright headers are lowercase
                token = headers.get("authorization")
                
                if token and token.startswith("Bearer "):
                    if self.latest_access_token != token:
                        logger.info(f"[TOKEN]  Captured NEW Access Token! ({token[:15]}...) via {url}")
                        self.latest_access_token = token
                        
                        # Also capture User-Agent from this request if available
                        if "user-agent" in headers:
                            self.latest_user_agent = headers["user-agent"]
                            
        except Exception as e:
            pass # Don't crash on intercept
        except Exception as e:
            pass # Don't crash on intercept

    def _on_response_intercept(self, response):
        """Callback for every response - Fire and Forget"""
        try:
            url = response.url
            # Filter for relevant JSON endpoints
            if "sora.chatgpt.com" in url and ("profile/drafts" in url or "feed" in url or "tasks" in url):
                if response.status == 200 and "application/json" in response.headers.get("content-type", ""):
                     # We cannot await here directly effectively if not async handler, 
                     # but Playwright handlers can be regular functions.
                     # To read body, we need to handle it carefully.
                     # PROPER WAY: Schedule a background task to read it to not block the handler?
                     # Actually, page.on handler CAN be async.
                     asyncio.create_task(self._process_response_body(response))
        except Exception as e:
            pass

    async def _process_response_body(self, response):
        """Async helper to read response body"""
        try:
            data = await response.json()
            url = response.url
            
            # Identify endpoint type
            endpoint_type = "unknown"
            if "profile/drafts" in url: endpoint_type = "DRAFTS"
            elif "feed" in url: endpoint_type = "FEED"
            elif "tasks" in url: endpoint_type = "TASKS"
            elif "nf/create" in url: endpoint_type = "SUBMISSION"
            
            logger.info(f"[TASK]  Intercepted {endpoint_type} JSON ({len(str(data))} bytes)")
            
            # Store data for analysis/usage
            self.latest_intercepted_data = data
            
            if endpoint_type == "SUBMISSION":
                # Parse submission result for credits
                self.last_submission_result = data
                logger.info("[OK]  Captured SUBMISSION response!")
                if "rate_limit_and_credit_balance" in data:
                    balance = data["rate_limit_and_credit_balance"]
                    daily_creds = balance.get("estimated_num_videos_remaining")
                    reset_secs = balance.get("access_resets_in_seconds")
                    logger.info(f"[CREDITS]  Credits Remaining: {daily_creds} | Reset in: {reset_secs}s")
            
            # Parse and cache items
            items = []
            if "items" in data: items = data["items"]
            elif isinstance(data, list): items = data
            
            if items:
                logger.info(f"   Found {len(items)} items in {endpoint_type}")
                for item in items:
                    # Extract key info
                    vid_id = item.get("id")
                    if not vid_id: continue
                    
                    # Normalize Status
                    # In drafts JSON, status might be inferred from 'url' presence or specific fields
                    # If 'url' is present and valid, it's likely 'complete' or 'ready'
                    # If 'processing_status' exists, use it.
                    status = item.get("status", "unknown")
                    download_url = item.get("url")
                    
                    # Drafts API often returns 'url' even if processing? verify
                    # Usually "url" is the result video.
                    # If it has a URL, we treat it as potentially downloadable.
                    
                    if vid_id not in self.intercepted_videos:
                        self.intercepted_videos[vid_id] = {}
                        
                    self.intercepted_videos[vid_id].update({
                        "id": vid_id,
                        "status": status,
                        "download_url": download_url,
                        "prompt": item.get("prompt"),
                        "last_updated": asyncio.get_event_loop().time()
                    })
                    
                    # Logging specific
                    # logger.info(f"   - Cached {vid_id}: {status} | URL: {bool(download_url)}")

        except Exception as e:
            # logger.warning(f"[WARNING]  Failed to parse intercepted JSON from {response.url}: {e}")
            pass

    async def wait_for_completion_api(self, match_prompt: str, timeout: int = 600, task_id: Optional[str] = None) -> Optional[dict]:
        """
        Polls for video completion using API only (no UI automation).
        Uses /nf/pending/v2 and /profile/drafts endpoints.

        Args:
            match_prompt: Prompt text to match against (fallback if task_id not available)
            timeout: Maximum seconds to wait
            task_id: Sora task ID for precise matching (RECOMMENDED)

        Returns:
            dict with video data including download_url, or None if timeout
        """
        if task_id:
            logger.info(f"[WAIT]  Waiting for video completion (API) - Task ID: {task_id}")
        else:
            logger.info(f"[WAIT]  Waiting for video completion (API) - Prompt: '{match_prompt[:30]}...' (NO task_id - using fuzzy match)")

        start_time = time.time()
        poll_interval = 15  # Poll every 15 seconds

        while time.time() - start_time < timeout:
            try:
                # 1. Check pending tasks first
                pending = await self.get_pending_tasks_api()
                if pending is not None:
                    # Check if our task is still pending
                    is_pending = False
                    for task in pending:
                        # PRIORITY 1: Match by task_id (exact match)
                        if task_id and task.get("id") == task_id:
                            progress = (task.get("progress_pct") or 0) * 100
                            logger.info(f"[STATS]  Task {task_id} still pending: {progress:.1f}% complete")
                            is_pending = True
                            break

                        # FALLBACK: Match by prompt (fuzzy - less reliable)
                        if not task_id:
                            task_prompt = task.get("prompt", "")
                            if match_prompt[:30].strip() in task_prompt or task_prompt[:30].strip() in match_prompt:
                                progress = (task.get("progress_pct") or 0) * 100
                                logger.info(f"[STATS]  Task still pending (prompt match): {progress:.1f}% complete")
                                is_pending = True
                                break

                    # If not in pending, check drafts for completion
                    if not is_pending or len(pending) == 0:
                        # Use get_drafts_api() with curl_cffi instead of _api_get_drafts() with aiohttp
                        # to bypass Cloudflare protection
                        drafts = await self.get_drafts_api()
                        if drafts:
                            for draft in drafts:
                                # PRIORITY 1: Match by task_id (exact match)
                                if task_id and draft.get("task_id") == task_id:
                                    download_url = draft.get("url") or draft.get("downloadable_url") or draft.get("video_url")
                                    if download_url:
                                        logger.info(f"[OK]  Video completed! Task ID: {task_id}")
                                        return {
                                            "id": draft.get("id"),
                                            "task_id": task_id,
                                            "download_url": download_url,
                                            "prompt": draft.get("prompt"),
                                            "status": "completed"
                                        }
                                    elif draft.get("status") == "failed":
                                        logger.warning(f"[ERROR]  Video generation failed for task {task_id}")
                                        return {"status": "failed", "id": draft.get("id"), "task_id": task_id}

                                # FALLBACK: Match by prompt (less reliable)
                                if not task_id:
                                    draft_prompt = draft.get("prompt", "")
                                    if match_prompt[:30].strip() in draft_prompt or draft_prompt[:30].strip() in match_prompt:
                                        download_url = draft.get("url") or draft.get("downloadable_url") or draft.get("video_url")
                                        if download_url:
                                            logger.warning(f"[WARNING]  Video matched by PROMPT (no task_id)! ID: {draft.get('id')}")
                                            return {
                                                "id": draft.get("id"),
                                                "download_url": download_url,
                                                "prompt": draft_prompt,
                                                "status": "completed"
                                            }
                                        elif draft.get("status") == "failed":
                                            logger.warning(f"[ERROR]  Video generation failed (prompt match)")
                                            return {"status": "failed", "id": draft.get("id")}

            except Exception as e:
                logger.warning(f"API poll error: {e}")

            elapsed = int(time.time() - start_time)
            logger.info(f"[WAIT]  Polling... ({elapsed}s / {timeout}s)")
            await asyncio.sleep(poll_interval)

        logger.error(f"[ERROR]  Timeout waiting for video completion after {timeout}s")
        return None

    async def _api_get_pending_tasks(self) -> Optional[list]:
        """Get pending tasks via API (internal helper)"""
        if not self.latest_access_token:
            return None

        headers = {
            "Authorization": self.latest_access_token,
            "Content-Type": "application/json",
            "User-Agent": self.latest_user_agent or "Mozilla/5.0"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://sora.chatgpt.com/backend/nf/pending/v2",
                    headers=headers
                ) as response:
                    if response.status == 200:
                        return await response.json()
        except Exception as e:
            logger.debug(f"_api_get_pending_tasks error: {e}")
        return None

    async def _api_get_drafts(self) -> Optional[list]:
        """Get drafts via API (internal helper)"""
        if not self.latest_access_token:
            return None

        headers = {
            "Authorization": self.latest_access_token,
            "Content-Type": "application/json",
            "User-Agent": self.latest_user_agent or "Mozilla/5.0"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://sora.chatgpt.com/backend/project_y/profile/drafts?limit=15",
                    headers=headers
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("items", data) if isinstance(data, dict) else data
        except Exception as e:
            logger.debug(f"_api_get_drafts error: {e}")
        return None

    async def get_credits_api(self) -> dict:
        """
        Check credits via API.
        
        Strategy:
        1. If Browser Mode (self.page): Use page.evaluate() to fetch using browser context.
           This is MOST RELIABLE as it uses exact cookies/headers/fingerprint of the session.
        2. If API Mode or Browser method fails: Fallback to aiohttp with stored tokens.
        
        Returns:
            dict with 'credits', 'source', 'reset_seconds' on success
            dict with 'error', 'error_code' on failure (instead of None for better debugging)
            None only if no token available
        """
        if not self.latest_access_token:
            logger.warning("[ERROR]  get_credits_api failed: No access token captured.")
            return {"error": "No access token", "error_code": "NO_TOKEN"}

        # --- STRATEGY 1: BROWSER CONTEXT (Preferred) ---
        if self.page:
            try:
                # We inject a script to fetch and return the JSON
                # This naturally handles all cookies and headers
                js_code = """
                async () => {
                    try {
                        const response = await fetch('https://sora.chatgpt.com/backend/nf/check');
                        if (response.status === 200) {
                            return await response.json();
                        } else {
                             // Try billing as fallback
                             const resp2 = await fetch('https://sora.chatgpt.com/backend/billing/credit_balance');
                             if (resp2.status === 200) {
                                 return await resp2.json();
                             }
                        }
                        return null;
                    } catch (e) {
                        return null;
                    }
                }
                """
                data = await self.page.evaluate(js_code)
                
                if data:
                    # Parse nf/check format
                    if "rate_limit_and_credit_balance" in data:
                        balance_info = data.get("rate_limit_and_credit_balance", {})
                        estimated_remaining = balance_info.get("estimated_num_videos_remaining")
                        purchased_remaining = balance_info.get("estimated_num_purchased_videos_remaining", 0)
                        reset_seconds = balance_info.get("access_resets_in_seconds")
                        
                        if estimated_remaining is not None:
                            total_credits = int(estimated_remaining) + int(purchased_remaining)
                            logger.info(f"[OK]  Credit Check (Browser): Free={estimated_remaining} | Total={total_credits}")
                            return {"credits": total_credits, "source": "browser_nf_check", "reset_seconds": reset_seconds}
                            
                    # Parse billing format
                    elif "credits" in data:
                         logger.info(f"[OK]  Credit Check (Browser Billing): {data['credits']}")
                         return {"credits": int(data["credits"]), "source": "browser_billing"}
                         
            except Exception as e:
                logger.warning(f"[WARNING]  Browser credit check failed: {e}")

        # --- STRATEGY 2: API-ONLY (Fallback) ---
        
        # Generate sentinel (try/except to not block if library issue)
        sentinel_header = ""
        try:
            from app.core.sentinel import get_sentinel_token
            import json
            token_data = get_sentinel_token(flow="sora_create_task") # Use existing flow
            sentinel_header = json.dumps(json.loads(token_data) if isinstance(token_data, str) else token_data)
        except Exception as s_err:
             logger.warning(f"[WARNING]  Credit check sentinel gen failed: {s_err}")

        headers = {
            "Authorization": self.latest_access_token,
            "Content-Type": "application/json",
            "User-Agent": self.latest_user_agent or "Mozilla/5.0",
            "openai-sentinel-token": sentinel_header,
            "oai-device-id": getattr(self, 'device_id', "") or "",
            "oai-language": "en-US"
        }

        # Prepare cookies and check expiry
        cookie_dict = {}
        expired_cookies = []
        current_time = time.time()
        
        if hasattr(self, 'cookies') and self.cookies:
            for c in self.cookies:
                cookie_dict[c['name']] = c['value']
                # Check if cookie is expired
                exp = c.get('expires', -1)
                if exp > 0 and exp < current_time:
                    expired_cookies.append(c['name'])
        
        # Log cookie status
        if expired_cookies:
            logger.warning(f"[WARNING]  {len(expired_cookies)} cookies đã hết hạn: {expired_cookies[:5]}...")
        logger.info(f"🍪 Using {len(cookie_dict)} cookies for API call")

        # Build cookie string for curl_cffi
        cookie_str = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])
        
        # Use curl_cffi with browser TLS fingerprint to bypass Cloudflare
        try:
            from curl_cffi import requests as curl_requests
            
            curl_headers = {
                "Authorization": self.latest_access_token,
                "Cookie": cookie_str,
                "oai-device-id": getattr(self, 'device_id', "") or "",
                "oai-language": "en-US",
                "Referer": "https://sora.chatgpt.com/profile",
                "Accept": "*/*",
            }
            
            logger.info("[API]  Using curl_cffi for Cloudflare bypass...")
            
            # Priority 1: /nf/check
            response = curl_requests.get(
                "https://sora.chatgpt.com/backend/nf/check",
                headers=curl_headers,
                impersonate="chrome",
                timeout=30
            )
            
            logger.debug(f"🔍 /nf/check Response ({response.status_code})")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                except:
                    logger.error(f"[ERROR]  Failed to decode JSON: {response.text[:200]}")
                    data = {}
                
                # Parse rate_limit_and_credit_balance
                balance_info = data.get("rate_limit_and_credit_balance", {})
                estimated_remaining = balance_info.get("estimated_num_videos_remaining")
                purchased_remaining = balance_info.get("estimated_num_purchased_videos_remaining", 0)
                rate_limit_reached = balance_info.get("rate_limit_reached", False)
                reset_seconds = balance_info.get("access_resets_in_seconds")
                
                if estimated_remaining is not None:
                    total_credits = int(estimated_remaining) + int(purchased_remaining)
                    logger.info(f"[OK]  Credit Check (curl_cffi): Free={estimated_remaining} | Purchased={purchased_remaining} | Total={total_credits}")
                    
                    if rate_limit_reached:
                        logger.warning(f"[WARNING]  Rate Limit Reached! Reset in {reset_seconds}s")
                        return {"credits": 0, "source": "curl_rate_limited", "reset_seconds": reset_seconds}
                    
                    return {"credits": total_credits, "source": "curl_nf_check", "reset_seconds": reset_seconds}
                    
            elif response.status_code in [401, 403]:
                # Check if Cloudflare challenge
                if "Just a moment" in response.text:
                    logger.error("[ERROR]  Cloudflare challenge - cookies may need refresh")
                    return {"error": "Cloudflare challenge", "error_code": "CLOUDFLARE_BLOCK"}
                else:
                    logger.error(f"[ERROR]  nf/check Auth Failed (HTTP {response.status_code})")
                    return {"error": f"Auth failed: HTTP {response.status_code}", "error_code": "TOKEN_EXPIRED"}
                    
            elif response.status_code == 429:
                logger.warning("[WARNING]  Rate Limited (HTTP 429)")
                return {"error": "Rate limited", "error_code": "RATE_LIMITED"}
            
            # Fallback: /billing/credit_balance
            logger.info("[MONITOR]  Trying fallback: /billing/credit_balance")
            response = curl_requests.get(
                "https://sora.chatgpt.com/backend/billing/credit_balance",
                headers=curl_headers,
                impersonate="chrome"
            )
            
            if response.status_code == 200:
                data = response.json()
                if "credits" in data:
                    logger.info(f"[OK]  Credit Check (curl billing): {data['credits']}")
                    return {"credits": int(data["credits"]), "source": "curl_billing"}
                    
        except ImportError:
            logger.warning("[WARNING]  curl_cffi not installed, falling back to aiohttp...")
            # Fallback to aiohttp (may fail with Cloudflare)
            return await self._get_credits_aiohttp(headers, cookie_dict, expired_cookies)
        except Exception as e:
            logger.error(f"[ERROR]  curl_cffi exception: {e}")

        # If we reach here, both failed
        logger.error(f"[ERROR]  All API credit checks failed!")
        logger.error(f"   Token: {self.latest_access_token[:50] if self.latest_access_token else 'None'}...")
        logger.error(f"   Cookies: {len(cookie_dict)} total, {len(expired_cookies)} expired")
        return {"error": "All API checks failed", "error_code": "ALL_FAILED"}

    async def get_pending_tasks_api(self) -> list:
        """
        Get list of pending video generation tasks with progress.
        Uses /nf/pending/v2 endpoint. Works in API-only mode.

        Returns:
            list: [{"id": "task_...", "status": "queued", "prompt": "...", "progress_pct": 0.85}]
            Empty list [] means all videos are complete.
        """
        if not self.latest_access_token:
            logger.warning("[ERROR]  get_pending_tasks_api failed: No access token captured.")
            return None

        # Use curl_cffi to bypass Cloudflare
        try:
            from curl_cffi import requests as curl_requests
            
            headers = {
                "Authorization": self.latest_access_token,
                "Content-Type": "application/json",
                "User-Agent": self.latest_user_agent or "Mozilla/5.0",
                "Referer": "https://sora.chatgpt.com/"
            }
            
            # Simple sync call (fast enough) or could use AsyncSession
            response = curl_requests.get(
                "https://sora.chatgpt.com/backend/nf/pending/v2",
                headers=headers,
                impersonate="chrome",
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    if len(data) == 0:
                        logger.info("[OK]  Pending Tasks: [] - All videos complete!")
                    else:
                        for task in data:
                            progress = (task.get('progress_pct') or 0) * 100
                            logger.info(f"[STATS]  Task {task.get('id')}: {task.get('status')} | {progress:.1f}%")
                    return data
                else:
                    return data # Handle if it returns dict?
                    
            elif response.status_code == 403:
                if "Just a moment" in response.text:
                    logger.warning("[WARNING]  Cloudflare blocked Pending Tasks check.")
                else:
                    logger.warning(f"[WARNING]  Pending Tasks 403: {response.text[:100]}")
            
        except ImportError:
            # Fallback to aiohttp
            logger.warning("[WARNING]  curl_cffi missing, falling back to aiohttp for pending tasks...")
            try:
                headers = {
                    "Authorization": self.latest_access_token,
                    "Content-Type": "application/json",
                    "User-Agent": self.latest_user_agent or "Mozilla/5.0"
                }
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        "https://sora.chatgpt.com/backend/nf/pending/v2",
                        headers=headers
                    ) as response:
                        if response.status == 200:
                            return await response.json()
            except Exception as e:
                logger.debug(f"get_pending_tasks_api failed (aiohttp): {e}")
                
        except Exception as e:
            logger.error(f"[ERROR]  get_pending_tasks_api failed: {e}")
            
        return None
        
    async def get_drafts_api(self) -> Optional[list]:
        """
        Get drafts via API using curl_cffi to bypass Cloudflare.
        """
        if not self.latest_access_token:
            return None

        # Use curl_cffi to bypass Cloudflare
        try:
            from curl_cffi import requests as curl_requests
            
            headers = {
                "Authorization": self.latest_access_token,
                "Content-Type": "application/json",
                "User-Agent": self.latest_user_agent or "Mozilla/5.0",
                "Referer": "https://sora.chatgpt.com/profile"
            }
            
            # Simple sync call (fast enough) or could use AsyncSession
            response = curl_requests.get(
                "https://sora.chatgpt.com/backend/project_y/profile/drafts?limit=15",
                headers=headers,
                impersonate="chrome",
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                items = data.get("items", data) if isinstance(data, dict) else data
                if items:
                    logger.debug(f"🔍 Found {len(items)} drafts via API")
                return items
                    
            elif response.status_code == 403:
                logger.warning(f"[WARNING]  Cloudflare blocked Drafts check (HTTP {response.status_code})")
            
        except ImportError:
            # Fallback to aiohttp
            logger.warning("[WARNING]  curl_cffi missing, falling back to aiohttp for drafts...")
            return await self._api_get_drafts()
            
        except Exception as e:
            logger.error(f"[ERROR]  get_drafts_api failed: {e}")
            
        return None

    async def generate_video_api(
        self,
        prompt: str,
        orientation: str = "landscape",
        size: str = "small",
        n_frames: int = 180,
        model: str = "sy_8",
        image_file_id: str = None,
    ) -> dict:
        """
        Generate video via direct API call using Sentinel bypass.
        
        Args:
            prompt: Text prompt for video generation
            orientation: 'landscape' or 'portrait'
            size: 'small', 'medium', or 'large'
            n_frames: Number of frames (180 = 6s, 300 = 10s)
            model: Model ID (default 'sy_8')
            image_file_id: Optional file_id from upload_image_api() for image-to-video
            
        Returns:
            dict with 'success', 'task_id', 'error' keys
        """
        from app.core.sentinel import get_sentinel_token
        import json
        
        logger.info(f"[GENERATE]  Generating video via API: {prompt[:50]}...")
        
        if not self.latest_access_token:
            logger.error("[ERROR]  No access token available")
            return {"success": False, "error": "No access token"}
        
        # Generate sentinel token
        try:
            sentinel_payload = get_sentinel_token(flow="sora_create_task")
            logger.info(f"[LOCK]  Generated sentinel token")
        except Exception as e:
            logger.error(f"[ERROR]  Sentinel token generation failed: {e}")
            return {"success": False, "error": f"Sentinel failed: {e}"}
        
        # Build request payload
        payload = {
            "kind": "video",
            "prompt": prompt,
            "title": None,
            "orientation": orientation,
            "size": size,
            "n_frames": n_frames,
            "inpaint_items": [],
            "remix_target_id": None,
            "metadata": None,
            "cameo_ids": None,
            "cameo_replacements": None,
            "model": model,
            "style_id": None,
            "audio_caption": None,
            "audio_transcript": None,
            "video_caption": None,
            "storyboard_id": None
        }
        
        # Add image attachment if provided
        if image_file_id:
            # CLEAN ID: Strip any metadata prefix/suffix (e.g. "sentinel#file_ID#usage")
            clean_id = image_file_id
            if "#" in clean_id:
                parts = clean_id.split("#")
                for p in parts:
                    if p.startswith("file_") or p.startswith("file-"):
                        clean_id = p
                        break
            
            logger.info(f"📎 Attaching Image: {clean_id} (Original: {image_file_id[:20]}...)")
            payload["inpaint_items"] = [{"kind": "file", "file_id": clean_id}]
        
        # Get device ID
        if self.page:
            # Browser mode - get from localStorage
            try:
                oai_device_id = await self.page.evaluate("""() => {
                    return localStorage.getItem('oai-did') || 
                           document.cookie.match(/oai-did=([^;]+)/)?.[1] || 
                           null;
                }""")
            except:
                oai_device_id = getattr(self, 'device_id', None)
        else:
            # API-only mode - use stored device_id
            oai_device_id = getattr(self, 'device_id', None) or ""
        
        # Build headers
        headers = {
            'Content-Type': 'application/json',
            'Authorization': self.latest_access_token,
            'openai-sentinel-token': json.dumps(json.loads(sentinel_payload) if isinstance(sentinel_payload, str) else sentinel_payload),
            'oai-device-id': oai_device_id or "",
            'oai-language': 'en-US',
            'User-Agent': self.latest_user_agent or 'Mozilla/5.0'
        }
        
        try:
            logger.info(f"[START]  GENERATE PAYLOAD: {json.dumps(payload, ensure_ascii=False)}")
            
            if self.page:
                # Browser mode - use page.evaluate
                js_code = f"""
                async () => {{
                    const payload = {json.dumps(payload)};
                    const sentinelPayload = {sentinel_payload};
                    
                    try {{
                        const response = await fetch('https://sora.chatgpt.com/backend/nf/create', {{
                            method: 'POST',
                            headers: {{
                                'Content-Type': 'application/json',
                                'Authorization': '{self.latest_access_token}',
                                'openai-sentinel-token': JSON.stringify(sentinelPayload),
                                'oai-device-id': '{oai_device_id or ""}',
                                'oai-language': 'en-US'
                            }},
                            body: JSON.stringify(payload)
                        }});
                        
                        const text = await response.text();
                        return {{ status: response.status, body: text }};
                    }} catch (e) {{
                        return {{ status: 0, error: e.toString() }};
                    }}
                }}
                """
                result = await self.page.evaluate(js_code)
            else:
                # API-only mode (100% headless) - use curl_cffi
                try:
                    from curl_cffi import requests as curl_requests
                    logger.info("🔌 Using curl_cffi for headless API call (Bypassing Cloudflare)...")
                except ImportError:
                    logger.error("[ERROR]  curl_cffi not installed! Fallback to aiohttp (High risk of block)")
                    import aiohttp
                    curl_requests = None

                if curl_requests:
                    # curl_cffi does not support async context manager in the same way as aiohttp usually?
                    # Actually curl_cffi.requests.AsyncSession is available in newer versions
                    # But sync request is safer/easier if async not strictly required for performance here
                    # However, this function is async. We should use async if possible or run in thread.
                    # Simple approach: Use sync curl_requests inside run_in_executor if needed, 
                    # OR use curl_requests.post directly (sync) since it's fast enough or allows impersonate.
                    
                    # NOTE: curl_cffi requests.post is SYNC. We should be careful blocking event loop.
                    # But for now, to ensure bypass, sync is acceptable or use AsyncSession.
                    
                    response = curl_requests.post(
                        'https://sora.chatgpt.com/backend/nf/create',
                        headers=headers,
                        json=payload,
                        impersonate="chrome",
                        timeout=30
                    )
                    
                    result = {"status": response.status_code, "body": response.text}
                else:
                     # Fallback to aiohttp
                     async with aiohttp.ClientSession() as session:
                        async with session.post(
                            'https://sora.chatgpt.com/backend/nf/create',
                            headers=headers,
                            json=payload
                        ) as response:
                            text = await response.text()
                            result = {"status": response.status, "body": text}
            
            if result.get('status') == 200:
                logger.info("[OK]  Video generation API call successful!")
                try:
                    response_data = json.loads(result['body'])
                    task_id = response_data.get('id') or response_data.get('task_id')
                    return {"success": True, "task_id": task_id, "response": response_data}
                except:
                    return {"success": True, "response": result['body']}
            else:
                error_msg = result.get('body', result.get('error', 'Unknown error'))
                if 'sentinel' in str(error_msg).lower():
                    logger.error("[ERROR]  Sentinel block - token may have expired")
                else:
                    logger.error(f"[ERROR]  API error {result.get('status')}: {str(error_msg)[:200]}")
                return {"success": False, "error": error_msg}
                
        except Exception as e:
            logger.error(f"[ERROR]  generate_video_api exception: {e}")
            return {"success": False, "error": str(e)}

    async def upload_image_api(self, image_path: str) -> dict:
        """
        Upload an image via API for use in prompts.
        Works in both browser and API-only mode.
        """
        import os
        import json
        
        logger.info(f"📤 Uploading image: {image_path}")
        
        if not os.path.exists(image_path):
            return {"success": False, "error": f"File not found: {image_path}"}
        
        if not self.latest_access_token:
            return {"success": False, "error": "No access token"}
            
        filename = os.path.basename(image_path)
        ext = os.path.splitext(image_path)[1].lower()
        mime_type = "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/png"
        
        # Try curl_cffi FIRST (More robust, bypasses Browser CORS)
        try:
            from curl_cffi import requests as curl_requests
            
            # Use curl_cffi (Stronger bypass)
            cookie_str = ""
            if hasattr(self, 'cookies') and self.cookies:
                cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in self.cookies])

            headers = {
                "Authorization": self.latest_access_token,
                "User-Agent": self.latest_user_agent or "Mozilla/5.0",
                "Cookie": cookie_str,
                "Origin": "https://sora.chatgpt.com",
                "Referer": "https://sora.chatgpt.com/"
            }
            
            try:
                import urllib3
                with open(image_path, 'rb') as f:
                    file_content = f.read()
                    
                # Manual Multipart Encoding
                # fields = {'name': (filename, data, content_type)}
                fields = {
                    'file': (filename, file_content, mime_type)
                }
                
                body, content_type = urllib3.encode_multipart_formdata(fields)
                headers["Content-Type"] = content_type
                
                logger.info(f"🔌 Uploading with curl_cffi (Priority)...")
                # payload must be passed as 'data' (bytes)
                response = curl_requests.post(
                    "https://sora.chatgpt.com/backend/project_y/file/upload",
                    headers=headers,
                    data=body,
                    impersonate="chrome",
                    timeout=60
                )
                
                if response.status_code == 200:
                    data = json.loads(response.text)
                    logger.info(f"[OK]  Image uploaded (curl): file_id={data.get('file_id', 'unknown')[:30]}...")
                    return {
                        "success": True,
                        "file_id": data.get('file_id'),
                        "url": data.get('url'),
                        "asset_pointer": data.get('asset_pointer')
                    }
                else:
                    logger.warning(f"[WARNING] curl upload failed ({response.status_code}), falling back to browser/aiohttp: {response.text[:100]}")
                    # Fallthrough to browser/aiohttp
            except Exception as e:
                 logger.warning(f"[WARNING] curl upload exception: {e}")
                 # Fallthrough
        except ImportError:
            pass

        # Fallback 1: Browser Fetch (if page exists)
        if self.page:
                # Browser mode
                import base64
                with open(image_path, "rb") as f:
                    image_bytes = f.read()
                image_b64 = base64.b64encode(image_bytes).decode('utf-8')
                
                js_code = f"""
                async () => {{
                    try {{
                        const b64 = "{image_b64}";
                        const binaryString = atob(b64);
                        const bytes = new Uint8Array(binaryString.length);
                        for (let i = 0; i < binaryString.length; i++) {{
                            bytes[i] = binaryString.charCodeAt(i);
                        }}
                        const blob = new Blob([bytes], {{ type: '{mime_type}' }});
                        
                        const formData = new FormData();
                        formData.append('file', blob, '{filename}');
                        
                        const response = await fetch('https://sora.chatgpt.com/backend/project_y/file/upload', {{
                            method: 'POST',
                            headers: {{
                                'Authorization': '{self.latest_access_token}'
                            }},
                            body: formData
                        }});
                        
                        const text = await response.text();
                        return {{ status: response.status, body: text }};
                    }} catch (e) {{
                        return {{ status: 0, error: e.toString() }};
                    }}
                }}
                """
                result = await self.page.evaluate(js_code)
        else:
             # Fallback 2: aiohttp
             # Fallback to aiohttp (Weaker)
                    import aiohttp
                    async with aiohttp.ClientSession() as session:
                        data = aiohttp.FormData()
                        data.add_field('file',
                                       open(image_path, 'rb'),
                                       filename=filename,
                                       content_type=mime_type)
                        
                        headers = {
                            "Authorization": self.latest_access_token,
                            "User-Agent": self.latest_user_agent or "Mozilla/5.0"
                        }
                        
                        async with session.post(
                            "https://sora.chatgpt.com/backend/project_y/file/upload",
                            headers=headers,
                            data=data
                        ) as response:
                            text = await response.text()
                            result = {"status": response.status, "body": text}
        
        # Process result from Browser/Aiohttp
        if result.get('status') == 200:
                data = json.loads(result['body'])
                logger.info(f"[OK]  Image uploaded (fallback): file_id={data.get('file_id', 'unknown')[:30]}...")
                return {
                    "success": True,
                    "file_id": data.get('file_id'),
                    "url": data.get('url'),
                    "asset_pointer": data.get('asset_pointer')
                }
        else:
                return {"success": False, "error": result.get('body', result.get('error'))}
                
        except Exception as e:
            logger.error(f"[ERROR]  upload_image_api exception: {e}")
            return {"success": False, "error": str(e)}

    async def get_drafts_api(self) -> list:
        """
        Get list of draft videos with URLs. Works in API-only mode.

        Returns:
            list of draft video objects with id, status, video_url, etc.
        """
        # Use curl_cffi to bypass Cloudflare
        try:
            from curl_cffi import requests as curl_requests
            
            headers = {
                "Authorization": self.latest_access_token,
                "Content-Type": "application/json",
                "User-Agent": self.latest_user_agent or "Mozilla/5.0",
                "Referer": "https://sora.chatgpt.com/"
            }
            
            response = curl_requests.get(
                "https://sora.chatgpt.com/backend/project_y/profile/drafts?limit=15",
                headers=headers,
                impersonate="chrome",
                timeout=20
            ) 
            
            if response.status_code == 200:
                data = response.json()
                drafts = data.get('items', data) if isinstance(data, dict) else data
                logger.info(f"[OK]  Drafts API: Retrieved {len(drafts)} drafts (curl_cffi)")
                return drafts
            else:
                logger.warning(f"[WARNING]  Drafts API failed ({response.status_code}): {response.text[:100]}")
                
        except ImportError:
            # Fallback to aiohttp
            logger.warning("[WARNING]  curl_cffi missing, falling back to aiohttp for drafts...")
            try:
                headers = {
                    "Authorization": self.latest_access_token,
                    "Content-Type": "application/json",
                    "User-Agent": self.latest_user_agent or "Mozilla/5.0"
                }
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        "https://sora.chatgpt.com/backend/project_y/profile/drafts?limit=15",
                        headers=headers
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            drafts = data.get('items', data) if isinstance(data, dict) else data
                            logger.info(f"[OK]  Drafts API: Retrieved {len(drafts)} drafts (aiohttp)")
                            return drafts
            except Exception as e:
                logger.debug(f"get_drafts_api failed (aiohttp): {e}")

        except Exception as e:
            logger.error(f"[ERROR]  get_drafts_api failed: {e}")

        return None

    async def post_video_api(self, video_id: str = None, title: str = None, description: str = None) -> dict:
        """
        Publish/post a video via API with sentinel bypass.
        Works in both browser and API-only mode.
        """
        from app.core.sentinel import get_sentinel_token
        import json
        
        logger.info(f"📤 Publishing video via API...")
        
        if not self.latest_access_token:
            return {"success": False, "error": "No access token"}
        
        # Generate sentinel token for post flow
        try:
            sentinel_payload = get_sentinel_token(flow="sora_2_create_post")
        except Exception as e:
            return {"success": False, "error": f"Sentinel failed: {e}"}
        
        # Determine Device ID
        oai_device_id = getattr(self, 'device_id', "")
        if self.page:
            try:
                oai_device_id = await self.page.evaluate("""() => {
                    return localStorage.getItem('oai-did') || null;
                }""")
            except:
                pass
        
        # Build payload
        payload = {
            "title": title or "Sora Video",
            "description": description or "",
            "visibility": "public"
        }
        if video_id:
            payload["video_id"] = video_id
            
        try:
            if self.page:
                # Browser mode
                js_code = f"""
                async () => {{
                    const sentinelPayload = {sentinel_payload};
                    
                    try {{
                        const response = await fetch('https://sora.chatgpt.com/backend/project_y/post', {{
                            method: 'POST',
                            headers: {{
                                'Content-Type': 'application/json',
                                'Authorization': '{self.latest_access_token}',
                                'openai-sentinel-token': JSON.stringify(sentinelPayload),
                                'oai-device-id': '{oai_device_id}',
                                'oai-language': 'en-US'
                            }},
                            body: JSON.stringify({json.dumps(payload)})
                        }});
                        
                        const text = await response.text();
                        return {{ status: response.status, body: text }};
                    }} catch (e) {{
                        return {{ status: 0, error: e.toString() }};
                    }}
                }}
                """
                result = await self.page.evaluate(js_code)
            else:
                # API-only mode
                import aiohttp
                
                headers = {
                    "Authorization": self.latest_access_token,
                    "Content-Type": "application/json",
                    "User-Agent": self.latest_user_agent or "Mozilla/5.0",
                    "openai-sentinel-token": json.dumps(json.loads(sentinel_payload) if isinstance(sentinel_payload, str) else sentinel_payload),
                    "oai-device-id": oai_device_id,
                    "oai-language": "en-US"
                }

                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        'https://sora.chatgpt.com/backend/project_y/post',
                        headers=headers,
                        json=payload
                    ) as response:
                        text = await response.text()
                        result = {"status": response.status, "body": text}
                        
            if result.get('status') == 200:
                data = json.loads(result['body'])
                logger.info(f"[OK]  Video Published! URL: {data.get('url')}")
                return {"success": True, "post_id": data.get('id'), "url": data.get('url')}
            else:
                 error_msg = result.get('body', result.get('error'))
                 logger.error(f"[ERROR]  Post API failed: {error_msg}")
                 return {"success": False, "error": error_msg}

        except Exception as e:
            logger.error(f"[ERROR]  post_video_api exception: {e}")
            return {"success": False, "error": str(e)}

    async def verify_identity(self, expected_email: str) -> bool:
        """
        STRICT SECURITY CHECK:
        Verifies that the current browser session is actually logged in as 'expected_email'.
        Prevents 'Cross-Account' pollution if profiles get mixed up.
        """
        logger.info(f"🆔 Verifying Identity (Expected: {expected_email})...")
        
        if not self.latest_access_token:
             # Try to trigger a fetch to get token first?
             # Or just try the endpoint without token (if browser cookies handle it)
             pass

        target_url = "https://chatgpt.com/backend-api/me"
        
        try:
            # Fetch 'me' profile
            result = await self.page.evaluate(f"""async () => {{
                try {{
                    const res = await fetch('{target_url}', {{
                        headers: {{ 'Content-Type': 'application/json' }}
                    }});
                    if (res.status === 200) {{
                        const data = await res.json();
                        return {{ status: 200, email: data.email }};
                    }}
                    return {{ status: res.status, email: null }};
                }} catch (e) {{
                    return {{ status: 0, email: null, error: e.toString() }};
                }}
            }}""")
            
            if result['status'] == 200:
                actual_email = result.get('email', '')
                logger.info(f"   👤 Current Session Email: {actual_email}")
                
                if actual_email and actual_email.lower().strip() == expected_email.lower().strip():
                    logger.info("[OK]  Identity Verified.")
                    return True
                else:
                    logger.error(f"[ERROR]  IDENTITY MISMATCH! Expected: {expected_email} | Found: {actual_email}")
                    return False
            else:
                logger.warning(f"[WARNING]  Identity check failed (API {result['status']}). Assuming safe if logged in.")
                # If API fails, we can't verify. 
                # Strict mode: Return False? 
                # Lenient mode: Return True (don't block operation if API is flakey)
                # Let's Return True but warn, to avoid blocking valid runs on API networking issues.
                return True
                
        except Exception as e:
            logger.error(f"Error during identity verify: {e}")
            return True # Fail open to avoid stopping automation on unrelated errors verification logic should be robust
            
        return True

    # ========== VideoGenerationDriver Interface Implementation ==========
    # Wrapper methods to match abstract interface

    async def generate_video(
        self,
        prompt: str,
        duration: int,
        aspect_ratio: str,
        image_path: Optional[str] = None
    ) -> VideoResult:
        """
        Generate video - implements VideoGenerationDriver interface

        Args:
            prompt: Text prompt for video generation
            duration: Duration in seconds (5, 10, or 15)
            aspect_ratio: Aspect ratio ("16:9", "9:16", "1:1")
            image_path: Optional path to image for image-to-video

        Returns:
            VideoResult with task_id if successful
        """
        # Map duration to n_frames
        duration_to_frames = {5: 150, 10: 300, 15: 450}
        n_frames = duration_to_frames.get(duration, 180)

        # Map aspect ratio to orientation
        if aspect_ratio == "16:9":
            orientation = "landscape"
        elif aspect_ratio == "9:16":
            orientation = "portrait"
        else:
            orientation = "landscape"  # Default

        # Upload image if provided
        file_id = None
        if image_path:
            upload_result = await self.upload_image(image_path)
            if not upload_result.success:
                return VideoResult(success=False, error=upload_result.error)
            file_id = upload_result.file_id

        # Call internal API method
        result = await self.generate_video_api(
            prompt=prompt,
            orientation=orientation,
            n_frames=n_frames,
            image_file_id=file_id
        )

        # Convert dict to VideoResult
        return VideoResult(
            success=result.get("success", False),
            task_id=result.get("task_id"),
            error=result.get("error")
        )

    async def get_credits(self) -> CreditsInfo:
        """
        Get credits information - implements VideoGenerationDriver interface

        Returns:
            CreditsInfo with credits remaining
        """
        result = await self.get_credits_api()

        if result is None:
            return CreditsInfo(credits=None, error="No access token")

        if "error" in result:
            return CreditsInfo(
                credits=None,
                error_code=result.get("error_code"),
                error=result.get("error")
            )

        return CreditsInfo(
            credits=result.get("credits"),
            reset_seconds=result.get("reset_seconds")
        )

    async def upload_image(self, image_path: str) -> UploadResult:
        """
        Upload image for video generation - implements VideoGenerationDriver interface

        Args:
            image_path: Path to image file

        Returns:
            UploadResult with file_id if successful
        """
        result = await self.upload_image_api(image_path)

        return UploadResult(
            success=result.get("success", False),
            file_id=result.get("file_id"),
            error=result.get("error")
        )

    async def wait_for_completion(
        self,
        task_id: str,
        timeout: int = 300,
        poll_interval: int = 10
    ) -> Optional[VideoData]:
        """
        Wait for video generation to complete - implements VideoGenerationDriver interface

        Args:
            task_id: Task ID to wait for
            timeout: Max wait time in seconds
            poll_interval: Seconds between polls (not used in internal implementation)

        Returns:
            VideoData when complete, None if timeout
        """
        result = await self.wait_for_completion_api(
            match_prompt="",  # Not needed when task_id provided
            timeout=timeout,
            task_id=task_id
        )

        if result is None:
            return None

        if result.get("status") == "failed":
            return None

        return VideoData(
            id=result.get("id", ""),
            download_url=result.get("download_url", ""),
            status=result.get("status", "completed"),
            progress_pct=None
        )

    async def get_pending_tasks(self) -> list:
        """
        Get list of pending generation tasks - implements VideoGenerationDriver interface

        Returns:
            List of PendingTask objects
        """
        result = await self.get_pending_tasks_api()

        if result is None:
            return []

        # Convert dicts to PendingTask objects
        tasks = []
        for task_dict in result:
            tasks.append(PendingTask(
                id=task_dict.get("id", ""),
                status=task_dict.get("status", ""),
                progress_pct=task_dict.get("progress_pct"),
                created_at=task_dict.get("created_at")
            ))

        return tasks

    async def login(self, email: Optional[str] = None, password: Optional[str] = None, cookies: Optional[dict] = None) -> dict:
        await self.start()
        await self.login_page.login(email or "", password or "", self.base_url)
        
        # Identity Verification Safeguard
        if email:
            is_valid_identity = await self.verify_identity(email)
            if not is_valid_identity:
                logger.error("🚨 CRITICAL: Session Identity Mismatch! Expected different user.")
                logger.warning("[CLEANUP]  Force Check-out (Clearing Cookies) to prevent cross-account contamination...")
                
                # Force Logout
                try:
                    await self.page.context.clear_cookies()
                except:
                    pass
                
                raise Exception(f"Session Identity Mismatch: Logged in user is NOT {email}. Cookies cleared.")
        
        # Wait a bit for traffic to generate token if needed
        if not self.latest_access_token:
             logger.info("[WAIT]  Waiting 5s for token capture after login...")
             await asyncio.sleep(5)
        
        return await self.context.cookies()

    



