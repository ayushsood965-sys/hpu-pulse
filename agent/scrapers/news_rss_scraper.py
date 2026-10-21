import re
import urllib.parse
import xml.etree.ElementTree as ET
from typing import List, Dict, Any
from .base_scraper import BaseScraper
from ..freshness import is_item_fresh

class NewsRSSScraper(BaseScraper):
    """
    Priority 2 Scraper: Curated Regional Newspaper Streams covering HPU Shimla:
    - Amar Ujala (Himachal / Shimla Edition): Local reporting on HPU administrative decisions & holidays
    - Divya Himachal: Authoritative on teacher strikes, student elections, and results
    - The Tribune (Himachal Edition): VC appointments, High Court orders, and academic circulars
    """
    def __init__(self):
        super().__init__(name="NewsRSSScraper (Regional Newspapers - Priority 2)")
        self.streams = [
            {
                "publication": "Amar Ujala",
                "query": 'Amar Ujala (HPU OR "Himachal Pradesh University" OR "एचपीयू")',
                "hl": "hi",
                "ceid": "IN:hi"
            },
            {
                "publication": "Divya Himachal",
                "query": 'Divya Himachal (HPU OR "Himachal Pradesh University" OR "एचपीयू")',
                "hl": "hi",
                "ceid": "IN:hi"
            },
            {
                "publication": "The Tribune",
                "query": '"The Tribune" ("Himachal Pradesh University" OR "HPU Shimla")',
                "hl": "en-IN",
                "ceid": "IN:en"
            },
            {
                "publication": "HPU Exam & Alert Stream",
                "query": '"HPU Shimla" (exam OR result OR admission OR datesheet OR holiday OR postpone)',
                "hl": "en-IN",
                "ceid": "IN:en"
            },
            {
                "publication": "Himachal Vernacular Stream",
                "query": '"एचपीयू शिमला" OR "हिमाचल विश्वविद्यालय शिमला" परीक्षा OR परिणाम',
                "hl": "hi",
                "ceid": "IN:hi"
            }
        ]

    def _clean_title(self, title: str) -> str:
        """Strips newspaper branding suffix from title."""
        if not title:
            return ""
        clean = re.sub(
            r"\s*-\s*(?:Amar\s*Ujala|Divya\s*Himachal|The\s*Tribune|Tribune\s*India|Hindustan\s*Times|Dainik\s*Bhaskar|Jagran|News18|Zee\s*News).*$",
            "",
            title,
            flags=re.IGNORECASE
        )
        return clean.strip()

    def fetch_stream(self, stream_config: Dict[str, str]) -> List[Dict[str, Any]]:
        pub = stream_config["publication"]
        query = stream_config["query"]
        hl = stream_config["hl"]
        ceid = stream_config["ceid"]

        encoded_q = urllib.parse.quote(query)
        feed_url = f"https://news.google.com/rss/search?q={encoded_q}&hl={hl}&gl=IN&ceid={ceid}"
        xml_content = self.fetch_url(feed_url, retries=2, backoff=1.0)
        if not xml_content:
            return []

        items = []
        try:
            root = ET.fromstring(xml_content.encode("utf-8", errors="replace"))
            for entry in root.findall(".//item")[:15]:
                raw_title = entry.find("title").text if entry.find("title") is not None else ""
                link = entry.find("link").text if entry.find("link") is not None else ""
                pub_date = entry.find("pubDate").text if entry.find("pubDate") is not None else ""
                desc = entry.find("description").text if entry.find("description") is not None else ""

                if not raw_title or not link:
                    continue

                cleaned_title = self._clean_title(raw_title)
                title_lower = cleaned_title.lower()

                # Filter out completely irrelevant news
                if not any(k in title_lower for k in ["hpu", "himachal", "university", "विश्वविद्यालय", "एचपीयू", "शिमला"]):
                    continue

                # Classify priority & category
                is_breaking = any(w in title_lower for w in [
                    "postpone", "cancel", "holiday", "strike", "clash", "protest", "snowfall", "closed", "rescheduled", "स्थगित", "छुट्टी", "बंद"
                ])
                category = "GENERAL"
                if "result" in title_lower or "परिणाम" in title_lower or "मेरिट" in title_lower:
                    category = "RESULT"
                elif "exam" in title_lower or "परीक्षा" in title_lower or "datesheet" in title_lower or "डेटशीट" in title_lower:
                    category = "EXAM"
                elif "admission" in title_lower or "दाखिला" in title_lower or "काउंसलिंग" in title_lower:
                    category = "ADMISSION"
                elif "holiday" in title_lower or "छुट्टी" in title_lower or "अवकाश" in title_lower:
                    category = "HOLIDAY"

                candidate = {
                    "source": f"Regional News ({pub})",
                    "source_priority": 2,
                    "title": cleaned_title,
                    "url": link,
                    "pdf_url": None,
                    "category": category,
                    "priority": "TIER1_BREAKING" if is_breaking else "TIER2_ROUTINE",
                    "notice_date": pub_date,
                    "official_ref_no": None,
                    "raw_text": f"Regional Newspaper ({pub}) Report: {cleaned_title}. {desc}",
                    "summary": f"{cleaned_title}\n{desc}" if desc else cleaned_title
                }

                # STRICT FRESHNESS FILTER: Only today or upcoming
                fresh, reason = is_item_fresh(candidate)
                if not fresh:
                    # Drop stale news
                    continue

                items.append(candidate)
        except Exception as e:
            print(f"[NewsRSSScraper] XML parsing error for '{pub}': {e}")

        return items

    def scrape_all(self) -> List[Dict[str, Any]]:
        all_items = []
        for stream in self.streams:
            try:
                results = self.fetch_stream(stream)
                all_items.extend(results)
            except Exception as e:
                print(f"[NewsRSSScraper] Error fetching {stream['publication']}: {e}")
        return all_items
