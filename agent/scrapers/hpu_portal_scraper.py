import re
from typing import List, Dict, Any
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from .base_scraper import BaseScraper
from ..freshness import is_item_fresh

class HPUPortalScraper(BaseScraper):
    """
    Priority 3 (Official Portals & Subdomains):
    - https://nadmissions.hpushimla.in/: Merit lists, entrance exam results, cutoffs, counseling notices
    - https://nexams.hpushimla.in/: Examination notifications, datesheets, gazette results, roll-number lists
    - https://nstudentportal.hpushimla.in/: Pre-examination forms, registration dates, student verification circulars
    - https://recruitment.hpushimla.in/: Faculty/non-teaching vacancies, interview schedules
    """
    def __init__(self):
        super().__init__(name="HPUPortalScraper (Official Subdomains - Priority 3)")

    def scrape_admissions_portal(self) -> List[Dict[str, Any]]:
        """Scrapes merit lists, counseling schedules from nadmissions.hpushimla.in."""
        url = "https://nadmissions.hpushimla.in/"
        html = self.fetch_url(url, retries=2, backoff=1.5)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        items = []

        for a in soup.find_all("a"):
            title = a.get_text(strip=True)
            href = a.get("href")
            if not title or not href:
                continue

            href_lower = href.lower()
            if "downloadfile.ashx" in href_lower or ".pdf" in href_lower or any(k in title.lower() for k in ["notice", "merit", "counselling", "cutoff", "entrance"]):
                full_url = urljoin(url, href)
                pdf_url = full_url if ("downloadfile.ashx" in href_lower or ".pdf" in href_lower) else None

                priority = "TIER1_BREAKING" if any(w in title.lower() for w in ["urgent", "postponed", "cancelled", "last date today"]) else "TIER2_ROUTINE"

                items.append({
                    "source": "Official Portal (nadmissions.hpushimla.in)",
                    "source_priority": 3,
                    "title": title,
                    "url": full_url,
                    "pdf_url": pdf_url,
                    "category": "ADMISSION",
                    "priority": priority,
                    "notice_date": None,
                    "official_ref_no": None,
                    "raw_text": f"HPU Admissions Portal: {title}",
                    "summary": f"HPU Admission Notice: {title}"
                })

        return items

    def scrape_exams_portal(self) -> List[Dict[str, Any]]:
        """Scrapes notices from nexams.hpushimla.in."""
        base_desc_url = "https://nexams.hpushimla.in/CollegePortal/General_Inst_Not_Desc.aspx?id="
        items = []

        for notice_id in range(1, 15):
            url = f"{base_desc_url}{notice_id}"
            html = self.fetch_url(url, retries=2, backoff=1.0)
            if not html:
                continue

            soup = BeautifulSoup(html, "html.parser")
            subject_td = None
            date_td = None
            desc_td = None

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

                category = "EXAM"
                if "result" in combined_desc.lower():
                    category = "RESULT"
                elif "registration" in combined_desc.lower() or "rme" in combined_desc.lower():
                    category = "ADMISSION"

                items.append({
                    "source": "Official Portal (nexams.hpushimla.in)",
                    "source_priority": 3,
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

    def scrape_student_portal(self) -> List[Dict[str, Any]]:
        """Scrapes registration dates & verification circulars from nstudentportal.hpushimla.in."""
        url = "https://nstudentportal.hpushimla.in/"
        html = self.fetch_url(url, retries=2, backoff=1.5)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        items = []

        # Find important notification callouts
        for el in soup.find_all(["div", "p", "marquee"]):
            text = el.get_text(separator=" ", strip=True)
            if any(k in text.lower() for k in ["important information", "student verification", "pre-examination", "registration date"]):
                if 25 < len(text) < 400:
                    items.append({
                        "source": "Official Portal (nstudentportal.hpushimla.in)",
                        "source_priority": 3,
                        "title": text[:120],
                        "url": url,
                        "pdf_url": None,
                        "category": "ADMISSION",
                        "priority": "TIER2_ROUTINE",
                        "notice_date": None,
                        "official_ref_no": None,
                        "raw_text": text,
                        "summary": text
                    })
                    break

        return items

    def scrape_recruitment_portal(self) -> List[Dict[str, Any]]:
        """Scrapes faculty/non-teaching vacancies & schedules from recruitment.hpushimla.in."""
        url = "https://recruitment.hpushimla.in/"
        html = self.fetch_url(url, retries=2, backoff=1.5)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        items = []

        for a in soup.find_all("a"):
            title = a.get_text(strip=True)
            href = a.get("href")
            if not title or not href or len(title) < 15:
                continue

            title_lower = title.lower()
            if any(k in title_lower for k in ["notice", "interview", "recruitment", "advertisement", "extension", "vacancy"]):
                full_url = urljoin(url, href)
                pdf_url = full_url if full_url.endswith(".pdf") else None

                items.append({
                    "source": "Official Portal (recruitment.hpushimla.in)",
                    "source_priority": 3,
                    "title": title[:120],
                    "url": full_url,
                    "pdf_url": pdf_url,
                    "category": "GENERAL",
                    "priority": "TIER2_ROUTINE",
                    "notice_date": None,
                    "official_ref_no": None,
                    "raw_text": title,
                    "summary": f"HPU Recruitment Notice: {title}"
                })

        return items[:10]

    def scrape_all(self) -> List[Dict[str, Any]]:
        raw_results = []
        try:
            raw_results.extend(self.scrape_admissions_portal())
        except Exception as e:
            print(f"[HPUPortalScraper] Admissions scrape warning: {e}")

        try:
            raw_results.extend(self.scrape_exams_portal())
        except Exception as e:
            print(f"[HPUPortalScraper] Exams scrape warning: {e}")

        try:
            raw_results.extend(self.scrape_student_portal())
        except Exception as e:
            print(f"[HPUPortalScraper] Student portal scrape warning: {e}")

        try:
            raw_results.extend(self.scrape_recruitment_portal())
        except Exception as e:
            print(f"[HPUPortalScraper] Recruitment portal scrape warning: {e}")

        fresh_results = []
        for it in raw_results:
            fresh, reason = is_item_fresh(it)
            if fresh:
                fresh_results.append(it)

        return fresh_results
