import os
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import requests
import yt_dlp
from googlenewsdecoder import gnewsdecoder

from .config import (
    CURATED_REELS_DIR,
    MAX_DAILY_REEL_UPLOADS,
    REELS_LOOKBACK_DAYS,
    REELS_DATE_CUTOFF,
    TARGET_REEL_HANDLES,
    SERVER_URL,
    INSTAGRAM_ACCESS_TOKEN,
    INSTAGRAM_ACCOUNT_ID
)
from .db import (
    is_curated_reel_seen,
    is_reel_already_published,
    is_video_hash_published,
    claim_reel_for_publishing,
    update_curated_reel_video_hash,
    normalize_reel_shortcode,
    save_curated_reel,
    get_daily_curated_reels_count,
    get_pending_curated_reels,
    get_discovered_user_reels,
    get_curated_reel_by_id,
    dismiss_discovered_reel,
    dismiss_all_discovered_reels,
    mark_curated_reel_published,
    update_curated_reel_status,
    record_published_post,
    get_monitored_channels,
    get_connection
)
from .poster import publish_reel_to_instagram
from .uploader import upload_video
import hashlib

REEL_SHORTCODE_REGEX = re.compile(r"instagram\.com/(?:reel|p|reels)/([A-Za-z0-9_-]+)", re.IGNORECASE)

def compute_file_sha256(file_path: str) -> str:
    """Computes SHA-256 hash of a local video file for bulletproof content deduplication."""
    if not file_path or not Path(file_path).exists():
        return ""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

def extract_reel_shortcode(url: str) -> Optional[str]:
    """Extracts and normalizes the Instagram shortcode from any post or reel URL."""
    if not url:
        return None
    clean = re.sub(r"\?.*$", "", str(url).strip())
    match = REEL_SHORTCODE_REGEX.search(clean)
    if match:
        return match.group(1).strip()
    return None


def clean_handle(handle: str) -> str:
    """Removes leading @ and trims handle."""
    return (handle or "").strip().lstrip("@")

def get_active_target_handles() -> List[str]:
    """Retrieves dynamic monitored channels from the database, falling back to config defaults."""
    try:
        channels = get_monitored_channels()
        if channels:
            return [c["handle"].strip().lstrip("@") for c in channels if c.get("handle")]
    except Exception as e:
        print(f"[ReelsCurator] Warning reading target handles from DB: {e}")
    return TARGET_REEL_HANDLES

def get_rolling_date_cutoff(days: int = REELS_LOOKBACK_DAYS) -> Tuple[date, str]:
    """
    Returns (cutoff_date_obj, 'YYYYMMDD') representing the lookback threshold.
    Reels uploaded on or after this date qualify for engagement evaluation.
    """
    cutoff_date = date.today() - timedelta(days=days)
    return cutoff_date, cutoff_date.strftime("%Y%m%d")

def parse_date_cutoff() -> str:
    """Returns YYYYMMDD string for date cutoff based on rolling lookback window."""
    _, cutoff_str = get_rolling_date_cutoff()
    return cutoff_str

def fetch_reel_metadata_and_download(
    url: str,
    download: bool = False
) -> Optional[Dict[str, Any]]:
    """
    Uses yt-dlp to inspect or download a public Instagram Reel.
    Returns metadata dictionary or None if extraction fails.
    """
    shortcode = extract_reel_shortcode(url) or "reel"
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "format": "b[ext=mp4]/best[ext=mp4]/best",
        "outtmpl": str(CURATED_REELS_DIR / f"{shortcode}.%(ext)s"),
        "socket_timeout": 20
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=download)
            if not info:
                return None

            upload_date = info.get("upload_date") or ""
            timestamp = info.get("timestamp")
            if not upload_date and timestamp:
                upload_date = datetime.fromtimestamp(timestamp).strftime("%Y%m%d")

            uploader = info.get("channel") or info.get("uploader") or info.get("uploader_id") or ""
            uploader = clean_handle(uploader)

            view_count = info.get("view_count") or 0
            like_count = info.get("like_count") or 0
            comment_count = info.get("comment_count") or 0

            local_path = None
            if download:
                CURATED_REELS_DIR.mkdir(parents=True, exist_ok=True)
                expected_path = CURATED_REELS_DIR / f"{shortcode}.mp4"
                if expected_path.exists() and expected_path.stat().st_size > 10000:
                    local_path = str(expected_path)
                else:
                    for f in CURATED_REELS_DIR.glob(f"{shortcode}.*"):
                        if f.is_file() and f.stat().st_size > 10000:
                            local_path = str(f)
                            break

                # Fallback: direct CDN stream download if yt-dlp file is missing
                if not local_path or not Path(local_path).exists() or Path(local_path).stat().st_size == 0:
                    cdn_url = info.get("url")
                    if cdn_url:
                        print(f"  [ReelsCurator] Downloading direct CDN video stream to {expected_path.name}...")
                        try:
                            r = requests.get(cdn_url, stream=True, timeout=30)
                            if r.status_code == 200:
                                with open(expected_path, "wb") as f_out:
                                    for chunk in r.iter_content(chunk_size=1024*1024):
                                        if chunk:
                                            f_out.write(chunk)
                                local_path = str(expected_path)
                                print(f"  [ReelsCurator] Direct download complete ({Path(local_path).stat().st_size} bytes).")
                        except Exception as e_cdn:
                            print(f"  [ReelsCurator] Direct CDN download failed: {e_cdn}")

            return {
                "instagram_url": f"https://www.instagram.com/reel/{shortcode}/",
                "shortcode": shortcode,
                "uploader_handle": uploader,
                "caption": info.get("description") or info.get("title") or "",
                "view_count": int(view_count) if view_count else 0,
                "like_count": int(like_count) if like_count else 0,
                "comment_count": int(comment_count) if comment_count else 0,
                "upload_date": upload_date,
                "timestamp": timestamp,
                "thumbnail_url": info.get("thumbnail"),
                "local_video_path": local_path,
                "video_url": info.get("url")
            }
    except Exception as e:
        print(f"[ReelsCurator] yt-dlp error for {url}: {e}")
        # In case yt-dlp download failed, attempt flat extraction + direct stream download
        if download:
            try:
                CURATED_REELS_DIR.mkdir(parents=True, exist_ok=True)
                expected_path = CURATED_REELS_DIR / f"{shortcode}.mp4"
                with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl2:
                    info2 = ydl2.extract_info(url, download=False)
                    cdn_url = info2.get("url") if info2 else None
                    if cdn_url:
                        print(f"  [ReelsCurator] Recovering via direct CDN stream...")
                        r = requests.get(cdn_url, stream=True, timeout=30)
                        if r.status_code == 200:
                            with open(expected_path, "wb") as f_out:
                                for chunk in r.iter_content(chunk_size=1024*1024):
                                    if chunk:
                                        f_out.write(chunk)
                            uploader2 = clean_handle(info2.get("channel") or info2.get("uploader") or info2.get("uploader_id") or "")
                            return {
                                "instagram_url": f"https://www.instagram.com/reel/{shortcode}/",
                                "shortcode": shortcode,
                                "uploader_handle": uploader2,
                                "caption": info2.get("description") or info2.get("title") or "",
                                "view_count": int(info2.get("view_count") or 0),
                                "like_count": int(info2.get("like_count") or 0),
                                "comment_count": int(info2.get("comment_count") or 0),
                                "upload_date": info2.get("upload_date") or "",
                                "timestamp": info2.get("timestamp"),
                                "thumbnail_url": info2.get("thumbnail"),
                                "local_video_path": str(expected_path),
                                "video_url": cdn_url
                            }
            except Exception as e2:
                print(f"[ReelsCurator] Recovery download failed: {e2}")
        return None

def is_reel_qualified(meta: Dict[str, Any], lookback_days: int = REELS_LOOKBACK_DAYS) -> Tuple[bool, str]:
    """
    Enforces filtering rules:
    1. Uploaded within the past `lookback_days` days (default 3-day rolling window).
    2. Engagement: Views >= 1000 OR Likes >= 200 OR Comments >= 100.
    """
    _, cutoff_str = get_rolling_date_cutoff(lookback_days)
    upload_date = meta.get("upload_date") or ""

    if upload_date and upload_date < cutoff_str:
        return False, f"Uploaded on {upload_date}, older than rolling {lookback_days}-day window (cutoff: {cutoff_str})"

    views = int(meta.get("view_count") or 0)
    likes = int(meta.get("like_count") or 0)
    comments = int(meta.get("comment_count") or 0)

    has_views = views >= 1000
    has_likes = likes >= 200
    has_comments = comments >= 100

    if has_views or has_likes or has_comments:
        return True, f"Qualified (Views: {views}, Likes: {likes}, Comments: {comments})"

    return False, f"Below thresholds (Views: {views}<1000, Likes: {likes}<200, Comments: {comments}<100)"

def scan_target_handles_for_reels(force_for_test: bool = False, lookback_days: int = REELS_LOOKBACK_DAYS) -> List[Dict[str, Any]]:
    """
    Monitors all Category 1 to 4 target handles and general HPU keywords for newly published reels.
    Identifies eligible reels within the past `lookback_days` days, applies cutoff & thresholds, and enqueues them.
    """
    active_handles = get_active_target_handles()
    targets = [(h, f'site:instagram.com/reel "{h}"') for h in active_handles]
    targets += [
        ("hpu", 'site:instagram.com/reel "hpu"'),
        ("himachal_pradesh_university", 'site:instagram.com/reel "himachal pradesh university"'),
        ("hpushimla", 'site:instagram.com/reel "hpushimla"')
    ]
    cutoff_date, cutoff_str = get_rolling_date_cutoff(lookback_days)
    print(f"\n[ReelsCurator] 🔍 Starting scan across {len(targets)} HPU search targets (rolling {lookback_days}-day window from {cutoff_str})...")
    discovered = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    today_str = datetime.now().strftime("%Y-%m-%d")
    tomorrow_str = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")

    for handle, query_text in targets:
        try:
            query = urllib.parse.quote(query_text)
            rss_url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
            res = requests.get(rss_url, headers=headers, timeout=10)
            if res.status_code != 200:
                continue

            root = ET.fromstring(res.content)
            items = root.findall(".//item")[:8]

            for item in items:
                pub_date_str = item.find("pubDate").text if item.find("pubDate") is not None else ""
                article_url = item.find("link").text if item.find("link") is not None else ""

                if not article_url:
                    continue

                # Quick date check: if item pubDate is older than rolling cutoff date, skip
                if pub_date_str:
                    try:
                        parsed_dt = datetime.strptime(pub_date_str[:16], "%a, %d %b %Y")
                        if parsed_dt.date() < cutoff_date:
                            continue
                    except Exception:
                        pass

                # Resolve Google News redirect to direct Instagram URL
                decoded = gnewsdecoder(article_url)
                if not decoded or not decoded.get("success"):
                    continue

                direct_url = decoded.get("decoded_url")
                shortcode = normalize_reel_shortcode(extract_reel_shortcode(direct_url))
                if not shortcode or is_curated_reel_seen(shortcode, direct_url) or is_reel_already_published(shortcode, direct_url):
                    continue


                # Inspect reel metadata via yt-dlp
                meta = fetch_reel_metadata_and_download(direct_url, download=False)
                if not meta:
                    continue

                # If uploader not extracted from video, use the target handle
                if not meta.get("uploader_handle"):
                    meta["uploader_handle"] = handle

                qualified, reason = is_reel_qualified(meta, lookback_days=lookback_days)
                print(f"  [ReelsCurator] Reel {shortcode} (@{meta['uploader_handle']}): {reason}")
                if not qualified and not force_for_test:
                    continue

                # Quota calculation: if today's uploads already reached 15, schedule for tomorrow
                today_count = get_daily_curated_reels_count(today_str)
                if today_count >= MAX_DAILY_REEL_UPLOADS:
                    meta["status"] = "QUEUED_FOR_NEXT_DAY"
                    meta["target_post_date"] = tomorrow_str
                else:
                    meta["status"] = "PENDING"
                    meta["target_post_date"] = today_str

                reel_id = save_curated_reel(meta)
                if reel_id:
                    meta["id"] = reel_id
                    discovered.append(meta)
                    print(f"  ✅ [ReelsCurator] Successfully enqueued reel #{reel_id} ({shortcode}) with status {meta['status']}")

        except Exception as e:
            print(f"[ReelsCurator] Error scanning handle @{handle}: {e}")

    print(f"[ReelsCurator] 🏁 Scan completed. Discovered & enqueued {len(discovered)} new eligible reels.\n")
    return discovered

def generate_curation_caption(meta: Dict[str, Any]) -> str:
    """Creates a respectful, compliant attribution caption for the curated reel."""
    handle = meta.get("uploader_handle") or "hpu_student"
    orig_caption = meta.get("caption") or ""

    clean_desc = re.sub(r"#[A-Za-z0-9_]+", "", orig_caption).strip()
    clean_desc = re.sub(r"\s+", " ", clean_desc)
    if len(clean_desc) > 350:
        clean_desc = clean_desc[:347] + "..."

    caption = (
        f"🎥 Video Via: @{handle}\n"
        f"🏛 Himachal Pradesh University (#HPUShimla)\n\n"
        f"{clean_desc}\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📢 Shared for student awareness, campus updates & student community.\n"
        f"All copyrights belong to original creator @{handle}.\n\n"
        f"#HPU #HPUShimla #HimachalPradeshUniversity #SummerHill #Shimla #HPUUpdates #HPUReels"
    )
    return caption

def publish_curated_reel_record(reel_record: Dict[str, Any], dry_run: bool = False) -> bool:
    """
    Downloads the MP4 file (if needed), verifies binary SHA-256 content uniqueness,
    hosts it on SERVER_URL, and publishes the reel to @hpu.pulse via Meta Graph API.
    Guarantees no reel is EVER uploaded or posted twice.
    """
    reel_id = reel_record.get("id")
    url = reel_record.get("instagram_url")
    shortcode = normalize_reel_shortcode(reel_record.get("shortcode") or extract_reel_shortcode(url))
    handle = reel_record.get("uploader_handle") or "creator"

    # Step 0: Check if this reel is already published
    if is_reel_already_published(shortcode, url):
        print(f"[ReelsCurator] 🛑 DUPLICATE BLOCKED: Reel ({shortcode}) has ALREADY been published to Instagram! Skipping.")
        if reel_id:
            update_curated_reel_status(reel_id, "PUBLISHED")
        return False

    # Step 0b: Atomic concurrency lock (guarantees only 1 worker publishes this reel)
    if reel_id:
        if not claim_reel_for_publishing(reel_id):
            print(f"[ReelsCurator] ⚠️ Reel #{reel_id} ({shortcode}) is already locked in PUBLISHING state by another task. Skipping.")
            return False

    today_str = datetime.now().strftime("%Y-%m-%d")
    today_count = get_daily_curated_reels_count(today_str)

    if today_count >= MAX_DAILY_REEL_UPLOADS:
        tomorrow_str = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        print(f"[ReelsCurator] 🛑 Daily quota reached ({today_count}/{MAX_DAILY_REEL_UPLOADS}). Moving #{reel_id} to tomorrow ({tomorrow_str}).")
        if reel_id:
            update_curated_reel_status(reel_id, "QUEUED_FOR_NEXT_DAY", target_post_date=tomorrow_str)
        return False

    print(f"\n[ReelsCurator] 🚀 Publishing Curated Reel #{reel_id} ({shortcode}) from @{handle}...")

    # 1. Ensure MP4 is downloaded locally
    local_path = reel_record.get("local_video_path")
    if not local_path or not Path(local_path).exists():
        print(f"  📥 Downloading high-res MP4 via yt-dlp...")
        download_meta = fetch_reel_metadata_and_download(url, download=True)
        if not download_meta or not download_meta.get("local_video_path"):
            print(f"  ❌ Failed to download video for {url}")
            if reel_id:
                update_curated_reel_status(reel_id, "FAILED")
            return False
        local_path = download_meta["local_video_path"]

    # 1b. Compute and verify binary SHA-256 hash of the video file
    video_hash = compute_file_sha256(local_path)
    if video_hash:
        if is_video_hash_published(video_hash):
            print(f"[ReelsCurator] 🛑 DUPLICATE BLOCKED: Video binary SHA-256 hash ({video_hash[:12]}...) was ALREADY published to Instagram! Deleting file and aborting.")
            try:
                if local_path and Path(local_path).exists():
                    os.remove(local_path)
            except Exception:
                pass
            if reel_id:
                update_curated_reel_status(reel_id, "DUPLICATE_VIDEO_HASH")
            return False

        if reel_id:
            update_curated_reel_video_hash(reel_id, video_hash)

    # 2. Form publicly accessible URL
    video_filename = Path(local_path).name
    public_video_url = f"{SERVER_URL}/generated_cards/curated_reels/{video_filename}"
    print(f"  🌐 Public Video URL: {public_video_url}")

    # 3. Generate Attribution Caption
    caption = generate_curation_caption(reel_record)

    # 4. Dry Run Check
    if dry_run:
        fake_id = f"dry_run_curated_{shortcode}"
        print(f"  [DRY RUN] Would publish reel to Instagram. Fake Media ID: {fake_id}")
        if reel_id:
            mark_curated_reel_published(reel_id, fake_id)
        record_published_post(
            post_type="REEL",
            tier="CURATED_REEL",
            category="CAMPUS_REELS",
            headline=f"Reel via @{handle} ({shortcode})",
            caption=caption,
            media_urls=[public_video_url],
            instagram_media_id=fake_id,
            video_hash=video_hash
        )
        try:
            if local_path and Path(local_path).exists():
                os.remove(local_path)
        except Exception:
            pass
        return True

    # 5. Meta Graph API Publishing
    try:
        media_id = publish_reel_to_instagram(
            video_url=public_video_url,
            caption=caption,
            audio_name="",
            is_emergency=True,
            is_manual=True
        )
    except Exception as e:
        print(f"  ❌ Meta Graph API publishing failed for reel #{reel_id}: {e}")
        media_id = None

    if media_id:
        print(f"  🎉 Successfully published reel on Instagram! Media ID: {media_id}")
        if reel_id:
            mark_curated_reel_published(reel_id, media_id)
        record_published_post(
            post_type="REEL",
            tier="CURATED_REEL",
            category="CAMPUS_REELS",
            headline=f"Reel via @{handle} ({shortcode})",
            caption=caption,
            media_urls=[public_video_url],
            instagram_media_id=media_id,
            video_hash=video_hash
        )
        # Auto-cleanup: remove local video file to maintain zero disk usage
        try:
            if local_path and Path(local_path).exists():
                os.remove(local_path)
                print(f"  🧹 Cleaned up local video file {video_filename} from server disk.")
        except Exception as e:
            print(f"  Cleanup note: {e}")
        return True
    else:
        print(f"  ❌ Meta Graph API publishing failed for reel #{reel_id}.")
        if reel_id:
            update_curated_reel_status(reel_id, "FAILED")
        try:
            if local_path and Path(local_path).exists():
                os.remove(local_path)
        except Exception:
            pass
        return False

def process_curated_reels_queue(dry_run: bool = False, max_to_post: int = 1) -> int:
    """
    Processes eligible reels from the queue respecting daily limit of 15.
    If today's quota is exhausted, shifts waiting items to QUEUED_FOR_NEXT_DAY.
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    tomorrow_str = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
    posted_today = get_daily_curated_reels_count(today_str)
    remaining_quota = max(0, MAX_DAILY_REEL_UPLOADS - posted_today)

    if remaining_quota <= 0:
        print(f"[ReelsCurator] ℹ️ Daily upload quota of {MAX_DAILY_REEL_UPLOADS} reached for today. Ensuring remaining items are marked for tomorrow.")
        pending = get_pending_curated_reels()
        for p in pending:
            if p.get("target_post_date") == today_str:
                update_curated_reel_status(p["id"], "QUEUED_FOR_NEXT_DAY", target_post_date=tomorrow_str)
        return 0

    pending = get_pending_curated_reels(limit=max_to_post)
    if not pending:
        return 0

    posted_count = 0
    for reel in pending:
        if posted_count >= remaining_quota:
            break
        # Guard against any duplicate reel that slipped past prior checks
        if is_reel_already_published(reel.get("shortcode"), reel.get("instagram_url")):
            print(f"[ReelsCurator] 🛑 Skipping reel #{reel['id']} ({reel.get('shortcode')}): Already marked as published.")
            update_curated_reel_status(reel["id"], "PUBLISHED")
            continue

        success = publish_curated_reel_record(reel, dry_run=dry_run)
        if success:
            posted_count += 1
            if posted_count < max_to_post and not dry_run:
                time.sleep(15)

    return posted_count

def manually_enqueue_reel(url: str, force: bool = False) -> Dict[str, Any]:
    """Allows manual link input from the dashboard."""
    shortcode = normalize_reel_shortcode(extract_reel_shortcode(url))
    if not shortcode:
        return {"success": False, "error": "Invalid Instagram Reel URL"}

    if (is_curated_reel_seen(shortcode, url) or is_reel_already_published(shortcode, url)) and not force:
        return {"success": False, "error": f"Reel ({shortcode}) has already been recorded or published in database"}

    meta = fetch_reel_metadata_and_download(url, download=False)
    if not meta:
        return {"success": False, "error": "Could not fetch metadata for this Reel"}

    if not force:
        qualified, reason = is_reel_qualified(meta)
        if not qualified:
            return {"success": False, "error": reason, "meta": meta}

    today_str = datetime.now().strftime("%Y-%m-%d")
    tomorrow_str = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
    today_count = get_daily_curated_reels_count(today_str)

    if today_count >= MAX_DAILY_REEL_UPLOADS:
        meta["status"] = "QUEUED_FOR_NEXT_DAY"
        meta["target_post_date"] = tomorrow_str
    else:
        meta["status"] = "PENDING"
        meta["target_post_date"] = today_str

    reel_id = save_curated_reel(meta)
    if not reel_id:
        return {"success": False, "error": "Database error saving reel"}

    meta["id"] = reel_id
    return {"success": True, "reel": meta}

def crawl_and_publish_single_reel_now(url: str, force: bool = True) -> Dict[str, Any]:
    """Crawls/downloads a specific reel URL and immediately publishes it to Instagram with strict deduplication."""
    shortcode = normalize_reel_shortcode(extract_reel_shortcode(url))
    if not shortcode:
        return {"success": False, "error": "Invalid Instagram Reel URL"}

    if is_reel_already_published(shortcode, url):
        return {"success": False, "error": f"Reel ({shortcode}) has ALREADY been published to Instagram. Duplicate posting prevented."}

    print(f"\n[ReelsCurator] 🚀 Direct Crawl & Publish Triggered for: {url}")
    meta = fetch_reel_metadata_and_download(url, download=False)
    if not meta:
        return {"success": False, "error": "Could not extract metadata from Instagram"}

    # Save reel record to DB
    reel_id = save_curated_reel(meta)
    if not reel_id:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, status FROM curated_reels WHERE shortcode = ?", (shortcode,))
        row = cursor.fetchone()
        conn.close()
        if row:
            if row["status"] == "PUBLISHED":
                return {"success": False, "error": f"Reel ({shortcode}) has already been published to Instagram."}
            reel_id = row["id"]

    if not reel_id:
        return {"success": False, "error": "Database error registering reel"}

    meta["id"] = reel_id
    success = publish_curated_reel_record(meta, dry_run=False)
    if success:
        return {"success": True, "message": f"Successfully published reel {shortcode} to Instagram!", "reel": meta}
    else:
        return {"success": False, "error": "Publishing rejected or Meta Graph API error (check server logs)", "reel": meta}


# =========================================================================
# Public / Other Users Viral Reel Discovery Pipeline (Hashtag / Geotag Radar)
# =========================================================================

PUBLIC_REEL_DISCOVERY_TARGETS = [
    ("#hpushimla", 'site:instagram.com/reel "#hpushimla"'),
    ("#hpucampus", 'site:instagram.com/reel "#hpucampus"'),
    ("#himachalpradeshuniversity", 'site:instagram.com/reel "#himachalpradeshuniversity"'),
    ("#summerhillshimla", 'site:instagram.com/reel "#summerhillshimla"'),
    ("#hpushimlalife", 'site:instagram.com/reel "#hpushimlalife"'),
    ("#hpuuniversity", 'site:instagram.com/reel "#hpuuniversity"'),
    ("hpu_viral", 'site:instagram.com/reel "HPU Shimla" viral'),
    ("hpu_summerhill", 'site:instagram.com/reel "HPU Summerhill"'),
    ("hpu_fest_campus", 'site:instagram.com/reel "HPU" (fest OR campus OR protest OR snowfall OR library)'),
    ("hpu_students", 'site:instagram.com/reel "HPU Shimla" (students OR reels)')
]

HPU_RELEVANCE_KEYWORDS = [
    "hpu", "himachal pradesh university", "summerhill", "summer hill",
    "shimla university", "hpushimla", "hpucampus", "vc office", "dr. ambedkar",
    "hpu_shimla", "hpushimlalife", "shimla"
]

def is_hpu_content_relevant(text: str) -> bool:
    """Verifies that discovered reel text actually pertains to Himachal Pradesh University."""
    if not text:
        return False
    lower_text = text.lower()
    return any(kw in lower_text for kw in HPU_RELEVANCE_KEYWORDS)

def scan_public_user_reels(lookback_days: int = REELS_LOOKBACK_DAYS) -> List[Dict[str, Any]]:
    """
    Scans public hashtags, locations, and search radar for viral HPU reels from other users.
    Discovered reels are queued with status 'DISCOVERED_PENDING_REVIEW' (NEVER autoposted).
    User can review and manually choose to publish one or all to the Instagram page.
    """
    cutoff_date, cutoff_str = get_rolling_date_cutoff(lookback_days)
    active_monitored = [h.lower() for h in get_active_target_handles()]
    print(f"\n[ReelsCurator] 🌐 Starting Public User Reel Radar across {len(PUBLIC_REEL_DISCOVERY_TARGETS)} hashtag/location queries...")
    discovered = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    today_str = datetime.now().strftime("%Y-%m-%d")

    for source_label, query_text in PUBLIC_REEL_DISCOVERY_TARGETS:
        try:
            query = urllib.parse.quote(query_text)
            rss_url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
            res = requests.get(rss_url, headers=headers, timeout=10)
            if res.status_code != 200:
                continue

            root = ET.fromstring(res.content)
            items = root.findall(".//item")[:10]

            for item in items:
                pub_date_str = item.find("pubDate").text if item.find("pubDate") is not None else ""
                article_url = item.find("link").text if item.find("link") is not None else ""

                if not article_url:
                    continue

                # Quick date check: if older than lookback cutoff date, skip
                if pub_date_str:
                    try:
                        parsed_dt = datetime.strptime(pub_date_str[:16], "%a, %d %b %Y")
                        if parsed_dt.date() < cutoff_date:
                            continue
                    except Exception:
                        pass

                # Resolve Google News redirect to direct Instagram URL
                decoded = gnewsdecoder(article_url)
                if not decoded or not decoded.get("success"):
                    continue

                direct_url = decoded.get("decoded_url")
                shortcode = normalize_reel_shortcode(extract_reel_shortcode(direct_url))
                if not shortcode or is_curated_reel_seen(shortcode, direct_url) or is_reel_already_published(shortcode, direct_url):
                    continue


                # Extract reel metadata via yt-dlp
                meta = fetch_reel_metadata_and_download(direct_url, download=False)
                if not meta:
                    continue

                uploader = (meta.get("uploader_handle") or "").strip().lower()
                # If this reel is from one of the 40 monitored channels, let the channel pipeline handle it
                if uploader and uploader in active_monitored:
                    continue

                # Engagement threshold check (views >= 1000 OR likes >= 200 OR comments >= 100)
                qualified, reason = is_reel_qualified(meta, lookback_days=lookback_days)
                if not qualified:
                    print(f"  [Radar] Reel {shortcode} (@{meta['uploader_handle']}): {reason}")
                    continue

                # Content relevance check (avoid irrelevant videos using random hashtags)
                full_text = (meta.get("caption") or "") + " " + (meta.get("uploader_handle") or "") + " " + source_label
                if not is_hpu_content_relevant(full_text):
                    print(f"  [Radar] Reel {shortcode} (@{meta['uploader_handle']}) skipped: Content not relevant to HPU.")
                    continue

                # Enqueue with DISCOVERED_PENDING_REVIEW status - NEVER autoposted!
                meta["status"] = "DISCOVERED_PENDING_REVIEW"
                meta["discovery_source"] = f"Hashtag Radar: {source_label}"
                meta["target_post_date"] = today_str

                reel_id = save_curated_reel(meta)
                if reel_id:
                    meta["id"] = reel_id
                    discovered.append(meta)
                    print(f"  🌟 [Radar] Discovered public reel #{reel_id} ({shortcode}) by @{meta['uploader_handle']} via {source_label} [QUEUED FOR REVIEW]")

        except Exception as e:
            print(f"[ReelsCurator] Error scanning public radar query '{source_label}': {e}")

    print(f"[ReelsCurator] 🏁 Public User Reel Radar completed. Found {len(discovered)} potential reels for manual review.\n")
    return discovered

def publish_single_discovered_reel(reel_id: int, dry_run: bool = False) -> Dict[str, Any]:
    """
    Publishes a user-discovered reel from the review queue upon manual confirmation.
    Attribution is credited to the original creator and today's quota is charged.
    """
    reel_record = get_curated_reel_by_id(reel_id)
    if not reel_record:
        return {"success": False, "error": f"Discovered reel #{reel_id} not found in database"}

    # Strict deduplication check
    if reel_record.get("status") == "PUBLISHED" or is_reel_already_published(reel_record.get("shortcode"), reel_record.get("instagram_url")):
        return {"success": False, "error": f"Discovered reel #{reel_id} has ALREADY been published to Instagram."}

    print(f"\n[ReelsCurator] 🚀 Publishing user-discovered reel #{reel_id} from @{reel_record.get('uploader_handle')}...")
    success = publish_curated_reel_record(reel_record, dry_run=dry_run)
    if success:
        return {"success": True, "message": f"Successfully published reel #{reel_id} to Instagram!", "reel": reel_record}
    else:
        return {"success": False, "error": f"Failed to publish reel #{reel_id}. Check server logs or daily quota limits."}

def publish_bulk_discovered_reels(reel_ids: List[int], dry_run: bool = False) -> Dict[str, Any]:
    """
    Publishes multiple selected user-discovered reels sequentially with safe interval pacing.
    """
    published = []
    failed = []
    for rid in reel_ids:
        res = publish_single_discovered_reel(rid, dry_run=dry_run)
        if res.get("success"):
            published.append(rid)
            time.sleep(15)  # Safe delay between reel uploads to Instagram
        else:
            failed.append({"id": rid, "error": res.get("error")})

    return {
        "success": len(published) > 0,
        "published_count": len(published),
        "published_ids": published,
        "failed_count": len(failed),
        "failed_items": failed
    }

