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

    conn.commit()
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

# Auto-initialize tables
init_db()
