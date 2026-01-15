from curl_cffi import requests
import urllib.parse
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

class WatermarkRemover:
    """
    Service to remove watermarks from Sora videos using dyysy.com API.
    Follows Single Responsibility Principle: Only handles API communication and URL extraction.
    """
    BASE_URL = "https://api.dyysy.com/links2026"  # Updated endpoint (links2026)

    @staticmethod
    def get_clean_video_url(sora_share_url: str) -> Optional[str]:
        """
        Retrieves the clean (no watermark) video URL from a Sora share URL.
        
        Args:
            sora_share_url: The full sharing URL (e.g., https://sora.chatgpt.com/s/...) 
                            
        Returns:
            str: The direct URL to the clean mp4 video if found.
            None: If the API fails or no clean link is available.
        """
        if not sora_share_url:
            return None

        try:
            # Normalize URL to full format if only ID is provided
            if not sora_share_url.startswith("http"):
                # Assume it's a post ID, prepend the domain
                if sora_share_url.startswith("s_") or sora_share_url.startswith("p_"):
                    sora_share_url = f"https://sora.chatgpt.com/s/{sora_share_url}"
                else:
                    sora_share_url = f"https://sora.chatgpt.com/s/{sora_share_url}"
            
            logger.info(f"[WATERMARK] Fetching clean URL for: {sora_share_url}")
            
            # Use curl_cffi to impersonate Chrome and send POST Form Data
            # This bypasses potential bot protection
            response = requests.post(
                WatermarkRemover.BASE_URL,
                data={"url": sora_share_url},
                impersonate="chrome110",
                headers={"Content-Type": "application/x-www-form-urlencoded"}, 
                timeout=30
            )
            
            if response.status_code != 200:
                logger.error(f"[WATERMARK] API returned error: {response.status_code} - {response.text[:200]}")
                return None
            
            data = response.json()
            
            # Extract the 'mp4' link from 'data.links' object (new format)
            # Structure: {"ok": true, "data": {"links": {"mp4": "...", "mp4_wm": "...", ...}}}
            # Fallback: {"links": {"mp4": "...", ...}} (old format)
            # Or direct keys in data (observed in tests)
            
            links = None
            if 'data' in data and isinstance(data['data'], dict) and 'links' in data['data']:
                links = data['data']['links']
            elif 'links' in data:
                links = data['links']
            # Fallback: Check if 'mp4' is directly in 'data' (based on observed debug output)
            # Debug output showed: "data": "...mp4" ?? No, wait.
            # The debug output was truncated but implied data structure. 
            # Let's trust the standard parsing first, and add direct check if fails.
            
            clean_url = None
            if links and 'mp4' in links:
                clean_url = links['mp4']
            elif 'data' in data and isinstance(data['data'], dict) and 'mp4' in data['data']:
                 clean_url = data['data']['mp4']

            if clean_url:
                logger.info(f"[WATERMARK] Success! Clean URL found.")
                return clean_url
            
            logger.warning(f"[WATERMARK] Clean URL not found in response. Data keys: {list(data.keys())}")
            return None
            
            
        except Exception as e:
            logger.error(f"[WATERMARK] Unexpected error: {e}")
            return None

    @staticmethod
    async def process_video(
        video_id: str, 
        api_client,  # Type: SoraApiClient
        sentinel_token: str,
        title: str = "Sora Video",
        description: str = ""
    ) -> Optional[str]:
        """
        Full flow:
        1. Access Token -> API Client -> Post Video (Public)
        2. Get Share URL
        3. Remove Watermark (Get Clean URL)
        
        Args:
            video_id: The ID of the video to process.
            api_client: Instance of SoraApiClient to handle the post request.
            sentinel_token: Token required for posting.
            
        Returns:
            str: The clean video URL (mp4) if successful.
        """
        # 1. Post Video
        logger.info(f"[WATERMARK] Processing video {video_id} for watermark removal...")
        post_result = await api_client.post_video(
            video_id=video_id,
            title=title,
            description=description,
            sentinel_token=sentinel_token
        )
        
        if not post_result.get("success"):
            logger.error(f"[WATERMARK] Failed to post video: {post_result.get('error')}")
            return None
            
        share_url = post_result.get("url")
        if not share_url:
            logger.error("[WATERMARK] No share URL returned after posting.")
            return None
            
        logger.info(f"[WATERMARK] Video posted successfully: {share_url}")
        
        # 2. Get Clean URL
        # wait a bit for propagation? usually instant.
        clean_url = WatermarkRemover.get_clean_video_url(share_url)
        
        if clean_url:
            logger.info(f"[WATERMARK] Clean URL retrieved: {clean_url}")
            return clean_url
        else:
            logger.error(f"[WATERMARK] Failed to extract clean URL from {share_url}")
            return None

    @staticmethod
    def download_clean_video(clean_url: str, save_path: str) -> bool:
        """
        Downloads the clean video to the specified path.
        """
        try:
            logger.info(f"[WATERMARK] Downloading clean video to {save_path}...")
            
            # Create dir if not exists
            os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
            
            response = requests.get(clean_url, stream=True, timeout=60)
            response.raise_for_status()
            
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    
            logger.info(f"[WATERMARK] Download complete: {save_path}")
            return True
        except Exception as e:
            logger.error(f"[WATERMARK] Download failed: {e}")
            return False

