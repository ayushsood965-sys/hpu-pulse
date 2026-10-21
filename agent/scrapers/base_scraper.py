import time
import requests
import urllib3
from typing import Optional, Dict

# Suppress insecure HTTPS warning for university servers with self-signed/expired certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

class BaseScraper:
    def __init__(self, name: str, timeout: int = 15):
        self.name = name
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def fetch_url(self, url: str, retries: int = 3, backoff: float = 2.0) -> Optional[str]:
        """Fetches URL with automatic retries, timeout, and SSL fallback."""
        for attempt in range(1, retries + 1):
            try:
                response = self.session.get(url, timeout=self.timeout, verify=False)
                if response.status_code == 200:
                    return response.text
                elif response.status_code in (404, 403, 500):
                    print(f"[{self.name}] HTTP {response.status_code} for {url} (Attempt {attempt}/{retries})")
            except Exception as e:
                print(f"[{self.name}] Error fetching {url} on attempt {attempt}: {e}")
            
            if attempt < retries:
                time.sleep(backoff * attempt)
        return None

    def download_bytes(self, url: str, timeout: int = 25) -> Optional[bytes]:
        """Downloads binary content (e.g. PDF circulars) safely."""
        try:
            res = self.session.get(url, timeout=timeout, verify=False)
            if res.status_code == 200:
                return res.content
        except Exception as e:
            print(f"[{self.name}] Failed to download binary from {url}: {e}")
        return None
