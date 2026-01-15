from curl_cffi.requests import AsyncSession
import asyncio
import logging
import json
import os
import urllib3
import time
from curl_cffi import requests
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

class SoraApiClient:
    def __init__(self, access_token: str, user_agent: str, cookies: Optional[Dict] = None, account_email: str = None, device_id: str = None):
        self.access_token = access_token
        self.user_agent = user_agent
        self.cookies = cookies or {}
        self.account_email = account_email
        self.device_id = device_id
        
        # Log prefix
        self.log_prefix = f"[Account: {self.account_email}]" if self.account_email else "[Account: Unknown]"
        
        # Build cookie string and normalized dict
        self.cookie_dict = {}
        if isinstance(self.cookies, list):
             for c in self.cookies:
                 if isinstance(c, dict) and 'name' in c and 'value' in c:
                     self.cookie_dict[c['name']] = c['value']
        elif isinstance(self.cookies, dict):
             self.cookie_dict = self.cookies

        self.cookie_str = "; ".join([f"{k}={v}" for k, v in self.cookie_dict.items()])


        # Base headers mimicking browser
        self.headers = {
            "Authorization": f"Bearer {access_token}" if not access_token.startswith("Bearer") else access_token,
            "User-Agent": user_agent,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://sora.chatgpt.com",
            "Referer": "https://sora.chatgpt.com/",
            "Cookie": self.cookie_str,
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "oai-device-id": self.device_id or "",
            "oai-language": "en-US",
            "priority": "u=1, i"
        }

    def get_tasks(self, limit: int = 10) -> Dict[str, Any]:
        """
        Poll recent tasks (videos).
        Endpoint: https://sora.chatgpt.com/backend/project_y/feed
        OR drafts: https://sora.chatgpt.com/backend/project_y/profile/drafts
        """
        # Try Drafts first as it's our focus
        url = "https://sora.chatgpt.com/backend/project_y/profile/drafts"
        params = {
            "limit": limit,
        }
        
        # curl_cffi.requests.get mimics request.get but with 'impersonate'
        response = requests.get(
            url, 
            headers=self.headers, 
            cookies=self.cookie_dict,
            params=params,
            timeout=20,
            impersonate="chrome120" 
        )
        
        print(f"DEBUG Response: {response.status_code} | URL: {response.url}")
        # print(f"DEBUG Body: {response.text[:200]}") 

        if response.status_code == 200:
            return response.json()
        else:
             logger.error(f"API Error {response.status_code}: {response.text[:500]}")
             if response.status_code == 401:
                 raise Exception("Token Expired or Invalid")
             raise Exception(f"API Failed: {response.status_code}")

    def get_task_status(self, task_id: str) -> str:
        """
        Get status of a specific task. 
        """
    async def upload_image(self, image_path: str) -> Dict[str, Any]:
        """
        Upload image using curl_cffi to bypass CORS/Cloudflare.
        """
        if not os.path.exists(image_path):
            return {"success": False, "error": f"File not found: {image_path}"}

        filename = os.path.basename(image_path)
        ext = os.path.splitext(image_path)[1].lower()
        mime_type = "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/png"

        try:
            with open(image_path, 'rb') as f:
                file_content = f.read()

            # Manual Multipart Encoding
            fields = {
                'file': (filename, file_content, mime_type)
            }
            
            body, content_type = urllib3.encode_multipart_formdata(fields)
            
            # Copy headers and add Content-Type
            headers = self.headers.copy()
            headers["Content-Type"] = content_type
            # BUG FIX: Don't overwrite Authorization - it's already properly formatted in self.headers (line 33)
            # headers["Authorization"] = self.access_token  # REMOVED - this was breaking auth

            logger.info(f"🔌 {self.log_prefix} [API] Uploading image: {filename}...")
            
            # Use 'chrome' to match old code
            async with AsyncSession(impersonate="chrome") as session:
                response = await session.post(
                    "https://sora.chatgpt.com/backend/project_y/file/upload",
                    headers=headers,
                    data=body,
                    cookies=self.cookie_dict,  # FIX: Pass cookies explicitly
                    timeout=60
                )

                if response.status_code == 200:
                    data = json.loads(response.text)
                    
                    # Formatted Response Log
                    logger.info(f"====== 📥 UPLOAD IMAGE RESPONSE ======")
                    logger.info(json.dumps(data, indent=2))
                    logger.info("======================================")
                    
                    logger.info(f"{self.log_prefix} [OK] [API] Image uploaded: {data.get('file_id')}")
                    from app.core.drivers.abstractions import UploadResult
                    return UploadResult(
                        success=True,
                        file_id=data.get('file_id'),
                        error=None
                    )
                else:
                    logger.error(f"{self.log_prefix} [ERROR] [API] Upload failed ({response.status_code}): {response.text}")
                    from app.core.drivers.abstractions import UploadResult
                    return UploadResult(success=False, error=f"{response.status_code} - {response.text}")

        except Exception as e:
            logger.error(f"[ERROR] [API] Upload exception: {e}")
            return {"success": False, "error": str(e)}

    async def generate_video(self, payload: Dict[str, Any], sentinel_token: str, device_id: str) -> Dict[str, Any]:
        """
        Generate video via API.
        """
        url = "https://sora.chatgpt.com/backend/nf/create"
        
        headers = self.headers.copy()
        headers['Content-Type'] = 'application/json'
        
        # CRITICAL: Serialize sentinel token exactly like old code does
        # Old code: json.dumps(json.loads(sentinel_payload) if isinstance(sentinel_payload, str) else sentinel_payload)
        try:
            if isinstance(sentinel_token, str):
                # Parse and re-serialize to ensure proper JSON format
                parsed = json.loads(sentinel_token)
                headers['openai-sentinel-token'] = json.dumps(parsed)
            else:
                headers['openai-sentinel-token'] = json.dumps(sentinel_token)
        except Exception as e:
            logger.warning(f"{self.log_prefix} [WARNING] Sentinel token serialization failed: {e}")
            headers['openai-sentinel-token'] = sentinel_token
            
        headers['oai-device-id'] = device_id or ""
        headers['oai-language'] = 'en-US'

        # Formatted Payload Log
        logger.info(f"====== � GENERATE VIDEO PAYLOAD ======")
        logger.info(json.dumps(payload, indent=2))
        logger.info("==========================================")

        try:
            # Use 'chrome' impersonate to match old code exactly (not 'chrome120')
            async with AsyncSession(impersonate="chrome") as session:
                response = await session.post(
                    url,
                    headers=headers,
                    json=payload,
                    cookies=self.cookie_dict,  # FIX: Pass cookies explicitly
                    timeout=30
                )

                if response.status_code == 200:
                    try:
                        data = response.json()
                        # Formatted Response Log
                        logger.info(f"====== 📥 GENERATE VIDEO RESPONSE ======")
                        logger.info(json.dumps(data, indent=2))
                        logger.info("========================================")
                        
                        task_id = data.get('id') or data.get('task_id')
                        return {"success": True, "task_id": task_id, "response": data}
                    except:
                        logger.info(f"{self.log_prefix} [OK] [API] Generation started! Response: {response.text}")
                        return {"success": True, "response": response.text}
                else:
                    logger.error(f"{self.log_prefix} [ERROR] [API] Generate failed ({response.status_code}): {response.text}")
                    return {"success": False, "error": response.text}

        except Exception as e:
             logger.error(f"[ERROR] [API] Generate exception: {e}")
             return {"success": False, "error": str(e)}

    async def get_drafts(self, limit: int = 15) -> List[Dict]:
        """Get drafts list"""
        url = "https://sora.chatgpt.com/backend/project_y/profile/drafts"
        params = {"limit": limit}
        
        try:
            # Use 'chrome' to match old code
            async with AsyncSession(impersonate="chrome") as session:
                response = await session.get(
                    url,
                    headers=self.headers,
                    params=params,
                    cookies=self.cookie_dict,  # FIX: Pass cookies explicitly
                    timeout=20
                )
                
                if response.status_code == 200:
                    # Log full response for debugging
                    logger.info(f"[API] Get drafts success. Response: {response.text[:2000]}...") # Limit to avoid massive logs if too big
                    data = response.json()
                    items = data.get("items", data) if isinstance(data, dict) else data
                    return items
                else:
                     logger.warning(f"[API] Get drafts failed: {response.status_code} - {response.text}")
                     return []
        except Exception as e:
            logger.error(f"[API] Get drafts exception: {e}")
            return []

    async def get_pending_tasks(self) -> List[Dict]:
        """
        Get list of pending video generation tasks.
        Migrated from SoraDriver.get_pending_tasks_api
        """
        # Priority 1: curl_cffi
        try:
            # Use 'chrome' to match old code
            async with AsyncSession(impersonate="chrome") as session:
                response = await session.get(
                    "https://sora.chatgpt.com/backend/nf/pending/v2",
                    headers=self.headers,
                    cookies=self.cookie_dict,  # FIX: Pass cookies explicitly
                    timeout=15
                )
                if response.status_code == 200:
                    # Log full response for debugging
                    logger.info(f"{self.log_prefix} [API] get_pending_tasks response: {response.text}")
                    data = response.json()
                    task_list = data if isinstance(data, list) else []
                    logger.info(f"{self.log_prefix} [API] get_pending_tasks found {len(task_list)} tasks")
                    return task_list
                else:
                    logger.warning(f"{self.log_prefix} [API] get_pending_tasks failed: {response.status_code} - {response.text}")
        except Exception as e:
            logger.warning(f"[API] get_pending_tasks (curl) failed: {e}")
        
        return []


    async def get_credits_summary(self, device_id: str = None, sentinel_token: str = None) -> Dict[str, Any]:
        """
        Get credits info with full robustness (curl_cffi, fallbacks).
        Migrated from SoraDriver.get_credits_api
        """
        # 1. Try curl_cffi with browser fingerprint (Primary)
        try:
            # Prepare headers for curl
            curl_headers = self.headers.copy()
            if device_id:
                curl_headers["oai-device-id"] = device_id
            if sentinel_token:
                 curl_headers['openai-sentinel-token'] = json.dumps(json.loads(sentinel_token) if isinstance(sentinel_token, str) else sentinel_token)

            logger.info(f"{self.log_prefix} [API] check_credits: Using curl_cffi for Cloudflare bypass...")
            
            async with AsyncSession(impersonate="chrome120") as session:
                # Priority 1: /nf/check
                response = await session.get(
                    "https://sora.chatgpt.com/backend/nf/check",
                    headers=curl_headers,
                    cookies=self.cookie_dict,  # FIX: Pass cookies explicitly
                    timeout=30
                )
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        balance_info = data.get("rate_limit_and_credit_balance", {})
                        estimated_remaining = balance_info.get("estimated_num_videos_remaining")
                        purchased_remaining = balance_info.get("estimated_num_purchased_videos_remaining", 0)
                        reset_seconds = balance_info.get("access_resets_in_seconds")
                        
                        if estimated_remaining is not None:
                            total_credits = int(estimated_remaining) + int(purchased_remaining)
                            return {
                                "credits": total_credits, 
                                "source": "curl_nf_check", 
                                "reset_seconds": reset_seconds,
                                "raw": data
                            }
                    except:
                        pass
                
                # Priority 2: /billing/credit_balance
                response = await session.get(
                    "https://sora.chatgpt.com/backend/billing/credit_balance",
                    headers=curl_headers,
                    timeout=15
                )
                if response.status_code == 200:
                    data = response.json()
                    if "credits" in data:
                        return {"credits": int(data["credits"]), "source": "curl_billing"}

        except ImportError:
            logger.warning("[API] curl_cffi not installed, skipping robust check")
        except Exception as e:
            logger.error(f"[API] specific credit check failed: {e}")

        # 2. Fallback to simple endpoint (if any, otherwise return empty)
        return self._simple_get_credits()


    def _simple_get_credits(self) -> Optional[Dict]:
        """Original simple implementation as fallback"""
        url = "https://sora.chatgpt.com/backend/api/credits/summary"
        try:
            response = requests.get(
                url,
                headers=self.headers,
                impersonate="chrome120",
                timeout=15
            )
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
        return {"error": "All credit checks failed"}

    async def post_video(self, video_id: str, title: str, description: str, sentinel_token: str, generation_id: str = None) -> Dict[str, Any]:
        """
        Publish/post a video to get public URL.
        Uses new payload structure with attachments_to_create.
        """
        url = "https://sora.chatgpt.com/backend/project_y/post"
        
        # New Payload Structure
        # Note: post_text maps to description/title or prompt.
        payload = {
            "post_text": description or title or "Sora Video",
            "attachments_to_create": []
        }
        
        # Determine ID to use (generation_id preferred by API)
        target_gen_id = generation_id
        target_kind = "sora"
        
        # Heuristic: If video_id looks like generation_id (gen_) use it if generation_id missing
        if not target_gen_id and video_id and video_id.startswith("gen_"):
            target_gen_id = video_id
            
        # If we have a generation_id (or task_id treated as one?)
        if target_gen_id:
             payload["attachments_to_create"].append({
                "generation_id": target_gen_id,
                "kind": target_kind
             })
        elif video_id:
             # Fallback to task_id if no gen_id
             # Assuming 'task_id' field works or 'generation_id' accepts task IDs (unlikely but worth try as last resort)
             key = "task_id" if video_id.startswith("task_") else "generation_id"
             payload["attachments_to_create"].append({
                key: video_id,
                "kind": target_kind
             })

        headers = self.headers.copy()
        headers['Content-Type'] = 'application/json'
        headers['openai-sentinel-token'] = json.dumps(json.loads(sentinel_token) if isinstance(sentinel_token, str) else sentinel_token)
        
        logger.info(f"📤 {self.log_prefix} [API] Posting video {video_id} (GenID: {generation_id})...")

        try:
            async with AsyncSession(impersonate="chrome") as session:
                response = await session.post(
                    url,
                    headers=headers,
                    json=payload,
                    cookies=self.cookie_dict,
                    timeout=30
                )

                if response.status_code == 200:
                    data = response.json()
                    # Log full response for debugging
                    with open("post_response_debug.json", "w") as f:
                        json.dump(data, f, indent=2)
                    
                    # Extract post ID and share_ref - check both direct and nested locations
                    post_id = data.get('id')
                    share_ref = data.get('share_ref')
                    if not post_id and 'post' in data:
                        post_id = data['post'].get('id')
                        share_ref = data['post'].get('share_ref')
                    
                    # CRITICAL FIX: Construct proper URL for dyysy.com compatibility
                    # Format: https://sora.chatgpt.com/p/{post_id}?psh={share_ref}
                    # Note: post_id may or may not have 's_' prefix - add if missing
                    share_url = None
                    if post_id:
                        # Ensure post_id has correct format (force s_ prefix as required by external tools)
                        formatted_id = post_id if post_id.startswith('s_') else f"s_{post_id}"
                        
                        # Construct URL with share_ref param
                        share_url = f"https://sora.chatgpt.com/p/{formatted_id}"
                        if share_ref:
                            share_url += f"?psh={share_ref}"
                        
                    if not share_url or not post_id:
                        logger.error(f"{self.log_prefix} [ERROR] [API] Post succeeded but no post_id found in response")
                        return {"success": False, "error": "No post_id in response"}
                        
                    logger.info(f"{self.log_prefix} [OK] [API] Video Published! ID: {post_id} | URL: {share_url}")
                    return {"success": True, "post_id": post_id, "url": share_url, "share_ref": share_ref}


                else:
                    logger.error(f"{self.log_prefix} [ERROR] [API] Post failed ({response.status_code}): {response.text}")
                    return {"success": False, "error": f"{response.status_code} - {response.text}"}

        except Exception as e:
            logger.error(f"[ERROR] [API] Post exception: {e}")
            return {"success": False, "error": str(e)}

    async def verify_post_exists(self, post_id: str, video_id: str = None) -> bool:
        """
        Verify if a post actually exists in user's profile feed.
        Checks matching post_id OR matching video_id in attachments (task_id/generation_id).
        """
        try:
            async with AsyncSession(impersonate="chrome") as session:
                response = await session.get(
                    "https://sora.chatgpt.com/backend/project_y/profile_feed/me?limit=8&cut=nf2",
                    headers=self.headers,
                    cookies=self.cookie_dict,
                    timeout=15
                )
                
                if response.status_code == 200:
                    data = response.json()
                    items = data.get('items', [])
                    
                    target_post_id = post_id.replace("s_", "") if post_id else ""
                    
                    for item in items:
                        post = item.get('post', {})
                        
                        # 1. Match Post ID
                        current_post_id = post.get('id', "").replace("s_", "")
                        if target_post_id and current_post_id == target_post_id:
                            logger.info(f"{self.log_prefix} [OK] [VERIFY] Post {post_id} confirmed by Post ID!")
                            return True
                            
                        # 2. Match Video ID (Task/Gen ID) in Attachments
                        if video_id:
                            attachments = post.get('attachments', [])
                            for att in attachments:
                                if att.get('task_id') == video_id or att.get('generation_id') == video_id:
                                    logger.info(f"{self.log_prefix} [OK] [VERIFY] Post confirmed by Video ID match ({video_id}) inside Post {current_post_id}")
                                    return True
                    
                    logger.warning(f"{self.log_prefix} [WARNING] [VERIFY] Post/Video not found in feed.")
                    return False
                else:
                    logger.warning(f"{self.log_prefix} [VERIFY] Feed check failed: {response.status_code}")
                    return False
                    
        except Exception as e:
            logger.error(f"[VERIFY] Error checking feed: {e}")
            return False
