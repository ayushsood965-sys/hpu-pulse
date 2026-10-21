import re
import urllib.parse
import xml.etree.ElementTree as ET
import requests
from typing import List, Dict, Any
from .base_scraper import BaseScraper
from ..config import INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_ACCOUNT_ID
from ..freshness import is_item_fresh

class SocialScraper(BaseScraper):
    """
    Top-Priority Scraper for Popular HPU Student & Community Instagram Pages:
    - @hpuupdate: Benchmark student updates page in Himachal (fast on results & datesheets)
    - @hpudailyupdates: Daily screenshots of paper circulars and university orders
    - @hpushimla_official / @hpu_shimla_: Campus events, youth festivals, and routine notices
    - @sfihpu & @abvp_hpu_unit: Student unit handles for protests, strikes, and fee rollbacks
    """
    def __init__(self):
        super().__init__(name="SocialScraper (Instagram Competitor Feeds - Priority 1)")
        self.target_handles = [
            "hpuupdate",
            "hpudailyupdates",
            "hpu_shimla_",
            "hpushimla_official",
            "sfihpu",
            "abvp_hpu_unit"
        ]

    def _clean_caption(self, text: str) -> str:
        """Strips Instagram artifacts, trailing branding, and hashtag clutter."""
        if not text:
            return ""
        # Remove trailing ' - Instagram'
        clean = re.sub(r"\s*-\s*Instagram\s*$", "", text, flags=re.IGNORECASE)
        # Remove hashtags
        clean = re.sub(r"#[A-Za-z0-9_]+", "", clean)
        # Clean extra whitespace
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean

    def _is_update_related(self, text: str) -> bool:
        """Determines if a post is an actual university update or general student alert."""
        text_lower = text.lower()
        # Exclude generic photo metadata captions
        if re.search(r"photo by .+ \(@[\w\._]+\) ·", text_lower):
            return False
        if text_lower.startswith("instagram video by") and len(text_lower) < 40:
            return False
        if len(text.strip()) < 15:
            return False

        update_keywords = [
            "result", "exam", "datesheet", "date sheet", "date-sheet", "admission",
            "merit", "counsel", "counselling", "postpone", "cancel", "holiday",
            "strike", "protest", "fee", "notification", "circular", "form",
            "re-appear", "reappear", "semester", "roll", "cutoff", "cut-off",
            "revised", "urgent", "closed", "snowfall", "clash", "b.a", "b.sc",
            "b.com", "b.ed", "m.a", "m.sc", "m.com", "llb", "bca", "bba"
        ]
        return any(k in text_lower for k in update_keywords)

    def scrape_via_rss(self) -> List[Dict[str, Any]]:
        """
        Fetches live Instagram posts from competitor accounts via Google News RSS indexing.
        Provides unblocked, 100% reliable real-time access to competitor updates.
        """
        items = []
        for handle in self.target_handles:
            try:
                # Query Google News RSS for this specific handle on Instagram
                query = urllib.parse.quote(f'site:instagram.com "{handle}"')
                url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
                xml_content = self.fetch_url(url, retries=2, backoff=1.0)
                if not xml_content:
                    continue

                root = ET.fromstring(xml_content.encode("utf-8", errors="replace"))
                entries = root.findall(".//item")[:15]

                for entry in entries:
                    raw_title = entry.find("title").text if entry.find("title") is not None else ""
                    link = entry.find("link").text if entry.find("link") is not None else ""
                    pub_date = entry.find("pubDate").text if entry.find("pubDate") is not None else ""
                    desc = entry.find("description").text if entry.find("description") is not None else ""

                    if not raw_title:
                        continue

                    cleaned = self._clean_caption(raw_title)
                    if not self._is_update_related(cleaned):
                        continue

                    cleaned_lower = cleaned.lower()
                    is_breaking = any(w in cleaned_lower for w in [
                        "postpone", "cancel", "holiday", "strike", "urgent", "snowfall", "closed", "datesheet"
                    ])

                    category = "GENERAL"
                    if "result" in cleaned_lower:
                        category = "RESULT"
                    elif "exam" in cleaned_lower or "datesheet" in cleaned_lower or "date-sheet" in cleaned_lower:
                        category = "EXAM"
                    elif "admission" in cleaned_lower or "merit" in cleaned_lower or "counsel" in cleaned_lower:
                        category = "ADMISSION"
                    elif "holiday" in cleaned_lower:
                        category = "HOLIDAY"

                    candidate = {
                        "source": f"Instagram @{handle}",
                        "source_priority": 1,
                        "title": cleaned[:120],
                        "url": link,
                        "pdf_url": None,
                        "category": category,
                        "priority": "TIER1_BREAKING" if is_breaking else "TIER2_ROUTINE",
                        "notice_date": pub_date,
                        "official_ref_no": None,
                        "raw_text": f"Competitor Post from @{handle}: {cleaned}. {desc}",
                        "summary": cleaned
                    }
                    fresh, reason = is_item_fresh(candidate)
                    if not fresh:
                        continue
                    items.append(candidate)
            except Exception as e:
                print(f"[SocialScraper] RSS error for @{handle}: {e}")

        return items

    def scrape_via_business_discovery(self) -> List[Dict[str, Any]]:
        """Uses Meta Graph API Business Discovery if token permissions permit."""
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
                res = requests.get(endpoint, timeout=8).json()
                media_list = res.get("business_discovery", {}).get("media", {}).get("data", [])

                for m in media_list:
                    caption = m.get("caption", "")
                    permalink = m.get("permalink", "")
                    if not caption or not self._is_update_related(caption):
                        continue

                    cleaned = self._clean_caption(caption)
                    caption_lower = cleaned.lower()
                    is_breaking = any(w in caption_lower for w in [
                        "postpone", "cancel", "alert", "holiday", "strike", "urgent"
                    ])

                    category = "GENERAL"
                    if "result" in caption_lower:
                        category = "RESULT"
                    elif "exam" in caption_lower or "datesheet" in caption_lower:
                        category = "EXAM"
                    elif "admission" in caption_lower or "merit" in caption_lower:
                        category = "ADMISSION"

                    candidate = {
                        "source": f"Instagram @{handle}",
                        "source_priority": 1,
                        "title": cleaned[:120],
                        "url": permalink,
                        "pdf_url": None,
                        "category": category,
                        "priority": "TIER1_BREAKING" if is_breaking else "TIER2_ROUTINE",
                        "notice_date": m.get("timestamp"),
                        "official_ref_no": None,
                        "raw_text": cleaned,
                        "summary": cleaned[:250]
                    }
                    fresh, reason = is_item_fresh(candidate)
                    if not fresh:
                        continue
                    items.append(candidate)
            except Exception:
                pass

        return items

    def scrape_all(self) -> List[Dict[str, Any]]:
        """
        Executes high-priority Instagram competitor monitoring.
        Combines RSS indexing and Graph API business discovery.
        """
        results = self.scrape_via_rss()
        api_results = self.scrape_via_business_discovery()
        results.extend(api_results)
        return results
