from typing import Optional, List
import logging
from app.core.drivers.abstractions import APIOnlyDriver, VideoResult, CreditsInfo, UploadResult, VideoData, PendingTask
from app.core.drivers.api_client import SoraApiClient

logger = logging.getLogger(__name__)

class SoraApiDriver(APIOnlyDriver):
    """
    Sora Driver implementation that uses ONLY the API.
    No browser automation, no Playwright dependency.
    
    Implements: VideoGenerationDriver
    """
    
    def __init__(self, access_token: str, device_id: str = None, user_agent: str = None, cookies: list = None, account_email: str = None):
        super().__init__(access_token=access_token, device_id=device_id, user_agent=user_agent)
        self.cookies = cookies or []
        self.account_email = account_email
        
        # Initialize API Client
        self.api_client = SoraApiClient(
            access_token=self.access_token,
            user_agent=self.user_agent,
            cookies=self.cookies,
            account_email=self.account_email,
            device_id=self.device_id
        )
        logger.info(f"🔌 SoraApiDriver initialized (Device ID: {self.device_id})")

    async def start(self) -> None:
        """No-op for API driver"""
        pass

    async def stop(self) -> None:
        """No-op for API driver"""
        pass

    async def generate_video(
        self,
        prompt: str,
        duration: int,
        aspect_ratio: str,
        image_path: Optional[str] = None
    ) -> VideoResult:
        """
        Generate video via API with retry logic for heavy_load errors
        """
        import asyncio
        import random
        import json

        # Map duration to n_frames
        duration_to_frames = {5: 150, 10: 300, 15: 450}
        n_frames = duration_to_frames.get(duration, 180)

        # Map aspect ratio to orientation
        if aspect_ratio == "16:9":
            orientation = "landscape"
        elif aspect_ratio == "9:16":
            orientation = "portrait"
        elif aspect_ratio == "1:1":
            orientation = "square"
        else:
            orientation = "landscape"  # Default fallback

        # Upload image if provided
        file_id = None
        if image_path:
            upload_result = await self.upload_image(image_path)
            if not upload_result.success:
                return VideoResult(success=False, error=upload_result.error)
            file_id = upload_result.file_id

        # Prepare Payload
        from app.core.sentinel import get_sentinel_token
        try:
            sentinel_payload = get_sentinel_token(flow="sora_create_task")
        except Exception as e:
            return VideoResult(success=False, error=f"Sentinel failed: {e}")

        # Build COMPLETE payload matching old implementation
        # CRITICAL: Sora API requires ALL fields, even if None
        payload = {
            "kind": "video",
            "prompt": prompt,
            "title": None,
            "orientation": orientation,
            "size": "small",  # BUG FIX: This was missing! Default: "small"
            "n_frames": n_frames,
            "inpaint_items": [],
            "remix_target_id": None,
            "metadata": None,
            "cameo_ids": None,
            "cameo_replacements": None,
            "model": "sy_8",
            "style_id": None,
            "audio_caption": None,
            "audio_transcript": None,
            "video_caption": None,
            "storyboard_id": None
        }

        if file_id:
            clean_id = file_id.split("#")[0] if "#" in file_id else file_id
            payload["inpaint_items"] = [{"kind": "file", "file_id": clean_id}]

        # Retry logic for heavy_load errors
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            logger.info(f"[API] Generate attempt {attempt}/{max_retries}")

            # Call API Client
            result = await self.api_client.generate_video(
                payload=payload,
                sentinel_token=sentinel_payload,
                device_id=self.device_id or ""
            )

            if result.get("success"):
                # Success!
                return VideoResult(
                    success=True,
                    task_id=result.get("task_id"),
                    error=None
                )

            # Failed - check error type
            error_str = str(result.get("error", ""))

            # Check if it's a heavy_load error
            is_heavy_load = False
            try:
                if isinstance(result.get("error"), str):
                    error_data = json.loads(error_str) if error_str.startswith("{") else {}
                    error_code = error_data.get("error", {}).get("code", "")
                    is_heavy_load = error_code == "heavy_load"
                elif isinstance(result.get("error"), dict):
                    error_code = result.get("error", {}).get("error", {}).get("code", "")
                    is_heavy_load = error_code == "heavy_load"
            except:
                is_heavy_load = "heavy_load" in error_str.lower()

            if is_heavy_load:
                if attempt < max_retries:
                    # Retry with delay
                    delay = random.randint(15, 30)
                    logger.warning(f"[API] Heavy load detected. Retry {attempt}/{max_retries} after {delay}s...")
                    await asyncio.sleep(delay)
                    continue
                else:
                    # Max retries reached for heavy_load
                    logger.error(f"[API] Max retries reached for heavy_load. Giving up.")
                    return VideoResult(success=False, error="Sora server under heavy load after 3 retries")

            # Non-heavy_load error: Use fallback verification
            logger.warning(f"[API] Generation failed ({error_str}). Verifying if task started anyway...")
            try:
                pending_tasks = await self.api_client.get_pending_tasks()
                for task in pending_tasks:
                     # Match prompt (first 50 chars to avoid truncation issues)
                     task_prompt = task.get("prompt", "")
                     if prompt[:50].strip() in task_prompt:
                         logger.info(f"[API] ✅ Verification SUCCESS! Found matching task {task.get('id')}")
                         return VideoResult(
                             success=True,
                             task_id=task.get("id"),
                             error=None
                         )
            except Exception as e:
                logger.warning(f"[API] Verification failed: {e}")

            # Non-heavy_load error without verification success
            return VideoResult(
                success=False,
                task_id=result.get("task_id"),
                error=error_str
            )

        # Should not reach here, but just in case
        return VideoResult(
            success=False,
            error="Unknown error after retries"
        )

    async def get_credits(self) -> CreditsInfo:
        """
        Get credits via API
        """
        # Generate sentinel if possible
        sentinel_token = ""
        try:
            from app.core.sentinel import get_sentinel_token
            import json
            token_data = get_sentinel_token(flow="sora_create_task")
            sentinel_token = json.dumps(json.loads(token_data) if isinstance(token_data, str) else token_data)
        except Exception:
            pass

        result = await self.api_client.get_credits_summary(
            device_id=self.device_id,
            sentinel_token=sentinel_token
        )

        if not result or "error" in result:
             return CreditsInfo(
                credits=None,
                error=result.get("error", "Unknown error"),
                error_code=result.get("error_code")
             )

        return CreditsInfo(
            credits=result.get("credits"),
            reset_seconds=result.get("reset_seconds")
        )

    async def upload_image(self, image_path: str) -> UploadResult:
        """Upload image via API"""
        result = await self.api_client.upload_image(image_path)
        return UploadResult(
            success=result.get("success", False),
            file_id=result.get("file_id"),
            error=result.get("error")
        )

    async def wait_for_completion(
        self,
        task_id: str,
        timeout: int = 600,
        poll_interval: int = 15,
        match_prompt: str = ""
    ) -> Optional[VideoData]:
        """
        Wait for completion via API polling (Robust Version).
        Ported from SoraBrowserDriver.wait_for_completion_api
        """
        if task_id:
            logger.info(f"[WAIT]  Waiting for video completion (API) - Task ID: {task_id}")
        else:
             # Fallback log if we ever support prompt-only waiting
            logger.info(f"[WAIT]  Waiting for video completion (API) - Prompt: '{match_prompt[:30]}...' (NO task_id)")

        import time
        import asyncio
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # 1. Check Pending
                pending = await self.api_client.get_pending_tasks()
                if pending:
                    # Check if our task is still pending
                    is_pending = False
                    for task in pending:
                        # PRIORITY 1: Match by task_id (exact match)
                        if task_id and task.get("id") == task_id:
                            progress = (task.get("progress_pct") or 0) * 100
                            logger.info(f"[STATS]  Task {task_id} still pending: {progress:.1f}% complete")
                            is_pending = True
                            break
                        
                        # FALLBACK: Match by prompt (fuzzy)
                        if not task_id and match_prompt:
                            task_prompt = task.get("prompt", "")
                            if match_prompt[:30].strip() in task_prompt or task_prompt[:30].strip() in match_prompt:
                                progress = (task.get("progress_pct") or 0) * 100
                                logger.info(f"[STATS]  Task still pending (prompt match): {progress:.1f}% complete")
                                is_pending = True
                                break
                
                    if is_pending:
                         await asyncio.sleep(poll_interval)
                         continue

                # 2. Check Drafts (Finished)
                # Use robust get_drafts from Client
                drafts = await self.api_client.get_drafts(limit=15)
                if drafts:
                    for draft in drafts:
                        # PRIORITY 1: Match by task_id
                        if task_id and draft.get("task_id") == task_id:
                            # Check for errors first (BUG FIX: Sora uses "kind" field for errors)
                            if draft.get("kind") == "sora_error" or draft.get("error_reason"):
                                error_msg = draft.get("error_reason") or "Unknown error"
                                logger.error(f"[ERROR] Video generation failed: {error_msg}")
                                # Return failed status - worker will mark job as failed
                                return VideoData(
                                    id=draft.get("id"),
                                    download_url="",
                                    status="failed"
                                )

                            # Check for download URL
                            download_url = draft.get("url") or draft.get("downloadable_url") or draft.get("video_url")
                            if download_url:
                                return VideoData(
                                    id=draft.get("id"),
                                    download_url=download_url,
                                    status="completed"
                                )
                            elif draft.get("status") == "failed":
                                return VideoData(id=draft.get("id"), download_url="", status="failed")
                        
                        # FALLBACK: Match by prompt
                        if not task_id and match_prompt:
                            draft_prompt = draft.get("prompt", "")
                            if match_prompt[:30].strip() in draft_prompt or draft_prompt[:30].strip() in match_prompt:
                                # Check for errors first (BUG FIX)
                                if draft.get("kind") == "sora_error" or draft.get("error_reason"):
                                    error_msg = draft.get("error_reason") or "Unknown error"
                                    logger.error(f"[ERROR] Video generation failed: {error_msg}")
                                    return VideoData(
                                        id=draft.get("id"),
                                        download_url="",
                                        status="failed"
                                    )

                                download_url = draft.get("url") or draft.get("downloadable_url") or draft.get("video_url")
                                if download_url:
                                     return VideoData(
                                        id=draft.get("id"),
                                        download_url=download_url,
                                        status="completed"
                                    )

            except Exception as e:
                logger.warning(f"[API] Poll error in wait_for_completion: {e}")
            
            elapsed = int(time.time() - start_time)
            # logger.info(f"[WAIT]  Polling... ({elapsed}s / {timeout}s)")
            await asyncio.sleep(poll_interval)
            
        return None

    async def get_pending_tasks(self) -> List[PendingTask]:
        """Get pending tasks via API"""
        raw_tasks = await self.api_client.get_pending_tasks()
        if not raw_tasks:
            return []
            
        tasks = []
        for t in raw_tasks:
            tasks.append(PendingTask(
                id=t.get("id", ""),
                status=t.get("status", "pending"),
                progress_pct=t.get("progress_pct"),
                created_at=t.get("created_at")
            ))
        return tasks
