import re
from typing import List, Dict, Any
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from .base_scraper import BaseScraper
from .pdf_ocr_parser import process_circular_pdf

class HPUPortalScraper(BaseScraper):
    def __init__(self):
        super().__init__(name="HPUPortalScraper")

    def scrape_admissions_portal(self) -> List[Dict[str, Any]]:
        """Scrapes merit lists, counseling schedules from nadmissions.hpushimla.in."""
        url = "https://nadmissions.hpushimla.in/"
        html = self.fetch_url(url)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        items = []

        # Find all notice links
        for a in soup.find_all("a"):
            title = a.get_text(strip=True)
            href = a.get("href")
            if not title or not href:
                continue

            href_lower = href.lower()
            if "downloadfile.ashx" in href_lower or ".pdf" in href_lower or "notice" in title.lower() or "merit" in title.lower() or "counselling" in title.lower():
                full_url = urljoin(url, href)
                pdf_url = full_url if ("downloadfile.ashx" in href_lower or ".pdf" in href_lower) else None

                # Infer priority: Merit lists / counseling are typically Tier 2, but emergency counseling deadlines can be Tier 1
                priority = "TIER1_BREAKING" if any(w in title.lower() for w in ["urgent", "postponed", "cancelled", "last date today"]) else "TIER2_ROUTINE"

                item = {
                    "source": "nadmissions.hpushimla.in",
                    "title": title,
                    "url": full_url,
                    "pdf_url": pdf_url,
                    "category": "ADMISSION",
                    "priority": priority,
                    "notice_date": None,
                    "official_ref_no": None,
                    "raw_text": title,
                    "summary": f"HPU Admission Update: {title}"
                }
                items.append(item)

        return items

    def scrape_exams_portal(self) -> List[Dict[str, Any]]:
        """Scrapes notices from nexams.hpushimla.in."""
        base_desc_url = "https://nexams.hpushimla.in/CollegePortal/General_Inst_Not_Desc.aspx?id="
        items = []

        # Probe latest IDs (typically 1 to 20 or dynamic)
        for notice_id in range(1, 15):
            url = f"{base_desc_url}{notice_id}"
            html = self.fetch_url(url)
            if not html:
                continue

            soup = BeautifulSoup(html, "html.parser")
            subject_td = None
            date_td = None
            desc_td = None

            # Look for Subject, Description, Posted Date labels
            for tr in soup.find_all("tr"):
                row_text = tr.get_text(strip=True)
                if "Subject" in row_text:
                    parts = tr.find_all("td")
                    if len(parts) >= 2:
                        subject_td = parts[-1].get_text(strip=True)
                elif "Description" in row_text:
                    parts = tr.find_all("td")
                    if len(parts) >= 2:
                        desc_td = parts[-1].get_text(strip=True)
                elif "Posted Date" in row_text:
                    date_match = re.search(r"\d{1,2}/\d{1,2}/\d{4}", row_text)
                    if date_match:
                        date_td = date_match.group(0)

            if subject_td and len(subject_td) > 3:
                title = subject_td
                combined_desc = f"{title}. {desc_td or ''}".strip()
                is_breaking = any(w in combined_desc.lower() for w in ["postponed", "cancelled", "revised", "urgent", "holiday", "strike"])
                
                # Determine category
                category = "EXAM"
                if "result" in combined_desc.lower():
                    category = "RESULT"
                elif "registration" in combined_desc.lower() or "rme" in combined_desc.lower():
                    category = "ADMISSION"

                items.append({
                    "source": "nexams.hpushimla.in",
                    "title": title,
                    "url": url,
                    "pdf_url": None,
                    "category": category,
                    "priority": "TIER1_BREAKING" if is_breaking else "TIER2_ROUTINE",
                    "notice_date": date_td,
                    "official_ref_no": f"HPU/EXAM/{notice_id}",
                    "raw_text": combined_desc,
                    "summary": combined_desc
                })

        return items

    def scrape_all(self) -> List[Dict[str, Any]]:
        results = []
        try:
            results.extend(self.scrape_admissions_portal())
        except Exception as e:
            print(f"[HPUPortalScraper] Admissions scrape error: {e}")

        try:
            results.extend(self.scrape_exams_portal())
        except Exception as e:
            print(f"[HPUPortalScraper] Exams scrape error: {e}")

        return results
