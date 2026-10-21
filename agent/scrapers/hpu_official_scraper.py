import re
from typing import List, Dict, Any
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from .base_scraper import BaseScraper

class HPUOfficialScraper(BaseScraper):
    """
    Priority 3 (Least Priority):
    - https://www.hpuniv.ac.in/: VC orders, executive council decisions, holidays, circulars (with 500-error resilience)
    - https://icdeolhpu.org/: International Centre for Distance Education & Open Learning circulars
    """
    def __init__(self):
        super().__init__(name="HPUOfficialScraper (hpuniv.ac.in & ICDEOL - Priority 3)")
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
                # Automatic 500 error resilience with retries and exponential backoff
                html = self.fetch_url(url, retries=2, backoff=1.5)
                if not html:
                    continue

                soup = BeautifulSoup(html, "html.parser")
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

                    is_breaking = any(w in text.lower() for w in [
                        "holiday", "postponed", "cancelled", "snowfall", "flood", "closed", "emergency", "strike"
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

                    date_match = re.search(r"\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4}", text)
                    notice_date = date_match.group(0) if date_match else None

                    domain = "icdeolhpu.org" if "icdeol" in url else "hpuniv.ac.in"
                    items.append({
                        "source": f"Official Portal ({domain})",
                        "source_priority": 3,
                        "title": title[:120],
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
                # Resilience against intermittent server errors or 500 status from hpuniv.ac.in
                print(f"[HPUOfficialScraper] Resilient fallback on {url}: {e}")
                continue

        return items
