import re
import email.utils
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, Dict, Any, List

# Indian Standard Time (IST = UTC+5:30)
IST = timezone(timedelta(hours=5, minutes=30))

def get_now_ist() -> datetime:
    """Returns current datetime in Indian Standard Time."""
    return datetime.now(IST)

def parse_date_to_ist(date_str: Optional[str]) -> Optional[datetime]:
    """
    Parses various date string formats into a timezone-aware datetime in IST:
    - RFC 2822/822 (Google News RSS: 'Wed, 21 Oct 2026 15:29:27 GMT')
    - ISO 8601 (Instagram Graph API: '2026-10-21T10:00:00+0000')
    - Standard numeric formats: 'DD/MM/YYYY', 'YYYY-MM-DD', 'MM/DD/YYYY', 'DD-MM-YYYY', 'DD.MM.YYYY'
    - Textual dates: '21 October 2026', '21-Oct-2026', 'October 21, 2026'
    """
    if not date_str or not isinstance(date_str, str):
        return None

    cleaned = date_str.strip()
    if not cleaned:
        return None

    # 1. Try RFC 2822 (standard for RSS feeds)
    try:
        dt = email.utils.parsedate_to_datetime(cleaned)
        if dt:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(IST)
    except Exception:
        pass

    # 2. Try ISO 8601
    try:
        iso_str = cleaned.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso_str)
        if dt:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=IST)
            return dt.astimezone(IST)
    except Exception:
        pass

    # 3. Numeric date patterns
    numeric_formats = [
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d.%m.%Y",
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d/%m/%y",
        "%d-%m-%y",
        "%d.%m.%y"
    ]
    for fmt in numeric_formats:
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.replace(tzinfo=IST)
        except Exception:
            pass

    # 4. English textual date patterns
    text_formats = [
        "%d %B %Y",
        "%d %b %Y",
        "%B %d, %Y",
        "%b %d, %Y",
        "%d-%b-%Y",
        "%d-%B-%Y"
    ]
    # Remove ordinal suffixes like 21st, 22nd, 23rd, 24th
    normalized = re.sub(r"(\d{1,2})(?:st|nd|rd|th)", r"\1", cleaned, flags=re.IGNORECASE)
    for fmt in text_formats:
        try:
            dt = datetime.strptime(normalized, fmt)
            return dt.replace(tzinfo=IST)
        except Exception:
            pass

    # 5. Regex search within longer strings
    date_regex = re.search(r"(\d{1,2})[-/\.](\d{1,2})[-/\.](\d{2,4})", cleaned)
    if date_regex:
        matched = date_regex.group(0)
        for fmt in numeric_formats:
            try:
                dt = datetime.strptime(matched, fmt)
                return dt.replace(tzinfo=IST)
            except Exception:
                pass

    return None

def extract_dates_from_text(text: str) -> List[datetime]:
    """Extracts all recognizable calendar dates from a text string."""
    if not text:
        return []

    found_dates = []
    # Pattern 1: DD/MM/YYYY or DD-MM-YYYY
    for m in re.finditer(r"\b(\d{1,2})[-/\.](\d{1,2})[-/\.](\d{4})\b", text):
        parsed = parse_date_to_ist(m.group(0))
        if parsed:
            found_dates.append(parsed)

    # Pattern 2: DD Month YYYY (e.g. 21 October 2026, 25th Aug 2026)
    for m in re.finditer(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(\d{4})\b", text, re.IGNORECASE):
        parsed = parse_date_to_ist(m.group(0))
        if parsed:
            found_dates.append(parsed)

    return found_dates

def is_item_fresh(item: Dict[str, Any], max_age_hours: float = 24.0) -> Tuple[bool, str]:
    """
    STRICT FRESHNESS FILTER:
    - Only allows updates published TODAY (or within the last 24 hours).
    - Or updates explicitly announcing an UPCOMING date/deadline (event date >= today)
      provided the notice is recent.
    - Strictly rejects previous updates, past year archives (2020-2025), and events
      that already occurred in the past.
    """
    now_ist = get_now_ist()
    today_ist = now_ist.date()
    current_year = now_ist.year

    title = str(item.get("title") or "")
    raw_text = str(item.get("raw_text") or "")
    summary = str(item.get("summary") or "")
    combined_text = f"{title} {raw_text} {summary}"

    # 1. Past Years Archive Filter (Strict Rule)
    # Reject anything mentioning 2018 up to previous year (unless it specifically mentions current academic cycle)
    for past_year in range(2018, current_year):
        year_str = str(past_year)
        if year_str in combined_text:
            # Check if this is an archive notice like Rectt-2022 or 19 Jul 2024
            if not f"{current_year}" in combined_text:
                return False, f"Rejection: Mentions past archive year {past_year}"

    # 2. Check for explicit past event indicators
    # e.g. "held on 26th August", "clash occurred on 19 Sep", "held on yesterday"
    past_event_patterns = [
        r"held\s+on\s+\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(?:20\d\d)?",
        r"conducted\s+on\s+\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*",
        r"organized\s+on\s+\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
    ]
    for pat in past_event_patterns:
        match = re.search(pat, combined_text, re.IGNORECASE)
        if match:
            # Verify if the matched date is in the past
            parsed_past = parse_date_to_ist(match.group(0))
            if parsed_past and parsed_past.date() < today_ist:
                return False, f"Rejection: Event already took place in the past ({match.group(0)})"

    # 3. Notice Publication Date Check
    notice_date_str = item.get("notice_date")
    pub_dt = parse_date_to_ist(notice_date_str) if notice_date_str else None

    if pub_dt:
        age_hours = (now_ist - pub_dt).total_seconds() / 3600.0

        # Check if published today in IST
        if pub_dt.date() == today_ist:
            return True, f"Approved: Published today ({pub_dt.strftime('%Y-%m-%d %H:%M')} IST)"

        # Allow grace period of max_age_hours (e.g. published yesterday evening within 24h)
        if 0 <= age_hours <= max_age_hours:
            return True, f"Approved: Published within {int(age_hours)}h window ({pub_dt.strftime('%Y-%m-%d %H:%M')})"

        # If publication date is in the future (some official circulars post tomorrow's gazette date)
        if pub_dt.date() > today_ist:
            return True, f"Approved: Upcoming circular date ({pub_dt.date()})"

        # If publication date is strictly in the past (> 24 hours ago)
        # Check if text contains an upcoming deadline or schedule date in future
        text_dates = extract_dates_from_text(combined_text)
        upcoming_dates = [d for d in text_dates if d.date() >= today_ist]
        if upcoming_dates:
            # Only allow if publication is relatively recent (within 72h max for upcoming deadline)
            if age_hours <= 72.0:
                return True, f"Approved: Contains upcoming event date ({upcoming_dates[0].date()})"
            return False, f"Rejection: Notice published too long ago ({pub_dt.date()}) despite future event"

        return False, f"Rejection: Published on past date ({pub_dt.date()}), older than {max_age_hours}h"

    # 4. If notice_date is None or cannot be parsed (e.g. undated portal scrape)
    # Check if text contains TODAY's date or an UPCOMING date
    text_dates = extract_dates_from_text(combined_text)
    if text_dates:
        for td in text_dates:
            if td.date() == today_ist:
                return True, f"Approved: Text explicitly mentions today's date ({today_ist})"
            if td.date() > today_ist:
                return True, f"Approved: Text announces upcoming date ({td.date()})"

        # If all detected dates in text are in the past
        past_dates = [d for d in text_dates if d.date() < today_ist]
        if past_dates:
            return False, f"Rejection: Only past dates found in text ({past_dates[0].date()})"

    # If NO date could be found anywhere:
    # STRICT RULE: We do NOT post undated archive items. Reject to prevent old notices from slipping in.
    return False, "Rejection: No valid today or upcoming date found (undated portal item)"
