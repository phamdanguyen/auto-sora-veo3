from curl_cffi import requests
import logging
import json
import urllib.parse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WM_DEBUG")

# User provided URL
SAMPLE_SORA_URL = "https://sora.chatgpt.com/p/s_6966d75360a08191be2e13a67aa24a71?psh=HXVzZXItblhJS2FLMklHVkZiQnJrYmpRT1B3T1pa.leqiScaFBCac"

BASE_URL = "https://api.dyysy.com/links2026"

def debug_dyysy():
    logger.info(f"Testing dyysy API with URL: {SAMPLE_SORA_URL} using curl_cffi")
    
    encoded_url = urllib.parse.quote(SAMPLE_SORA_URL, safe='')
    api_endpoint = f"{BASE_URL}/{encoded_url}"
    
    # Variant 5: POST Form Data
    print("\n--- TEST 5: POST Form Data ---")
    try:
        response = requests.post(
            BASE_URL, 
            data={"url": SAMPLE_SORA_URL}, 
            impersonate="chrome110",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30
        )
        print(f"Status: {response.status_code}")
        print(response.text[:500])
    except Exception as e: print(e)
    
    # Variant 1: Original (Path Param)
    print("\n--- TEST 1: Path Param ---")
    encoded_url = urllib.parse.quote(SAMPLE_SORA_URL, safe='')
    api_endpoint = f"{BASE_URL}/{encoded_url}"
    try:
        response = requests.get(api_endpoint, timeout=30)
        print(f"Status: {response.status_code}")
        print(response.text[:200])
    except Exception as e: print(e)

    # Variant 2: Query Param
    print("\n--- TEST 2: Query Param ---")
    api_endpoint_2 = f"{BASE_URL}?url={encoded_url}"
    try:
        response = requests.get(api_endpoint_2, timeout=30)
        print(f"Status: {response.status_code}")
        print(response.text[:200])
    except Exception as e: print(e)
    
    # Variant 3: POST request
    print("\n--- TEST 3: POST Request ---")
    try:
        response = requests.post(BASE_URL, data={"url": SAMPLE_SORA_URL}, timeout=30)
        print(f"Status: {response.status_code}")
        print(response.text[:200])
    except Exception as e: print(e)
    
    # Variant 4: Extract ID only
    print("\n--- TEST 4: ID Only ---")
    video_id = SAMPLE_SORA_URL.split("/")[-1]
    encoded_id = urllib.parse.quote(video_id, safe='')
    api_endpoint_4 = f"{BASE_URL}/{encoded_id}"
    try:
        response = requests.get(api_endpoint_4, timeout=30)
        print(f"Status: {response.status_code}")
        print(response.text[:200])
    except Exception as e: print(e)

if __name__ == "__main__":
    debug_dyysy()
