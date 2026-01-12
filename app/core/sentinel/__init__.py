# Sentinel Token Generator Module
# Adapted from github.com/leetanshaj/openai-sentinel for internal use

import hashlib
import json
import random
import time
import uuid
import pybase64
import requests
from datetime import datetime, timedelta, timezone


# Configuration Data
CORES = [8, 16, 24, 32]
CACHED_SCRIPTS = ["https://cdn.oaistatic.com/_next/static/cXh69klOLzS0Gy2joLDRS/_ssgManifest.js?dpl=453ebaec0d44c2decab71692e1bfe39be35a24b3"]
CACHED_DPL = ["prod-f501fe933b3edf57aea882da888e1a544df99840"]

NAVIGATOR_KEYS = [
    "registerProtocolHandler−function registerProtocolHandler() { [native code] }",
    "storage−[object StorageManager]",
    "locks−[object LockManager]",
    "appCodeName−Mozilla",
    "permissions−[object Permissions]",
    "webdriver−false",
    "vendor−Google Inc.",
    "mediaDevices−[object MediaDevices]",
    "cookieEnabled−true",
    "product−Gecko",
    "xr−[object XRSystem]",
    "clipboard−[object Clipboard]",
    "productSub−20030107",
    "hardwareConcurrency−32",
    "pdfViewerEnabled−true",
    "geolocation−[object Geolocation]",
    "onLine−true",
]

DOCUMENT_KEYS = ['_reactListeningo743lnnpvdg', 'location']

WINDOW_KEYS = [
    "0", "window", "self", "document", "name", "location",
    "customElements", "history", "navigation", "closed", "frames",
    "navigator", "origin", "screen", "innerWidth", "innerHeight",
    "performance", "crypto", "indexedDB", "localStorage", "sessionStorage",
    "fetch", "clearTimeout", "setTimeout", "alert", "confirm", "close",
]

MAX_ITERATION = 500000


def _get_parse_time():
    """Get formatted time in Eastern timezone."""
    now = datetime.now(timezone(timedelta(hours=-5)))
    return now.strftime("%a %b %d %Y %H:%M:%S") + " GMT-0500 (Eastern Standard Time)"


def _get_config(user_agent: str) -> list:
    """Generate browser configuration for PoW."""
    config = [
        random.choice([1920 + 1080, 2560 + 1440, 1920 + 1200, 2560 + 1600]),
        _get_parse_time(),
        4294705152,
        0,
        user_agent,
        random.choice(CACHED_SCRIPTS) if CACHED_SCRIPTS else "",
        CACHED_DPL,
        "en-US",
        "en-US,es-US,en,es",
        0,
        random.choice(NAVIGATOR_KEYS),
        random.choice(DOCUMENT_KEYS),
        random.choice(WINDOW_KEYS),
        time.perf_counter() * 1000,
        str(uuid.uuid4()),
        "",
        random.choice(CORES),
        time.time() * 1000 - (time.perf_counter() * 1000),
    ]
    return config


def _generate_answer(seed: str, diff: str, config: list) -> tuple:
    """Generate PoW solution by brute-force hashing."""
    diff_len = len(diff) // 2  # hex string, 2 chars per byte
    seed_encoded = seed.encode()
    
    static_config_part1 = (json.dumps(config[:3], separators=(',', ':'), ensure_ascii=False)[:-1] + ',').encode()
    static_config_part2 = (',' + json.dumps(config[4:9], separators=(',', ':'), ensure_ascii=False)[1:-1] + ',').encode()
    static_config_part3 = (',' + json.dumps(config[10:], separators=(',', ':'), ensure_ascii=False)[1:]).encode()
    
    target_diff = bytes.fromhex(diff)
    
    for i in range(MAX_ITERATION):
        dynamic_json_i = str(i).encode()
        dynamic_json_j = str(i >> 1).encode()
        final_json_bytes = static_config_part1 + dynamic_json_i + static_config_part2 + dynamic_json_j + static_config_part3
        base_encode = pybase64.b64encode(final_json_bytes)
        hash_value = hashlib.sha3_512(seed_encoded + base_encode).digest()
        
        if hash_value[:diff_len] <= target_diff:
            return base_encode.decode(), True
    
    return "wQ8Lk5FbGpA2NcR9dShT6gYjU7VxZ4D" + pybase64.b64encode(f'"{seed}"'.encode()).decode(), False


def get_pow_token(user_agent: str = None) -> str:
    """
    Generate a Proof of Work token.
    
    Args:
        user_agent: Browser user agent string (optional)
        
    Returns:
        PoW token string starting with 'gAAAAAC'
    """
    if not user_agent:
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
    
    config = _get_config(user_agent)
    seed = format(random.random())
    diff = "0fffff"
    solution, _ = _generate_answer(seed, diff, config)
    return 'gAAAAAC' + solution


def get_sentinel_token(flow: str = "sora_create_task") -> str:
    """
    Generate a complete Sentinel token for API authentication.
    
    Args:
        flow: The flow type (e.g., 'sora_create_task', 'sora_2_create_post')
        
    Returns:
        JSON string containing sentinel payload with p, t, c, id, flow fields
    """
    pow_token = get_pow_token()
    
    # Call sentinel/req API to get turnstile and token
    try:
        payload = {
            'p': pow_token,
            'id': str(uuid.uuid4()),
            'flow': flow
        }
        
        response = requests.post(
            url="https://chatgpt.com/backend-api/sentinel/req",
            data=json.dumps(payload),
            headers={'Content-Type': 'text/plain;charset=UTF-8'},
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            
            # Construct final sentinel token payload
            final_payload = {
                'p': pow_token,
                't': result.get("turnstile", {}).get('dx', ""),
                'c': result.get('token', ''),
                'id': str(uuid.uuid4()),
                'flow': flow
            }
            return json.dumps(final_payload)
        else:
            # Return basic payload on failure
            return json.dumps({
                'p': pow_token,
                'e': f'API error: {response.status_code}',
                'id': str(uuid.uuid4()),
                'flow': flow
            })
            
    except Exception as e:
        return json.dumps({
            'p': pow_token,
            'e': str(e),
            'id': str(uuid.uuid4()),
            'flow': flow
        })
