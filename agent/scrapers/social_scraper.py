import requests
from typing import List, Dict, Any
from .base_scraper import BaseScraper
from ..config import INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_ACCOUNT_ID

class SocialScraper(BaseScraper):
    def __init__(self):
        super().__init__(name="SocialScraper")
        # Target handles known for student alerts
        self.target_handles = ["hpuupdate", "sfihpu", "abvp_hpu_unit"]

    def scrape_via_business_discovery(self) -> List[Dict[str, Any]]:
        """Uses Meta Graph API Business Discovery to monitor target public accounts."""
        if not INSTAGRAM_ACCESS_TOKEN or not INSTAGRAM_ACCOUNT_ID or "your_" in INSTAGRAM_ACCESS_TOKEN:
            return []

        base_url = "https://graph.facebook.com/v21.0"
        items = []

        for handle in self.target_handles:
            try:
                endpoint = (
                    f"{base_url}/{INSTAGRAM_ACCOUNT_ID}?"
                    f"fields=business_discovery.username({handle})"
                    f"{{media.limit(5){{id,caption,timestamp,permalink}}}}&"
                    f"access_token={INSTAGRAM_ACCESS_TOKEN}"
                )
                res = requests.get(endpoint, timeout=12).json()
                media_list = res.get("business_discovery", {}).get("media", {}).get("data", [])

                for m in media_list:
                    caption = m.get("caption", "")
                    permalink = m.get("permalink", "")
                    if not caption:
                        continue

                    caption_lower = caption.lower()
                    is_breaking = any(w in caption_lower for w in [
                        "postpone", "cancel", "alert", "holiday", "strike", "urgent"
                    ])

                    category = "GENERAL"
                    if "result" in caption_lower:
                        category = "RESULT"
                    elif "exam" in caption_lower or "date sheet" in caption_lower:
                        category = "EXAM"
                    elif "admission" in caption_lower:
                        category = "ADMISSION"

                    items.append({
                        "source": f"Instagram @{handle}",
                        "title": caption.split("\n")[0][:100],
                        "url": permalink,
                        "pdf_url": None,
                        "category": category,
                        "priority": "TIER1_BREAKING" if is_breaking else "TIER2_ROUTINE",
                        "notice_date": m.get("timestamp"),
                        "official_ref_no": None,
                        "raw_text": caption,
                        "summary": caption[:250]
                    })
            except Exception as e:
                print(f"[SocialScraper] Business discovery warning for @{handle}: {e}")

        return items

    def scrape_all(self) -> List[Dict[str, Any]]:
        return self.scrape_via_business_discovery()
