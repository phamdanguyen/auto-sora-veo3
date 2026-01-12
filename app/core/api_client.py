from curl_cffi import requests
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class SoraApiClient:
    def __init__(self, access_token: str, user_agent: str, cookies: Optional[Dict] = None):
        self.access_token = access_token
        self.user_agent = user_agent
        self.cookies = cookies or {}
        
        # Base headers mimicking browser
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "User-Agent": user_agent,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://sora.chatgpt.com",
            # "Referer": "https://sora.chatgpt.com/", # Sometimes referer can trigger checks if not exact matches
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
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
            cookies=self.cookies,
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
        # No directID endpoint known yet, assume polling list
        return "unknown"
