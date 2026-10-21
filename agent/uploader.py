import os
import base64
import requests
import shutil
from pathlib import Path
from .config import IMGBB_API_KEY, OUTPUT_DIR, SERVER_URL

def upload_image(image_path: str) -> str:
    """Uploads local image to ImgBB or falls back to direct self-hosted URL."""
    filename = Path(image_path).name

    # Try ImgBB if key is configured
    if IMGBB_API_KEY and not IMGBB_API_KEY.startswith("your_"):
        try:
            with open(image_path, "rb") as f:
                img_bytes = f.read()
            b64_image = base64.b64encode(img_bytes).decode("utf-8")
            url = "https://api.imgbb.com/1/upload"
            payload = {"key": IMGBB_API_KEY, "image": b64_image}
            resp = requests.post(url, data=payload, timeout=25)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    return data["data"]["url"]
        except Exception as e:
            print(f"[Uploader] ImgBB upload fallback: {e}")

    # Fallback to direct self-hosted URL
    return f"{SERVER_URL}/generated_cards/{filename}"

def upload_video(video_path: str) -> str:
    """Returns a publicly accessible HTTPS streaming URL for Meta Graph API ingestion."""
    filename = Path(video_path).name
    dest_path = OUTPUT_DIR / filename
    if str(Path(video_path).resolve()) != str(dest_path.resolve()) and not dest_path.exists():
        try:
            shutil.copy2(video_path, dest_path)
        except Exception:
            pass

    # Tier 1: Check if running on server with public domain
    is_server = os.path.exists("/app/generated_cards") or os.getenv("COOLIFY_RESOURCE_UUID") or (os.name != "nt")
    if is_server and SERVER_URL and "localhost" not in SERVER_URL:
        direct_url = f"{SERVER_URL}/generated_cards/{filename}"
        print(f"  [Video Host] Direct Self-Hosted Video URL: {direct_url}")
        return direct_url

    # Tier 2: Try tmpfiles.org for local development
    try:
        with open(video_path, "rb") as f:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            res = requests.post("https://tmpfiles.org/api/v1/upload", files={"file": f}, headers=headers, timeout=30)
            if res.status_code == 200:
                data = res.json()
                if data.get("status") == "success":
                    raw_url = data["data"]["url"]
                    direct_url = raw_url.replace("tmpfiles.org/", "tmpfiles.org/dl/")
                    print(f"  [Video Host] Uploaded to tmpfiles: {direct_url}")
                    return direct_url
    except Exception as e:
        print(f"  [Video Host] tmpfiles upload error: {e}")

    # Tier 3: Local fallback
    if SERVER_URL:
        return f"{SERVER_URL}/generated_cards/{filename}"

    raise RuntimeError(f"Could not get public URL for video: {filename}")
