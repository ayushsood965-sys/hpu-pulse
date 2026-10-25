import sqlite3
import hashlib
import json
from datetime import datetime
from typing import List, Dict, Optional, Any
from .config import DB_PATH
from .freshness import is_item_fresh

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Scraped items table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scraped_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_hash TEXT UNIQUE NOT NULL,
            source TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            pdf_url TEXT,
            ocr_text TEXT,
            summary TEXT,
            category TEXT NOT NULL,
            priority TEXT NOT NULL,
            official_ref_no TEXT,
            notice_date TEXT,
            status TEXT DEFAULT 'PENDING',
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 2. Published posts history
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS published_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_type TEXT NOT NULL,
            tier TEXT NOT NULL,
            category TEXT NOT NULL,
            headline TEXT NOT NULL,
            caption TEXT NOT NULL,
            media_urls_json TEXT NOT NULL,
            instagram_media_id TEXT,
            audio_track TEXT,
            scraped_item_ids_json TEXT,
            published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 3. Batch queue for Tier 2 routine carousels
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS batch_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scraped_item_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            enqueued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'WAITING',
            FOREIGN KEY(scraped_item_id) REFERENCES scraped_items(id)
        )
    """)

    # 4. Comments auto-responder & replies
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS comment_replies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            comment_id TEXT UNIQUE NOT NULL,
            post_id TEXT NOT NULL,
            username TEXT,
            comment_text TEXT,
            reply_text TEXT,
            replied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 5. Curated Instagram Reels Queue & Published Records
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS curated_reels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            instagram_url TEXT UNIQUE NOT NULL,
            shortcode TEXT UNIQUE NOT NULL,
            uploader_handle TEXT NOT NULL,
            caption TEXT,
            view_count INTEGER DEFAULT 0,
            like_count INTEGER DEFAULT 0,
            comment_count INTEGER DEFAULT 0,
            upload_date TEXT,
            video_url TEXT,
            local_video_path TEXT,
            thumbnail_url TEXT,
            status TEXT DEFAULT 'PENDING',
            target_post_date TEXT,
            instagram_media_id TEXT,
            discovery_source TEXT DEFAULT 'TARGET_CHANNEL',
            enqueued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            published_at TIMESTAMP
        )
    """)

    # Migration: Ensure discovery_source column exists in curated_reels
    try:
        cursor.execute("ALTER TABLE curated_reels ADD COLUMN discovery_source TEXT DEFAULT 'TARGET_CHANNEL'")
    except Exception:
        pass

    # 6. Monitored Instagram Channels Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS monitored_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            handle TEXT UNIQUE NOT NULL,
            category TEXT DEFAULT 'Target HPU Channel',
            notes TEXT DEFAULT '',
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    # Seed default handles if table is empty
    cursor.execute("SELECT count(*) FROM monitored_channels")
    if cursor.fetchone()[0] == 0:
        try:
            from .config import TARGET_REEL_HANDLES
            for h in TARGET_REEL_HANDLES:
                clean_h = h.strip().lstrip("@")
                if clean_h:
                    cursor.execute(
                        "INSERT OR IGNORE INTO monitored_channels (handle, category, notes) VALUES (?, ?, ?)",
                        (clean_h, "Campus News & Alerts", "Default target channel")
                    )
            conn.commit()
        except Exception as e:
            print(f"Warning seeding default monitored channels: {e}")

    conn.close()

def compute_hash(content_string: str) -> str:
    """Computes a unique SHA-256 fingerprint for deduplication."""
    return hashlib.sha256(content_string.strip().lower().encode("utf-8")).hexdigest()

def is_content_seen(content_hash: str) -> bool:
    """Checks if a content hash has already been stored."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM scraped_items WHERE content_hash = ?", (content_hash,))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def is_url_seen(url: str) -> bool:
    """Checks if a specific URL has already been processed."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM scraped_items WHERE url = ?", (url.strip(),))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def save_scraped_item(item: Dict[str, Any]) -> Optional[int]:
    """
    Inserts a newly crawled item. If it's Tier 2 routine news, also enqueues it for batching.
    Returns the new item ID, or None if already exists.
    """
    content_hash = item.get("content_hash") or compute_hash(f"{item.get('url')}_{item.get('title')}")
    if is_content_seen(content_hash):
        return None

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO scraped_items (
                content_hash, source, title, url, pdf_url, ocr_text,
                summary, category, priority, official_ref_no, notice_date, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            content_hash,
            item.get("source", "portal"),
            item.get("title", ""),
            item.get("url", ""),
            item.get("pdf_url"),
            item.get("ocr_text"),
            item.get("summary", ""),
            item.get("category", "GENERAL"),
            item.get("priority", "TIER2_ROUTINE"),
            item.get("official_ref_no"),
            item.get("notice_date"),
            "PENDING"
        ))
        item_id = cursor.lastrowid

        # If routine, add to batch queue
        if item.get("priority") == "TIER2_ROUTINE":
            cursor.execute("""
                INSERT INTO batch_queue (scraped_item_id, category, status)
                VALUES (?, ?, 'WAITING')
            """, (item_id, item.get("category", "GENERAL")))

        conn.commit()
        return item_id
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def get_pending_tier1_items() -> List[Dict[str, Any]]:
    """
    Returns all unposted Tier 1 breaking news items, prioritized by source:
    1. Instagram Competitor Pages (@hpuupdate, @hpudailyupdates, etc.)
    2. Regional Newspapers (Amar Ujala, Divya Himachal, The Tribune)
    3. Official University Portals (nexams, nadmissions, hpuniv)

    STRICT FRESHNESS: Stale items older than today/24h are marked EXPIRED_STALE and dropped.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM scraped_items 
        WHERE priority = 'TIER1_BREAKING' AND status = 'PENDING'
        ORDER BY 
            CASE 
                WHEN source LIKE 'Instagram%' THEN 1
                WHEN source LIKE '%News%' OR source LIKE '%Amar Ujala%' OR source LIKE '%Divya Himachal%' OR source LIKE '%Tribune%' THEN 2
                ELSE 3
            END ASC,
            scraped_at DESC
    """)
    rows = [dict(r) for r in cursor.fetchall()]

    fresh_items = []
    stale_ids = []
    for r in rows:
        fresh, reason = is_item_fresh(r)
        if fresh:
            fresh_items.append(r)
        else:
            stale_ids.append(r["id"])

    if stale_ids:
        placeholders = ",".join("?" for _ in stale_ids)
        cursor.execute(f"UPDATE scraped_items SET status = 'EXPIRED_STALE' WHERE id IN ({placeholders})", stale_ids)
        conn.commit()

    conn.close()
    return fresh_items

def get_waiting_batch_items(category: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Returns waiting items from the batch queue, prioritized by source:
    1. Instagram Competitor Pages
    2. Regional Newspapers
    3. Official University Portals

    STRICT FRESHNESS: Stale items older than today/24h are marked EXPIRED_STALE and dropped.
    """
    conn = get_connection()
    cursor = conn.cursor()
    if category:
        cursor.execute("""
            SELECT s.*, b.id as queue_id FROM batch_queue b
            JOIN scraped_items s ON b.scraped_item_id = s.id
            WHERE b.status = 'WAITING' AND b.category = ?
            ORDER BY 
                CASE 
                    WHEN s.source LIKE 'Instagram%' THEN 1
                    WHEN s.source LIKE '%News%' OR s.source LIKE '%Amar Ujala%' OR s.source LIKE '%Divya Himachal%' OR s.source LIKE '%Tribune%' THEN 2
                    ELSE 3
                END ASC,
                b.enqueued_at DESC
        """, (category,))
    else:
        cursor.execute("""
            SELECT s.*, b.id as queue_id FROM batch_queue b
            JOIN scraped_items s ON b.scraped_item_id = s.id
            WHERE b.status = 'WAITING'
            ORDER BY 
                CASE 
                    WHEN s.source LIKE 'Instagram%' THEN 1
                    WHEN s.source LIKE '%News%' OR s.source LIKE '%Amar Ujala%' OR s.source LIKE '%Divya Himachal%' OR s.source LIKE '%Tribune%' THEN 2
                    ELSE 3
                END ASC,
                b.enqueued_at DESC
        """)
    rows = [dict(r) for r in cursor.fetchall()]

    fresh_items = []
    stale_item_ids = []
    stale_queue_ids = []
    for r in rows:
        fresh, reason = is_item_fresh(r)
        if fresh:
            fresh_items.append(r)
        else:
            stale_item_ids.append(r["id"])
            if r.get("queue_id"):
                stale_queue_ids.append(r["queue_id"])

    if stale_item_ids:
        placeholders = ",".join("?" for _ in stale_item_ids)
        cursor.execute(f"UPDATE scraped_items SET status = 'EXPIRED_STALE' WHERE id IN ({placeholders})", stale_item_ids)
    if stale_queue_ids:
        placeholders = ",".join("?" for _ in stale_queue_ids)
        cursor.execute(f"UPDATE batch_queue SET status = 'EXPIRED_STALE' WHERE id IN ({placeholders})", stale_queue_ids)
    if stale_item_ids or stale_queue_ids:
        conn.commit()

    conn.close()
    return fresh_items

def purge_stale_pending_items() -> int:
    """Purges all existing pending/waiting items that are older than today."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM scraped_items WHERE status = 'PENDING'")
    pending = [dict(r) for r in cursor.fetchall()]
    purged_count = 0
    stale_ids = []
    for item in pending:
        fresh, reason = is_item_fresh(item)
        if not fresh:
            stale_ids.append(item["id"])
            purged_count += 1

    if stale_ids:
        placeholders = ",".join("?" for _ in stale_ids)
        cursor.execute(f"UPDATE scraped_items SET status = 'EXPIRED_STALE' WHERE id IN ({placeholders})", stale_ids)
        cursor.execute(f"UPDATE batch_queue SET status = 'EXPIRED_STALE' WHERE scraped_item_id IN ({placeholders})", stale_ids)
        conn.commit()

    conn.close()
    return purged_count

def mark_items_published(item_ids: List[int]):
    """Marks scraped items and batch queue items as PUBLISHED."""
    if not item_ids:
        return
    conn = get_connection()
    cursor = conn.cursor()
    placeholders = ",".join("?" for _ in item_ids)
    cursor.execute(f"UPDATE scraped_items SET status = 'PUBLISHED' WHERE id IN ({placeholders})", item_ids)
    cursor.execute(f"UPDATE batch_queue SET status = 'PUBLISHED' WHERE scraped_item_id IN ({placeholders})", item_ids)
    conn.commit()
    conn.close()

def record_published_post(
    post_type: str,
    tier: str,
    category: str,
    headline: str,
    caption: str,
    media_urls: List[str],
    instagram_media_id: str,
    audio_track: Optional[str] = None,
    scraped_item_ids: Optional[List[int]] = None
) -> int:
    """Stores a successful Instagram post in history."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO published_posts (
            post_type, tier, category, headline, caption,
            media_urls_json, instagram_media_id, audio_track, scraped_item_ids_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        post_type,
        tier,
        category,
        headline,
        caption,
        json.dumps(media_urls),
        instagram_media_id,
        audio_track,
        json.dumps(scraped_item_ids or [])
    ))
    post_id = cursor.lastrowid
    conn.commit()
    conn.close()

    if scraped_item_ids:
        mark_items_published(scraped_item_ids)

    return post_id

def get_recent_posts(limit: int = 15) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM published_posts ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def is_comment_replied(comment_id: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM comment_replies WHERE comment_id = ?", (comment_id,))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def record_comment_reply(comment_id: str, post_id: str, username: str, comment_text: str, reply_text: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO comment_replies (comment_id, post_id, username, comment_text, reply_text)
        VALUES (?, ?, ?, ?, ?)
    """, (comment_id, post_id, username, comment_text, reply_text))
    conn.commit()
    conn.close()

def get_daily_published_count() -> int:
    """Returns the number of posts published today (calendar day in Asia/Kolkata)."""
    conn = get_connection()
    cursor = conn.cursor()
    today_str = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("""
        SELECT count(*) FROM published_posts 
        WHERE published_at LIKE ? OR date(published_at) = date('now')
    """, (f"{today_str}%",))
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_all_waiting_items() -> List[Dict[str, Any]]:
    """Returns all fresh waiting circulars/updates ordered by priority and freshness."""
    p1 = get_pending_tier1_items()
    p2 = get_waiting_batch_items()
    seen_ids = set()
    combined = []
    for item in p1 + p2:
        if item["id"] not in seen_ids:
            seen_ids.add(item["id"])
            combined.append(item)
    return combined

# =========================================================================
# Curated Reels Helper Functions (Quota, Dedup, Rollover Queue)
# =========================================================================

def is_curated_reel_seen(shortcode: str) -> bool:
    """Checks if a reel shortcode has already been recorded in curated_reels."""
    if not shortcode:
        return False
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM curated_reels WHERE shortcode = ? OR instagram_url LIKE ?", (shortcode, f"%{shortcode}%"))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def save_curated_reel(data: Dict[str, Any]) -> Optional[int]:
    """Saves a qualified curated reel into the queue."""
    shortcode = data.get("shortcode", "")
    if is_curated_reel_seen(shortcode):
        return None
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO curated_reels (
                instagram_url, shortcode, uploader_handle, caption,
                view_count, like_count, comment_count, upload_date,
                video_url, local_video_path, thumbnail_url, status,
                target_post_date, discovery_source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("instagram_url", ""),
            shortcode,
            data.get("uploader_handle", "").lstrip("@"),
            data.get("caption", ""),
            data.get("view_count", 0),
            data.get("like_count", 0),
            data.get("comment_count", 0),
            data.get("upload_date", ""),
            data.get("video_url", ""),
            data.get("local_video_path", ""),
            data.get("thumbnail_url", ""),
            data.get("status", "PENDING"),
            data.get("target_post_date", datetime.now().strftime("%Y-%m-%d")),
            data.get("discovery_source", "TARGET_CHANNEL")
        ))
        reel_id = cursor.lastrowid
        conn.commit()
        return reel_id
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def get_daily_curated_reels_count(target_date: Optional[str] = None) -> int:
    """Returns number of curated reels posted on target_date (default: today)."""
    conn = get_connection()
    cursor = conn.cursor()
    d_str = target_date or datetime.now().strftime("%Y-%m-%d")
    cursor.execute("""
        SELECT count(*) FROM curated_reels
        WHERE status = 'PUBLISHED' AND (published_at LIKE ? OR date(published_at) = ?)
    """, (f"{d_str}%", d_str))
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_pending_curated_reels(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Returns pending/queued curated reels ordered by target post date and ID."""
    conn = get_connection()
    cursor = conn.cursor()
    query = """
        SELECT * FROM curated_reels
        WHERE status IN ('PENDING', 'QUEUED_FOR_NEXT_DAY')
        ORDER BY target_post_date ASC, id ASC
    """
    if limit:
        query += f" LIMIT {int(limit)}"
    cursor.execute(query)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_published_curated_reels(limit: int = 50) -> List[Dict[str, Any]]:
    """Returns list of curated reels that were published to Instagram."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM curated_reels
        WHERE status = 'PUBLISHED'
        ORDER BY published_at DESC LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def mark_curated_reel_published(reel_id: int, instagram_media_id: str):
    """Marks a curated reel as PUBLISHED with media ID and timestamp."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE curated_reels
        SET status = 'PUBLISHED', instagram_media_id = ?, published_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (instagram_media_id, reel_id))
    conn.commit()
    conn.close()

def update_curated_reel_status(reel_id: int, status: str, target_post_date: Optional[str] = None):
    conn = get_connection()
    cursor = conn.cursor()
    if target_post_date:
        cursor.execute("UPDATE curated_reels SET status = ?, target_post_date = ? WHERE id = ?", (status, target_post_date, reel_id))
    else:
        cursor.execute("UPDATE curated_reels SET status = ? WHERE id = ?", (status, reel_id))
    conn.commit()
    conn.close()

def skip_curated_reel(reel_id: int):
    update_curated_reel_status(reel_id, 'SKIPPED')

def get_curated_reel_by_id(reel_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM curated_reels WHERE id = ?", (reel_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_discovered_user_reels(limit: int = 100) -> List[Dict[str, Any]]:
    """Returns public user reels discovered from hashtags/mentions waiting for manual user review."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM curated_reels
        WHERE status = 'DISCOVERED_PENDING_REVIEW'
        ORDER BY view_count DESC, id DESC
        LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def dismiss_discovered_reel(reel_id: int) -> bool:
    """Dismisses a discovered user reel from the review queue."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE curated_reels SET status = 'DISMISSED' WHERE id = ?", (reel_id,))
    conn.commit()
    rowcount = cursor.rowcount
    conn.close()
    return rowcount > 0

def dismiss_all_discovered_reels() -> int:
    """Dismisses all currently waiting discovered user reels."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE curated_reels SET status = 'DISMISSED' WHERE status = 'DISCOVERED_PENDING_REVIEW'")
    conn.commit()
    count = cursor.rowcount
    conn.close()
    return count

# =========================================================================
# Daily 7:00 PM News Carousel Helper Functions
# =========================================================================

def get_today_queued_news_count() -> int:
    """Returns count of news items queued for today's 7 PM carousel."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM batch_queue WHERE status = 'WAITING'")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_today_queued_news_items(limit: int = 10) -> List[Dict[str, Any]]:
    """Returns waiting items for today's single 7 PM news carousel."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.*, b.id as queue_id FROM batch_queue b
        JOIN scraped_items s ON b.scraped_item_id = s.id
        WHERE b.status = 'WAITING'
        ORDER BY 
            CASE 
                WHEN s.priority = 'TIER1_BREAKING' THEN 1
                ELSE 2
            END ASC,
            s.scraped_at DESC
        LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_daily_news_carousel_published_today() -> bool:
    """Checks if a routine news carousel has already been published today."""
    conn = get_connection()
    cursor = conn.cursor()
    today_str = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("""
        SELECT id FROM published_posts
        WHERE post_type = 'CAROUSEL' AND (published_at LIKE ? OR date(published_at) = ?)
    """, (f"{today_str}%", today_str))
    row = cursor.fetchone()
    conn.close()
    return row is not None

# =========================================================================
# Monitored Channels CRUD Helper Functions
# =========================================================================

def get_monitored_channels() -> List[Dict[str, Any]]:
    """Returns list of all monitored Instagram channels."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, handle, category, notes, added_at FROM monitored_channels ORDER BY id ASC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def add_monitored_channel(handle: str, category: str = "Target HPU Channel", notes: str = "") -> bool:
    """Adds a new channel to the monitored channels table."""
    clean_h = handle.strip().lstrip("@")
    if not clean_h:
        return False
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO monitored_channels (handle, category, notes) VALUES (?, ?, ?)",
            (clean_h, category or "Target HPU Channel", notes or "")
        )
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    finally:
        conn.close()
    return success

def update_monitored_channel(channel_id: int, handle: str, category: str = "", notes: str = "") -> bool:
    """Updates an existing monitored channel."""
    clean_h = handle.strip().lstrip("@")
    if not clean_h:
        return False
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE monitored_channels SET handle = ?, category = ?, notes = ? WHERE id = ?",
            (clean_h, category or "Target HPU Channel", notes or "", channel_id)
        )
        conn.commit()
        success = cursor.rowcount > 0
    except Exception:
        success = False
    finally:
        conn.close()
    return success

def delete_monitored_channel(channel_id_or_handle: Any) -> bool:
    """Deletes a channel from the monitored channels table by ID or handle."""
    conn = get_connection()
    cursor = conn.cursor()
    clean_val = str(channel_id_or_handle).strip().lstrip("@")
    try:
        if str(channel_id_or_handle).isdigit():
            cursor.execute("DELETE FROM monitored_channels WHERE id = ? OR handle = ?", (int(channel_id_or_handle), clean_val))
        else:
            cursor.execute("DELETE FROM monitored_channels WHERE handle = ?", (clean_val,))
        conn.commit()
        success = cursor.rowcount > 0
    except Exception:
        success = False
    finally:
        conn.close()
    return success

# Auto-initialize tables
init_db()
