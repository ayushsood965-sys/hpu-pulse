import xml.etree.ElementTree as ET
import urllib.parse
from typing import List, Dict, Any
from .base_scraper import BaseScraper

class NewsRSSScraper(BaseScraper):
    def __init__(self):
        super().__init__(name="NewsRSSScraper")
        self.queries = [
            ("Himachal Pradesh University Shimla", "en-IN", "IN:en"),
            ("HPU Shimla exam OR result OR admission OR holiday", "en-IN", "IN:en"),
            ("हिमाचल प्रदेश विश्वविद्यालय शिमला", "hi", "IN:hi")
        ]

    def fetch_rss_feed(self, query: str, hl: str, ceid: str) -> List[Dict[str, Any]]:
        encoded_q = urllib.parse.quote(query)
        feed_url = f"https://news.google.com/rss/search?q={encoded_q}&hl={hl}&gl=IN&ceid={ceid}"
        xml_content = self.fetch_url(feed_url)
        if not xml_content:
            return []

        items = []
        try:
            root = ET.fromstring(xml_content.encode("utf-8", errors="replace"))
            for entry in root.findall(".//item")[:15]:
                title = entry.find("title").text if entry.find("title") is not None else ""
                link = entry.find("link").text if entry.find("link") is not None else ""
                pub_date = entry.find("pubDate").text if entry.find("pubDate") is not None else ""
                desc = entry.find("description").text if entry.find("description") is not None else ""

                if not title or not link:
                    continue

                # Filter out irrelevant news
                title_lower = title.lower()
                if not any(k in title_lower for k in ["hpu", "himachal", "university", "विश्वविद्यालय"]):
                    continue

                # Classify priority & category
                is_breaking = any(w in title_lower for w in [
                    "postpone", "cancel", "holiday", "strike", "clash", "protest", "snowfall", "closed", "rescheduled"
                ])
                category = "GENERAL"
                if "result" in title_lower or "परिणाम" in title_lower:
                    category = "RESULT"
                elif "exam" in title_lower or "परीक्षा" in title_lower or "datesheet" in title_lower:
                    category = "EXAM"
                elif "admission" in title_lower or "दाखिला" in title_lower:
                    category = "ADMISSION"
                elif "holiday" in title_lower or "छुट्टी" in title_lower:
                    category = "HOLIDAY"

                items.append({
                    "source": "Regional News (Amar Ujala/Divya Himachal/Tribune)",
                    "title": title,
                    "url": link,
                    "pdf_url": None,
                    "category": category,
                    "priority": "TIER1_BREAKING" if is_breaking else "TIER2_ROUTINE",
                    "notice_date": pub_date,
                    "official_ref_no": None,
                    "raw_text": f"{title}. {desc}",
                    "summary": title
                })
        except Exception as e:
            print(f"[NewsRSSScraper] XML parsing error for '{query}': {e}")

        return items

    def scrape_all(self) -> List[Dict[str, Any]]:
        all_items = []
        for query, hl, ceid in self.queries:
            try:
                results = self.fetch_rss_feed(query, hl, ceid)
                all_items.extend(results)
            except Exception as e:
                print(f"[NewsRSSScraper] Error fetching RSS query '{query}': {e}")
        return all_items
