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
    REELS_DATE_CUTOFF,
    TARGET_REEL_HANDLES,
    SERVER_URL,
    INSTAGRAM_ACCESS_TOKEN,
    INSTAGRAM_ACCOUNT_ID
)
from .db import (
    is_curated_reel_seen,
    save_curated_reel,
    get_daily_curated_reels_count,
    get_pending_curated_reels,
    mark_curated_reel_published,
    update_curated_reel_status,
    record_published_post
)
from .poster import publish_reel_to_instagram
from .uploader import upload_video

REEL_SHORTCODE_REGEX = re.compile(r"instagram\.com/(?:reel|p|reels)/([A-Za-z0-9_-]+)", re.IGNORECASE)

def extract_reel_shortcode(url: str) -> Optional[str]:
    """Extracts the Instagram shortcode from any post or reel URL."""
    if not url:
        return None
    match = REEL_SHORTCODE_REGEX.search(url)
    return match.group(1) if match else None

def clean_handle(handle: str) -> str:
    """Removes leading @ and trims handle."""
    return (handle or "").strip().lstrip("@")

def parse_date_cutoff() -> str:
    """Returns YYYYMMDD string for date cutoff."""
    return REELS_DATE_CUTOFF.replace("-", "")

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

def is_reel_qualified(meta: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Enforces filtering rules:
    1. Uploaded ON or AFTER 25th October 2026.
    2. Engagement: Views > 1000 OR Likes > 200 OR Comments > 100.
    """
    cutoff_str = parse_date_cutoff()  # "20261025"
    upload_date = meta.get("upload_date") or ""

    if upload_date and upload_date < cutoff_str:
        return False, f"Uploaded on {upload_date}, which is before cutoff {cutoff_str} (25 Oct 2026)"

    views = meta.get("view_count") or 0
    likes = meta.get("like_count") or 0
    comments = meta.get("comment_count") or 0

    has_views = views > 1000
    has_likes = likes > 200
    has_comments = comments > 100

    if has_views or has_likes or has_comments:
        return True, f"Qualified (Views: {views}, Likes: {likes}, Comments: {comments})"

    return False, f"Below thresholds (Views: {views}<=1000, Likes: {likes}<=200, Comments: {comments}<=100)"

def scan_target_handles_for_reels(force_for_test: bool = False) -> List[Dict[str, Any]]:
    """
    Monitors all Category 1 to 4 target handles and general HPU keywords for newly published reels.
    Identifies eligible reels, applies cutoff & thresholds, and enqueues them.
    """
    targets = [(h, f'site:instagram.com/reel "{h}"') for h in TARGET_REEL_HANDLES]
    targets += [
        ("hpu", 'site:instagram.com/reel "hpu"'),
        ("himachal_pradesh_university", 'site:instagram.com/reel "himachal pradesh university"'),
        ("hpushimla", 'site:instagram.com/reel "hpushimla"')
    ]
    print(f"\n[ReelsCurator] 🔍 Starting scan across {len(targets)} HPU search targets (40 accounts + campus keywords)...")
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

                # Quick date check: if item pubDate says older year or month, skip
                if pub_date_str:
                    try:
                        parsed_dt = datetime.strptime(pub_date_str[:16], "%a, %d %b %Y")
                        if parsed_dt.date() < date(2026, 10, 25):
                            continue
                    except Exception:
                        pass

                # Resolve Google News redirect to direct Instagram URL
                decoded = gnewsdecoder(article_url)
                if not decoded or not decoded.get("success"):
                    continue

                direct_url = decoded.get("decoded_url")
                shortcode = extract_reel_shortcode(direct_url)
                if not shortcode or is_curated_reel_seen(shortcode):
                    continue

                # Inspect reel metadata via yt-dlp
                meta = fetch_reel_metadata_and_download(direct_url, download=False)
                if not meta:
                    continue

                # If uploader not extracted from video, use the target handle
                if not meta.get("uploader_handle"):
                    meta["uploader_handle"] = handle

                qualified, reason = is_reel_qualified(meta)
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
    Downloads the MP4 file (if needed), hosts it on SERVER_URL,
    and publishes the reel to @hpu.pulse via Meta Graph API.
    """
    reel_id = reel_record.get("id")
    url = reel_record.get("instagram_url")
    shortcode = reel_record.get("shortcode")
    handle = reel_record.get("uploader_handle")

    today_str = datetime.now().strftime("%Y-%m-%d")
    today_count = get_daily_curated_reels_count(today_str)

    if today_count >= MAX_DAILY_REEL_UPLOADS:
        tomorrow_str = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        print(f"[ReelsCurator] 🛑 Daily quota reached ({today_count}/{MAX_DAILY_REEL_UPLOADS}). Moving #{reel_id} to tomorrow ({tomorrow_str}).")
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
            update_curated_reel_status(reel_id, "FAILED")
            return False
        local_path = download_meta["local_video_path"]

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
        mark_curated_reel_published(reel_id, fake_id)
        record_published_post(
            post_type="REEL",
            tier="CURATED_REEL",
            category="CAMPUS_REELS",
            headline=f"Reel via @{handle}",
            caption=caption,
            media_urls=[public_video_url],
            instagram_media_id=fake_id
        )
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
        mark_curated_reel_published(reel_id, media_id)
        record_published_post(
            post_type="REEL",
            tier="CURATED_REEL",
            category="CAMPUS_REELS",
            headline=f"Reel via @{handle}",
            caption=caption,
            media_urls=[public_video_url],
            instagram_media_id=media_id
        )
        # Auto-cleanup: remove local video file to maintain near-zero disk usage
        try:
            if local_path and Path(local_path).exists():
                os.remove(local_path)
                print(f"  🧹 Cleaned up local video file {video_filename} from server disk.")
        except Exception as e:
            print(f"  Cleanup note: {e}")
        return True
    else:
        print(f"  ❌ Meta Graph API publishing failed for reel #{reel_id}.")
        update_curated_reel_status(reel_id, "FAILED")
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
        success = publish_curated_reel_record(reel, dry_run=dry_run)
        if success:
            posted_count += 1
            if posted_count < max_to_post and not dry_run:
                time.sleep(15)

    return posted_count

def manually_enqueue_reel(url: str, force: bool = False) -> Dict[str, Any]:
    """Allows manual link input from the dashboard."""
    shortcode = extract_reel_shortcode(url)
    if not shortcode:
        return {"success": False, "error": "Invalid Instagram Reel URL"}

    if is_curated_reel_seen(shortcode) and not force:
        return {"success": False, "error": f"Reel ({shortcode}) has already been recorded in database"}

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
