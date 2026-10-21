import re
from typing import List, Dict, Any
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from .base_scraper import BaseScraper

class HPUOfficialScraper(BaseScraper):
    def __init__(self):
        super().__init__(name="HPUOfficialScraper")
        self.endpoints = [
            "https://www.hpuniv.ac.in/notifications",
            "https://www.hpuniv.ac.in/circulars",
            "https://www.hpuniv.ac.in/notice-board",
            "https://www.hpuniv.ac.in/examination",
            "https://icdeolhpu.org/notifications.aspx"
        ]

    def scrape_all(self) -> List[Dict[str, Any]]:
        items = []
        for url in self.endpoints:
            try:
                html = self.fetch_url(url, retries=2, backoff=1.5)
                if not html:
                    continue

                soup = BeautifulSoup(html, "html.parser")
                # Look for table rows or lists of notices
                for row in soup.find_all(["tr", "li"]):
                    text = row.get_text(separator=" ", strip=True)
                    if len(text) < 15:
                        continue

                    link = row.find("a")
                    if not link:
                        continue

                    href = link.get("href")
                    if not href or href.startswith("javascript:") or href.startswith("#"):
                        continue

                    full_url = urljoin(url, href)
                    title = link.get_text(strip=True) or text[:120]

                    # Parse category & priority
                    is_breaking = any(w in text.lower() for w in [
                        "holiday", "postponed", "cancelled", "snowfall", "flood", "closed", "emergency"
                    ])
                    category = "GENERAL"
                    if "result" in text.lower():
                        category = "RESULT"
                    elif "exam" in text.lower() or "date sheet" in text.lower():
                        category = "EXAM"
                    elif "admission" in text.lower() or "counselling" in text.lower():
                        category = "ADMISSION"
                    elif "holiday" in text.lower() or "closure" in text.lower():
                        category = "HOLIDAY"

                    # Extract date if present
                    date_match = re.search(r"\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4}", text)
                    notice_date = date_match.group(0) if date_match else None

                    items.append({
                        "source": "hpuniv.ac.in",
                        "title": title,
                        "url": full_url,
                        "pdf_url": full_url if full_url.endswith(".pdf") else None,
                        "category": category,
                        "priority": "TIER1_BREAKING" if is_breaking else "TIER2_ROUTINE",
                        "notice_date": notice_date,
                        "official_ref_no": None,
                        "raw_text": text,
                        "summary": text
                    })
            except Exception as e:
                print(f"[HPUOfficialScraper] Warning on {url}: {e}")
                continue

        return items
