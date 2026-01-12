# Third-Party Watermark Removal Services
# Integrations for removing Sora watermarks from videos

import aiohttp
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class WatermarkRemover:
    """
    Module for removing watermarks from Sora videos using third-party services.
    
    Supported services:
    1. Kie.ai - API-based (requires API key, free credits available)
    2. Ezremove.ai - Web-based (free, no signup)
    3. Unwatermark.ai - Web-based (free, no signup)
    """
    
    def __init__(self, kie_api_key: str = None):
        """
        Initialize watermark remover.
        
        Args:
            kie_api_key: API key for Kie.ai (optional, get from https://kie.ai)
        """
        self.kie_api_key = kie_api_key
        self.kie_base_url = "https://api.kie.ai/api/v1"
        
    async def remove_watermark_kieai(self, video_url: str) -> dict:
        """
        Remove watermark using Kie.ai API.
        
        Args:
            video_url: Public URL to the Sora video
            
        Returns:
            dict with 'success', 'task_id', 'result_url', 'error' keys
        """
        if not self.kie_api_key:
            return {"success": False, "error": "Kie.ai API key not configured"}
        
        logger.info(f"🔧 Removing watermark via Kie.ai: {video_url[:50]}...")
        
        endpoint = f"{self.kie_base_url}/jobs/createTask"
        
        payload = {
            "model": "sora-watermark-remover",
            "input": {
                "video_url": video_url
            }
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.kie_api_key}"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                # Create task
                async with session.post(endpoint, json=payload, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        return {"success": False, "error": f"API error {response.status}: {error_text}"}
                    
                    result = await response.json()
                    task_id = result.get("task_id") or result.get("id")
                    
                    if not task_id:
                        return {"success": False, "error": "No task_id in response"}
                    
                    logger.info(f"   Task created: {task_id}")
                    
                    # Poll for completion
                    poll_endpoint = f"{self.kie_base_url}/jobs/getTask?task_id={task_id}"
                    
                    for _ in range(60):  # Max 5 minutes
                        await asyncio.sleep(5)
                        
                        async with session.get(poll_endpoint, headers=headers) as poll_response:
                            if poll_response.status == 200:
                                poll_result = await poll_response.json()
                                status = poll_result.get("status")
                                
                                if status == "completed":
                                    output = poll_result.get("output", {})
                                    result_url = output.get("video_url") or output.get("url")
                                    logger.info(f"   ✅ Watermark removed!")
                                    return {
                                        "success": True,
                                        "task_id": task_id,
                                        "result_url": result_url,
                                        "output": output
                                    }
                                elif status == "failed":
                                    return {"success": False, "error": poll_result.get("error", "Task failed")}
                                else:
                                    logger.debug(f"   Status: {status}")
                    
                    return {"success": False, "error": "Timeout waiting for watermark removal"}
                    
        except Exception as e:
            logger.error(f"❌ Kie.ai error: {e}")
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def get_free_services() -> list:
        """
        Get list of free watermark removal services (no API needed).
        
        Returns:
            List of service info dicts
        """
        return [
            {
                "name": "Ezremove.ai",
                "url": "https://ezremove.ai/free-sora-watermark-remover",
                "type": "web",
                "signup_required": False,
                "notes": "Free, instant, uses AI inpainting"
            },
            {
                "name": "Unwatermark.ai",
                "url": "https://unwatermark.ai/sora-watermark-remover",
                "type": "web",
                "signup_required": False,
                "notes": "Free, one-click, no registration"
            },
            {
                "name": "topYappers",
                "url": "https://topyappers.com/sora-watermark-remover",
                "type": "web",
                "signup_required": False,
                "notes": "Free AI-powered removal"
            },
            {
                "name": "ReelMoney",
                "url": "https://reel.money",
                "type": "web",
                "signup_required": False,
                "notes": "Free, processes in 3-10 minutes"
            },
            {
                "name": "Kie.ai",
                "url": "https://kie.ai",
                "type": "api",
                "signup_required": True,
                "notes": "API access with free credits for testing"
            }
        ]


async def download_video_without_watermark(
    video_url: str,
    output_path: str,
    kie_api_key: str = None
) -> dict:
    """
    Convenience function to download a Sora video without watermark.
    
    Args:
        video_url: Public URL to the Sora video
        output_path: Path to save the watermark-free video
        kie_api_key: Optional Kie.ai API key
        
    Returns:
        dict with 'success', 'output_path', 'error' keys
    """
    import aiohttp
    import os
    
    remover = WatermarkRemover(kie_api_key=kie_api_key)
    
    if kie_api_key:
        # Use API
        result = await remover.remove_watermark_kieai(video_url)
        if result["success"]:
            download_url = result["result_url"]
        else:
            return result
    else:
        # Without API, just return the services info
        return {
            "success": False,
            "error": "No API key provided. Use free web services instead.",
            "free_services": remover.get_free_services()
        }
    
    # Download the watermark-free video
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(download_url) as response:
                if response.status == 200:
                    os.makedirs(os.path.dirname(output_path), exist_ok=True)
                    with open(output_path, "wb") as f:
                        f.write(await response.read())
                    return {"success": True, "output_path": output_path}
                else:
                    return {"success": False, "error": f"Download failed: {response.status}"}
    except Exception as e:
        return {"success": False, "error": str(e)}
