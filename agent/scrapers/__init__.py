import sys
import datetime

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
from typing import List, Dict, Any
from .hpu_portal_scraper import HPUPortalScraper
from .hpu_official_scraper import HPUOfficialScraper
from .news_rss_scraper import NewsRSSScraper
from .social_scraper import SocialScraper
from .pdf_ocr_parser import process_circular_pdf
from ..db import save_scraped_item, is_content_seen, compute_hash

def run_crawler_pipeline() -> List[Dict[str, Any]]:
    """
    Executes the full multi-source crawler pipeline:
    1. Scrapes official portals, subdomains, RSS news, and social feeds.
    2. Deduplicates via SHA-256 content hash in SQLite.
    3. If an item contains a circular PDF, downloads and parses digital text or OCR.
    4. Saves newly discovered items into the database.
    Returns: List of newly discovered items.
    """
    print(f"\n[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🕷 Starting 30-Minute Multi-Source Crawl...")

    scrapers = [
        HPUPortalScraper(),
        NewsRSSScraper(),
        HPUOfficialScraper(),
        SocialScraper()
    ]

    raw_candidates = []
    for s in scrapers:
        try:
            print(f"  Fetching updates from {s.name}...")
            items = s.scrape_all()
            print(f"  ✔ {s.name} returned {len(items)} items.")
            raw_candidates.extend(items)
        except Exception as e:
            print(f"  ❌ Error running scraper {s.name}: {e}")

    newly_saved_items = []
    portal_scraper = HPUPortalScraper()

    for item in raw_candidates:
        content_hash = compute_hash(f"{item.get('url')}_{item.get('title')}")
        item["content_hash"] = content_hash

        if is_content_seen(content_hash):
            continue

        # If item has a PDF attachment, attempt OCR/text extraction
        pdf_url = item.get("pdf_url")
        if pdf_url:
            print(f"  📄 Downloading and parsing circular PDF: {pdf_url}")
            pdf_bytes = portal_scraper.download_bytes(pdf_url)
            if pdf_bytes:
                ocr_result = process_circular_pdf(pdf_bytes)
                item["ocr_text"] = ocr_result.get("text", "")
                if ocr_result.get("text"):
                    item["summary"] = f"{item['title']}\nDetails from official circular:\n{ocr_result['text'][:300]}"

        # Save to database
        item_id = save_scraped_item(item)
        if item_id:
            item["id"] = item_id
            newly_saved_items.append(item)
            print(f"  ✨ NEW UPDATE RECORDED [ID: {item_id}] [{item['priority']}] [{item['category']}]: {item['title'][:70]}")

    print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🕷 Crawl complete. {len(newly_saved_items)} new unique items saved to DB.")
    return newly_saved_items
