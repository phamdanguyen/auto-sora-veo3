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
            "oai-language": "en-US"
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
            
            async with AsyncSession(impersonate="chrome120") as session:
                response = await session.post(
                    "https://sora.chatgpt.com/backend/project_y/file/upload",
                    headers=headers,
                    data=body,
                    cookies=self.cookie_dict,  # FIX: Pass cookies explicitly
                    timeout=60
                )

                if response.status_code == 200:
                    data = json.loads(response.text)
                    logger.info(f"{self.log_prefix} [OK] [API] Image uploaded: {data.get('file_id')}")
                    return {
                        "success": True,
                        "file_id": data.get('file_id'),
                        "url": data.get('url'),
                        "asset_pointer": data.get('asset_pointer')
                    }
                else:
                    logger.error(f"{self.log_prefix} [ERROR] [API] Upload failed ({response.status_code}): {response.text}")
                    return {"success": False, "error": f"Upload failed: {response.status_code} - {response.text}"}

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
        # BUG FIX: Don't overwrite Authorization - it's already properly formatted in self.headers (line 33)
        # headers['Authorization'] = self.access_token  # REMOVED - this was breaking auth
        headers['openai-sentinel-token'] = json.dumps(json.loads(sentinel_token) if isinstance(sentinel_token, str) else sentinel_token)
        headers['oai-device-id'] = device_id or ""
        headers['oai-language'] = 'en-US'

        logger.info(f"🔌 {self.log_prefix} [API] Generating video: {str(payload)[:100]}...")

        try:
            async with AsyncSession(impersonate="chrome120") as session:
                response = await session.post(
                    url,
                    headers=headers,
                    json=payload,
                    cookies=self.cookie_dict,  # FIX: Pass cookies explicitly
                    timeout=30
                )

                if response.status_code == 200:
                    logger.info(f"{self.log_prefix} [OK] [API] Generation started!")
                    try:
                        data = response.json()
                        task_id = data.get('id') or data.get('task_id')
                        return {"success": True, "task_id": task_id, "response": data}
                    except:
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
            async with AsyncSession(impersonate="chrome120") as session:
                response = await session.get(
                    url,
                    headers=self.headers,
                    params=params,
                    cookies=self.cookie_dict,  # FIX: Pass cookies explicitly
                    timeout=20
                )
                
                if response.status_code == 200:
                    data = response.json()
                    items = data.get("items", data) if isinstance(data, dict) else data
                    return items
                else:
                     logger.warning(f"[API] Get drafts failed: {response.status_code}")
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
            async with AsyncSession(impersonate="chrome120") as session:
                response = await session.get(
                    "https://sora.chatgpt.com/backend/nf/pending/v2",
                    headers=self.headers,
                    cookies=self.cookie_dict,  # FIX: Pass cookies explicitly
                    timeout=15
                )
                if response.status_code == 200:
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

    async def post_video(self, video_id: str, title: str, description: str, sentinel_token: str) -> Dict[str, Any]:
        """
        Publish/post a video to get public URL.
        """
        url = "https://sora.chatgpt.com/backend/project_y/post"
        
        payload = {
            "title": title or "Sora Video",
            "description": description or "",
            "visibility": "public"
        }
        if video_id:
            payload["video_id"] = video_id

        headers = self.headers.copy()
        headers['Content-Type'] = 'application/json'
        headers['openai-sentinel-token'] = json.dumps(json.loads(sentinel_token) if isinstance(sentinel_token, str) else sentinel_token)
        
        logger.info(f"📤 {self.log_prefix} [API] Posting video {video_id}...")

        try:
            async with AsyncSession(impersonate="chrome120") as session:
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
                    
                    post_id = data.get('id')
                    share_url = data.get('url')
                    
                    # Fallback: check inside 'post' object
                    if not post_id and 'post' in data:
                        post_id = data['post'].get('id')
                    if not share_url and 'post' in data:
                        share_url = data['post'].get('url')
                        
                    # If we have a post ID but no URL, construct it
                    if post_id and not share_url:
                        share_url = f"https://sora.chatgpt.com/s/{post_id}"
                        
                    logger.info(f"{self.log_prefix} [OK] [API] Video Published! ID: {post_id} | URL: {share_url}")
                    return {"success": True, "post_id": post_id, "url": share_url}


                else:
                    logger.error(f"{self.log_prefix} [ERROR] [API] Post failed ({response.status_code}): {response.text}")
                    return {"success": False, "error": f"{response.status_code} - {response.text}"}

        except Exception as e:
            logger.error(f"[ERROR] [API] Post exception: {e}")
            return {"success": False, "error": str(e)}



