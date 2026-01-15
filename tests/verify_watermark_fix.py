import logging
import asyncio
import sys
import os

sys.path.append(os.getcwd())

from app.core.watermark_remover import WatermarkRemover

# Setup logging
logging.basicConfig(level=logging.INFO)

# User's Real URL
REAL_SORA_URL = "https://sora.chatgpt.com/p/s_6966d75360a08191be2e13a67aa24a71?psh=HXVzZXItblhJS2FLMklHVkZiQnJrYmpRT1B3T1pa.leqiScaFBCac"

def test_watermark_remover():
    print(f"Testing WatermarkRemover with URL: {REAL_SORA_URL}")
    
    clean_url = WatermarkRemover.get_clean_video_url(REAL_SORA_URL)
    
    if clean_url:
        print(f"\n[SUCCESS] Clean URL Retrieved: {clean_url}")
        print("Now testing download...")
        success = WatermarkRemover.download_clean_video(clean_url, "data/downloads/verify_clean.mp4")
        if success:
             print("[SUCCESS] Video downloaded to data/downloads/verify_clean.mp4")
        else:
             print("[FAILED] Download error")
    else:
        print("\n[FAILED] Could not get clean URL")

if __name__ == "__main__":
    test_watermark_remover()
