import re
import urllib.parse
import xml.etree.ElementTree as ET
from typing import List, Dict, Any
import requests
from bs4 import BeautifulSoup
from googlenewsdecoder import gnewsdecoder

from .base_scraper import BaseScraper
from ..freshness import is_item_fresh

class NewsRSSScraper(BaseScraper):
    """
    Priority 2 Scraper: Curated Regional Newspaper Streams covering HPU Shimla:
    - Amar Ujala (Himachal / Shimla Edition): Local reporting on HPU administrative decisions & holidays
    - Divya Himachal: Authoritative on teacher strikes, student elections, and results
    - The Tribune (Himachal Edition): VC appointments, High Court orders, and academic circulars
    - Jagran / Times of India / Hindustan Times: University results, cutoffs, and exam schedules
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

    def _fetch_article_body(self, google_link: str) -> Dict[str, str]:
        """
        Decodes Google News RSS link to publisher direct URL and extracts rich article text,
        meta description, and specific details (subjects, dates, percentages).
        """
        direct_url = google_link
        try:
            decoded = gnewsdecoder(google_link)
            if decoded.get("success") and decoded.get("decoded_url"):
                direct_url = decoded["decoded_url"]
        except Exception:
            pass

        article_text = ""
        meta_desc = ""
        try:
            resp = requests.get(
                direct_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                timeout=5.0
            )
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                
                # 1. OpenGraph / Meta Description
                og = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "description"})
                if og and og.get("content"):
                    meta_desc = og.get("content").strip()

                # 2. Main content container or article body divs
                story_div = None
                for d in soup.find_all(["div", "article", "section"]):
                    classes = d.get("class") or []
                    class_str = " ".join(classes).lower() if isinstance(classes, list) else str(classes).lower()
                    if any(k in class_str for k in ["story", "article-body", "news-detail", "post-content", "content-body"]):
                        txt = d.get_text(strip=True)
                        if len(txt) > 80:
                            story_div = d
                            break

                body_paras = []
                search_root = story_div if story_div else soup
                for p in search_root.find_all("p"):
                    p_txt = p.get_text(strip=True)
                    if len(p_txt) > 25 and not any(j in p_txt for j in ["Android", "डाउनलोड करें", "App", "Subscribe", "विज्ञापन"]):
                        if p_txt not in body_paras:
                            body_paras.append(p_txt)
                    if len(body_paras) >= 5:
                        break

                if body_paras:
                    article_text = "\n".join(body_paras)
                elif story_div:
                    article_text = story_div.get_text(separator="\n", strip=True)
        except Exception:
            pass

        full_details = ""
        if meta_desc and article_text:
            if meta_desc.lower() in article_text.lower():
                full_details = article_text
            else:
                full_details = f"{meta_desc}\n{article_text}"
        elif meta_desc:
            full_details = meta_desc
        elif article_text:
            full_details = article_text

        return {
            "direct_url": direct_url,
            "details": full_details.strip()
        }

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

                # Extract rich article body from decoded publisher URL
                article_info = self._fetch_article_body(link)
                direct_url = article_info["direct_url"]
                article_details = article_info["details"]

                rich_summary = f"{cleaned_title}\n{article_details}" if article_details else (f"{cleaned_title}\n{desc}" if desc else cleaned_title)

                candidate = {
                    "source": f"Regional News ({pub})",
                    "source_priority": 2,
                    "title": cleaned_title,
                    "url": direct_url or link,
                    "pdf_url": None,
                    "category": category,
                    "priority": "TIER1_BREAKING" if is_breaking else "TIER2_ROUTINE",
                    "notice_date": pub_date,
                    "official_ref_no": None,
                    "ocr_text": article_details,
                    "raw_text": f"Regional Newspaper ({pub}) Report: {cleaned_title}.\n{article_details or desc}",
                    "summary": rich_summary
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
