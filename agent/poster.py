import os
import time
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from .config import BASE_DIR, INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_ACCOUNT_ID

POSTER_JS_PATH = BASE_DIR / "agent" / "poster.mjs"

# Token-bucket rate limit state (in-memory)
LAST_PUBLISH_TIME = 0
MIN_SPACING_SECONDS = 300 # 5 minutes minimum between routine posts

def is_credentials_ready() -> bool:
    """Checks if valid non-placeholder Meta credentials exist."""
    return bool(
        INSTAGRAM_ACCESS_TOKEN and 
        INSTAGRAM_ACCOUNT_ID and 
        not INSTAGRAM_ACCESS_TOKEN.startswith("your_") and
        not INSTAGRAM_ACCOUNT_ID.startswith("your_")
    )

def check_rate_limit_and_throttle(is_emergency: bool = False):
    """Enforces rate-limit guardrails to protect the Instagram account from shadowbans."""
    global LAST_PUBLISH_TIME
    if is_emergency:
        # Tier 1 Breaking News bypasses routine wait
        LAST_PUBLISH_TIME = time.time()
        return

    now = time.time()
    elapsed = now - LAST_PUBLISH_TIME
    if elapsed < MIN_SPACING_SECONDS:
        wait_needed = int(MIN_SPACING_SECONDS - elapsed)
        print(f"  [Rate Limiter] Spacing posts to protect account. Sleeping {wait_needed}s...")
        time.sleep(wait_needed)

    LAST_PUBLISH_TIME = time.time()

def publish_to_instagram(image_url: str, caption: str, is_emergency: bool = False) -> str:
    """Publishes a single image card."""
    if not is_credentials_ready():
        print("  [Poster] Meta credentials not set or placeholder. Operating in DRY RUN mode.")
        return f"mock_ig_media_{int(time.time())}"

    check_rate_limit_and_throttle(is_emergency=is_emergency)

    env = os.environ.copy()
    env["INSTAGRAM_ACCESS_TOKEN"] = INSTAGRAM_ACCESS_TOKEN
    env["INSTAGRAM_ACCOUNT_ID"] = INSTAGRAM_ACCOUNT_ID

    cmd = ["node", str(POSTER_JS_PATH), image_url, caption]
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)

    if result.returncode != 0:
        error_msg = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Instagram publishing error: {error_msg}")

    data = json.loads(result.stdout.strip())
    if data.get("success"):
        return data["media_id"]
    raise RuntimeError(f"Publish failed: {data}")

def publish_carousel_to_instagram(image_urls: List[str], caption: str, is_emergency: bool = False) -> str:
    """Publishes a multi-slide carousel."""
    if not is_credentials_ready():
        print("  [Poster] Meta credentials not set or placeholder. Operating in DRY RUN mode.")
        return f"mock_carousel_media_{int(time.time())}"

    check_rate_limit_and_throttle(is_emergency=is_emergency)

    env = os.environ.copy()
    env["INSTAGRAM_ACCESS_TOKEN"] = INSTAGRAM_ACCESS_TOKEN
    env["INSTAGRAM_ACCOUNT_ID"] = INSTAGRAM_ACCOUNT_ID

    cmd = ["node", str(POSTER_JS_PATH), "--carousel", json.dumps(image_urls), caption]
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)

    if result.returncode != 0:
        error_msg = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Instagram Carousel publishing error: {error_msg}")

    data = json.loads(result.stdout.strip())
    if data.get("success"):
        return data["media_id"]
    raise RuntimeError(f"Carousel publish failed: {data}")

def publish_reel_to_instagram(video_url: str, caption: str, audio_name: str = "", is_emergency: bool = True) -> str:
    """Publishes a 9:16 video reel with audio."""
    if not is_credentials_ready():
        print("  [Poster] Meta credentials not set or placeholder. Operating in DRY RUN mode.")
        return f"mock_reel_media_{int(time.time())}"

    check_rate_limit_and_throttle(is_emergency=is_emergency)

    env = os.environ.copy()
    env["INSTAGRAM_ACCESS_TOKEN"] = INSTAGRAM_ACCESS_TOKEN
    env["INSTAGRAM_ACCOUNT_ID"] = INSTAGRAM_ACCOUNT_ID

    cmd = ["node", str(POSTER_JS_PATH), "--reel", video_url, caption, audio_name]
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)

    if result.returncode != 0:
        error_msg = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Instagram Reel publishing error: {error_msg}")

    data = json.loads(result.stdout.strip())
    if data.get("success"):
        return data["media_id"]
    raise RuntimeError(f"Reel publish failed: {data}")

def post_first_comment(media_id: str, comment_text: str) -> Optional[str]:
    """Posts an official verified comment under a published post."""
    if not is_credentials_ready():
        return "mock_comment_id"

    env = os.environ.copy()
    env["INSTAGRAM_ACCESS_TOKEN"] = INSTAGRAM_ACCESS_TOKEN
    env["INSTAGRAM_ACCOUNT_ID"] = INSTAGRAM_ACCOUNT_ID

    cmd = ["node", str(POSTER_JS_PATH), "--comment", media_id, comment_text]
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)

    if result.returncode == 0:
        try:
            data = json.loads(result.stdout.strip())
            return data.get("media_id")
        except Exception:
            pass
    return None
