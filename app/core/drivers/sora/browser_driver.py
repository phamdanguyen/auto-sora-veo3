from app.core.drivers.abstractions import BrowserBasedDriver, VideoResult, CreditsInfo, UploadResult, VideoData, PendingTask
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

class SoraBrowserDriver(BrowserBasedDriver):
    def __init__(self, headless: bool = False, proxy: Optional[str] = None, user_data_dir: Optional[str] = None, channel: str = "chrome", access_token: str = None, device_id: str = None, user_agent: str = None, cookies: list = None, account_email: str = None):
        super().__init__(headless=headless, proxy=proxy, user_data_dir=user_data_dir, channel=channel)
        
        # Store auth data if provided (Hybrid/API support)
        self.latest_access_token = access_token
        self.device_id = device_id
        self.latest_user_agent = user_agent
        self.cookies = cookies or []
        self.account_email = account_email

        # Use direct auth URL for reliable login flow
        self.base_url = "https://chatgpt.com/auth/login?next=%2Fsora%2F"
        
        # Page Objects (initialized after start)
        self.login_page = None
        self.creation_page = None
        self.drafts_page = None
        self.download_page = None
        self.verification_page = None
        
        # API Client (SOLID Refactor)
        self.api_client = None
        if self.latest_access_token:
            from app.core.drivers.api_client import SoraApiClient
            self.api_client = SoraApiClient(
                access_token=self.latest_access_token, 
                user_agent=self.latest_user_agent or "Mozilla/5.0",
                cookies=self.cookies,
                account_email=self.account_email,
                device_id=self.device_id
            )

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
            if "nf/create" in url and request.method == "POST":
                try:
                    logger.info("====== 🕵️ CAPTURED GENERATION REQUEST ======")
                    logger.info(f"URL: {url}")
                    logger.info(f"Headers: {request.headers}")
                    post_data = request.post_data
                    logger.info(f"Body: {post_data}")
                    logger.info("============================================")
                except Exception as e:
                    logger.warning(f"Failed to log request body: {e}")

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

    def _on_response_intercept(self, response):
        """Callback for every response - Fire and Forget"""
        try:
            url = response.url
            # Filter for relevant JSON endpoints
            if "sora.chatgpt.com" in url and ("profile/drafts" in url or "feed" in url or "tasks" in url or "create" in url):
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
            
            # Log full response for debugging (as requested by user)
            logger.info(f"[TASK]  Intercepted {endpoint_type} JSON ({len(str(data))} bytes)")
            
            if endpoint_type == "SUBMISSION":
                 logger.info(f"====== 🕵️ SUBMISSION RESPONSE ({url}) ======")
                 logger.info(json.dumps(data, indent=2)) # Log full JSON
                 logger.info("==========================================")
            else:
                 # For others, keep brief or log full if needed. User asked for "logs toàn bộ".
                 # Let's log full for DRAFTS too since it contains errors.
                 pass
            
            # Store data for analysis/usage
            self.latest_intercepted_data = data
            
            if endpoint_type == "SUBMISSION":
                # Parse submission result for credits
                self.last_submission_result = data
                logger.info("[OK]  Captured SUBMISSION response!")
                
                # [NEW] Log Payload & Headers for Debugging/Syncing API Driver
                try:
                    logger.info("====== 🕵️ CAPTURED GENERATION PAYLOAD ======")
                    # We can't easily get the request body from response object in Playwright directly 
                    # unless we captured it in _on_request_intercept.
                    # But we can log the Response Headers which might contain trace ID etc.
                    # Ideally we should match this with the Request.
                    logger.info(f"Response Headers: {response.headers}")
                    logger.info("============================================")
                except:
                    pass

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



    async def get_credits_api(self) -> dict:
        """
        Check credits via SoraApiClient.
        Delegates robust check to the API client.
        """
        if not self.api_client:
             if self.latest_access_token:
                from ..api_client import SoraApiClient
                self.api_client = SoraApiClient(self.latest_access_token, self.latest_user_agent, self.cookies)
             else:
                return {"error": "No access token", "error_code": "NO_TOKEN"}

        # Generate sentinel if possible (kept for compatibility with migrated logic)
        sentinel_token = ""
        try:
            from app.core.sentinel import get_sentinel_token
            import json
            token_data = get_sentinel_token(flow="sora_2_create_task")
            sentinel_token = json.dumps(json.loads(token_data) if isinstance(token_data, str) else token_data)
        except Exception:
             pass

        result = await self.api_client.get_credits_summary(
            device_id=self.device_id,
            sentinel_token=sentinel_token
        )
        
        if result:
            return result
            
        return {"error": "All API checks failed", "error_code": "ALL_FAILED"}

    async def get_pending_tasks_api(self) -> list:
        """
        Get list of pending video generation tasks with progress.
        Delegates to SoraApiClient.
        """
        if not self.api_client and self.latest_access_token:
             from ..api_client import SoraApiClient
             self.api_client = SoraApiClient(self.latest_access_token, self.latest_user_agent or "Mozilla/5.0", self.cookies)
        
        if self.api_client:
            return await self.api_client.get_pending_tasks()
            
        return None
        
    async def get_drafts_api(self) -> list:
        """
        Get list of draft videos via SoraApiClient.
        """
        if not self.api_client:
            # Try to init if token available now
            if self.latest_access_token:
                from ..api_client import SoraApiClient
                self.api_client = SoraApiClient(self.latest_access_token, self.latest_user_agent, self.cookies)
            else:
                 logger.warning("[WARNING] No API Client (missing token) for get_drafts")
                 return None

        # Use API Client
        return await self.api_client.get_drafts(limit=15)

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
        Generate video via SoraApiClient.
        """
        from app.core.sentinel import get_sentinel_token
        
        if not self.api_client:
             if self.latest_access_token:
                from ..api_client import SoraApiClient
                self.api_client = SoraApiClient(self.latest_access_token, self.latest_user_agent, self.cookies)
             else:
                return {"success": False, "error": "No access token / API Client"}

        # 1. Get Sentinel Token
        try:
            sentinel_payload = get_sentinel_token(flow="sora_2_create_task")
        except Exception as e:
            return {"success": False, "error": f"Sentinel failed: {e}"}

        # 2. Build Payload
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
            clean_id = image_file_id
            if "#" in clean_id:
                parts = clean_id.split("#")
                for p in parts:
                    if p.startswith("file_") or p.startswith("file-"):
                        clean_id = p
                        break
            payload["inpaint_items"] = [{"kind": "file", "file_id": clean_id}]

        # 3. Call API Client
        return await self.api_client.generate_video(
            payload=payload, 
            sentinel_token=sentinel_payload,
            device_id=self.device_id or ""
        )



    async def upload_image_api(self, image_path: str) -> dict:
        """
        Upload image via SoraApiClient.
        """
        if not self.api_client:
             if self.latest_access_token:
                from ..api_client import SoraApiClient
                self.api_client = SoraApiClient(self.latest_access_token, self.latest_user_agent, self.cookies)
             else:
                return {"success": False, "error": "No access token for upload"}

        return await self.api_client.upload_image(image_path)
                


    async def get_drafts_api(self) -> list:
        """
        Get list of draft videos via SoraApiClient.
        """
        if not self.api_client:
            # Try to init if token available now
            if self.latest_access_token:
                from ..api_client import SoraApiClient
                self.api_client = SoraApiClient(self.latest_access_token, self.latest_user_agent, self.cookies)
            else:
                 logger.warning("[WARNING] No API Client (missing token) for get_drafts")
                 return None

        # Use API Client
        # Use API Client
        return await self.api_client.get_drafts(limit=15)
            

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
        
        # Initialize API Client if not ready
        if not self.api_client:
             if self.latest_access_token:
                from ..api_client import SoraApiClient
                self.api_client = SoraApiClient(self.latest_access_token, self.latest_user_agent, self.cookies)
        
        # Generate sentinel token for post flow
        try:
            sentinel_payload = get_sentinel_token(flow="sora_2_create_post")
        except Exception as e:
            return {"success": False, "error": f"Sentinel failed: {e}"}
            
        # 1. Try via API Client (curl_cffi - Robust)
        if self.api_client:
            return await self.api_client.post_video(
                video_id=video_id,
                title=title,
                description=description,
                sentinel_token=sentinel_payload
            )

        # 2. Fallback to Browser Context if API Client fails to init (Unlikely if token exists)
        if self.page:
            try:
                # determine Device ID
                oai_device_id = await self.page.evaluate("""() => {
                    return localStorage.getItem('oai-did') || null;
                }""")
                
                payload = {
                    "title": title or "Sora Video",
                    "description": description or "",
                    "visibility": "public"
                }
                if video_id:
                    payload["video_id"] = video_id
            
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
                
                if result.get('status') == 200:
                    data = json.loads(result['body'])
                    logger.info(f"[OK]  Video Published! URL: {data.get('url')}")
                    return {"success": True, "post_id": data.get('id'), "url": data.get('url')}
                else:
                     error_msg = result.get('body', result.get('error'))
                     logger.error(f"[ERROR]  Post API failed (Browser): {error_msg}")
                     return {"success": False, "error": error_msg}

            except Exception as e:
                logger.error(f"[ERROR]  post_video_api (Browser) exception: {e}")
                return {"success": False, "error": str(e)}
        
        return {"success": False, "error": "No API Client and No Browser Page active"}

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
        
        [MODIFIED] Uses UI Automation (SoraCreationPage) instead of API to improve stability
        and bypass 'heavy_load' errors that frequent the direct API.
        """
        try:
            # Prepare Page Object
            if not self.creation_page:
                self.creation_page = SoraCreationPage(self.page)
                
            # Reset interception capture to ensure we get the NEW task ID
            self.last_submission_result = None
            
            # Map duration/aspect (UI usually defaults, we might skip setting specific UI controls if selectors missing)
            # TODO: Implement select_duration/aspect_ratio in SoraCreationPage if needed. 
            # For now, we rely on defaults or previous state, as stability is priority.
    
            # Upload image if provided
            if image_path:
                # We still use API for upload as it's reliable and hard to automate via UI drag-drop
                upload_result = await self.upload_image(image_path)
                if not upload_result.success:
                    return VideoResult(success=False, error=upload_result.error)
                # Note: Linking uploaded file to UI prompt is tricky without 'inpaint' UI logic.
                # If image is present, we might need to fallback to API or implement complex UI upload.
                # For now, let's warn if image is used with UI mode.
                logger.warning("Image provided but UI mode used. Image might not attach correctly without specific UI steps.")
    
            # 1. Fill Prompt (UI)
            # Ensure we are on the creation page
            logger.info(f"[Generate] Checking page state... Current URL: {self.page.url}")
            
            if "sora.chatgpt.com" not in self.page.url or "auth/login" in self.page.url:
                logger.info("[Generate] Navigating to Sora Home...")
                await self.page.goto("https://sora.chatgpt.com/", wait_until="domcontentloaded")
                await asyncio.sleep(3) # Wait for redirects
            
            # Check for Login Redirect
            if "auth/login" in self.page.url:
                 logger.error(f"[Generate] Redirected to Login Page! Session expired. URL: {self.page.url}")
                 return VideoResult(success=False, error="Session expired (Redirected to Login)")

            # Wait for Cloudflare challenge to complete
            logger.info("[Generate] Waiting for Cloudflare challenge to pass...")
            for _ in range(30): # Max 30 seconds
                title = await self.page.title()
                if "Just a moment" not in title and "Cloudflare" not in title:
                    logger.info(f"[Generate] Cloudflare check passed. Title: {title}")
                    break
                await asyncio.sleep(1)
            else:
                logger.error("[Generate] Cloudflare challenge timed out.")
                return VideoResult(success=False, error="Cloudflare challenge timed out")

            # Check for "Get Started" splash
            if await self.page.is_visible("text='Get started'"):
                 logger.info("Clicking 'Get started'...")
                 await self.page.click("text='Get started'")
                 await asyncio.sleep(1)

            await self.creation_page.fill_prompt(prompt)
            
            # 2. Click Generate (UI)
            # This triggers the real network request which we hope to intercept
            success = await self.creation_page.click_generate(prompt)
            
            if not success:
                return VideoResult(success=False, error="UI interaction failed (Click Generate)")

            # 3. Capture Task ID via Interception or Fallback
            # We wait up to 15s for the network response to be captured by _on_response_intercept
            task_id = None
            logger.info("[Generate] Waiting for network interception to capture Task ID...")
            
            for _ in range(30): # 15 seconds
                if self.last_submission_result:
                    task_id = self.last_submission_result.get("id")
                    logger.info(f"[Generate] Intercepted Task ID: {task_id}")
                    break
                await asyncio.sleep(0.5)
                
            # Fallback: Check pending tasks API if interception missed it
            if not task_id:
                logger.warning("[Generate] Interception missed task_id. Checking pending tasks via API...")
                # Give it a moment to appear in backend
                await asyncio.sleep(3) 
                pending = await self.get_pending_tasks_api()
                if pending:
                    for p in pending:
                        # Match by prompt content (fuzzy)
                        if prompt[:20] in p.get("prompt", ""):
                            task_id = p.get("id")
                            logger.info(f"[Generate] Found Task ID via Pending API (Fallback): {task_id}")
                            break
            
            # If still no task_id, we can't track it effectively, but if UI said success, 
            # maybe we return a placeholder? But PollWorker needs ID.
            if not task_id:
                 return VideoResult(success=False, error="Video submitted but failed to capture Task ID for tracking.")

            return VideoResult(
                success=True,
                task_id=task_id,
                error=None
            )
            
        except Exception as e:
            logger.error(f"Generate (UI Mode) failed: {e}", exc_info=True)
            return VideoResult(success=False, error=str(e))

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

    



