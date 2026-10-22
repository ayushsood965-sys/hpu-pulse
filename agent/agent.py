import sys
import time
from datetime import datetime
from typing import Optional, List, Dict, Any

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from .config import INSTAGRAM_HANDLE, MAX_DAILY_POSTS
from .scrapers import run_crawler_pipeline
from .news_classifier import classify_and_synthesize_update, bundle_routine_carousels
from .card_renderer import render_breaking_card, render_carousel_slides
from .reel_generator import create_looping_reel
from .uploader import upload_image, upload_video
from .poster import publish_to_instagram, publish_carousel_to_instagram, publish_reel_to_instagram, post_first_comment
from .db import (
    get_connection,
    get_pending_tier1_items,
    get_waiting_batch_items,
    get_all_waiting_items,
    get_daily_published_count,
    record_published_post,
    mark_items_published
)

def publish_breaking_reel_cycle(item: Optional[Dict[str, Any]] = None, dry_run: bool = False, is_manual: bool = False) -> Optional[Dict[str, Any]]:
    """
    Renders and publishes an immediate 9:16 Looped Video Reel with Instagram audio.
    When triggered manually or automatically, picks the best available item and posts instantly.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mode_tag = "MANUAL REEL" if is_manual else "BREAKING REEL"
    print(f"\n[{timestamp}] 🚨 INITIATING {mode_tag} CYCLE...")

    if not item:
        pending = get_pending_tier1_items()
        if pending:
            item = pending[0]
        else:
            waiting = get_all_waiting_items()
            if waiting:
                item = waiting[0]
            else:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM scraped_items ORDER BY id DESC LIMIT 1")
                row = cursor.fetchone()
                conn.close()
                if row:
                    item = dict(row)
                else:
                    print("  No items found in database to publish as video reel.")
                    return None

    item_id = item.get("id")
    print(f"  Processing update for reel [ID: {item_id}]: {item.get('title')[:70]}")

    # Step 1: AI Synthesis
    ai_content = classify_and_synthesize_update(item)
    headline = ai_content.get("headline", item.get("title")[:60])
    badge = ai_content.get("badge", "🔴 BREAKING ALERT" if item.get("priority") == "TIER1_BREAKING" else "📢 LATEST UPDATE")
    caption = ai_content.get("caption", f"📢 {badge}: {headline}")
    audio_id = ai_content.get("audio_track_id", "cornfield_chase")

    print(f"  Headline: \"{headline}\"")
    print(f"  Badge: {badge} | Audio Track ID: {audio_id}")

    # Step 2: Render 1080x1350 base card with synthesized key points
    details = item.get("ocr_text") or item.get("raw_text") or item.get("summary") or ""
    key_points = ai_content.get("key_points")
    card_path = render_breaking_card(
        headline=headline,
        category=item.get("category", "BREAKING"),
        details=details,
        badge=badge,
        key_points=key_points
    )

    # Step 3: Render 9:16 Video Reel with Instagram Audio
    reel_path, track_info = create_looping_reel(card_path, track_id=audio_id)
    audio_name = track_info["audio_name"]
    print(f"  ✔ Video reel rendered with audio [{audio_name}]: {reel_path}")

    # Step 4: Upload video
    video_url = upload_video(reel_path)
    print(f"  ✔ Video URL: {video_url}")

    # Step 5: Publish Reel
    if dry_run:
        media_id = f"dry_run_reel_{int(time.time())}"
        print(f"  [DRY RUN] Reel generated successfully (Skipped IG publish).")
    else:
        print(f"  Sending video reel to Meta Instagram Graph API...")
        try:
            media_id = publish_reel_to_instagram(video_url, caption, audio_name=audio_name, is_emergency=True, is_manual=is_manual)
            print(f"  ✔ VIDEO REEL PUBLISHED TO INSTAGRAM! Media ID: {media_id}")

            # Post friendly student comment
            first_comment = (
                "Drop your questions or branch/semester in the comments below! 👇\n"
                "Save this post so you don't miss any upcoming dates."
            )
            post_first_comment(media_id, first_comment)
        except Exception as e:
            print(f"  ❌ Instagram Reel Publish Failed: {e}")
            raise e

    # Record in DB
    record_published_post(
        post_type="REEL",
        tier="TIER1_BREAKING" if item.get("priority") == "TIER1_BREAKING" else "TIER2_ROUTINE",
        category=item.get("category", "GENERAL"),
        headline=headline,
        caption=caption,
        media_urls=[video_url],
        instagram_media_id=media_id,
        audio_track=audio_name,
        scraped_item_ids=[item_id] if item_id else None
    )

    return {
        "timestamp": timestamp,
        "type": "breaking_reel",
        "headline": headline,
        "media_id": media_id,
        "audio_track": audio_name
    }

def publish_routine_carousel_cycle(items: Optional[List[Dict[str, Any]]] = None, category: Optional[str] = None, dry_run: bool = False, is_manual: bool = False) -> Optional[Dict[str, Any]]:
    """
    Renders and publishes a 1080x1350 multi-slide Instagram Carousel
    batching together similar academic notices (Results, Merit lists, Datesheets, General updates).
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mode_tag = "MANUAL CAROUSEL" if is_manual else "ROUTINE CAROUSEL BATCH"
    print(f"\n[{timestamp}] 📚 INITIATING {mode_tag} CYCLE...")

    if not items:
        waiting = get_waiting_batch_items(category=category)
        if not waiting:
            waiting = get_all_waiting_items()
        if not waiting:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM scraped_items ORDER BY id DESC LIMIT 4")
            rows = cursor.fetchall()
            conn.close()
            if rows:
                waiting = [dict(r) for r in rows]
            else:
                print("  No waiting items in queue or database for carousel.")
                return None
        # Batch top 2 to 4 items
        items = waiting[:4]

    item_ids = [it.get("id") for it in items if it.get("id")]
    print(f"  Bundling {len(items)} items for carousel post (IDs: {item_ids})...")

    # Step 1: AI Bundle Synthesis
    cdata = bundle_routine_carousels(items)
    headline = cdata.get("headline", "HPU Updates")
    caption = cdata.get("caption", "HPU Official Updates")

    # Step 2: Render Multi-Slide Cards
    slide_paths = render_carousel_slides(cdata)
    print(f"  ✔ Rendered {len(slide_paths)} carousel slides.")

    # Step 3: Upload slides
    print(f"  Hosting {len(slide_paths)} slides for Instagram ingestion...")
    image_urls = []
    for idx, spath in enumerate(slide_paths, start=1):
        url = upload_image(spath)
        image_urls.append(url)
        print(f"  ✔ Slide {idx}/{len(slide_paths)} uploaded: {url}")
        time.sleep(0.5)

    # Step 4: Publish Carousel
    if dry_run:
        media_id = f"dry_run_carousel_{int(time.time())}"
        print(f"  [DRY RUN] Carousel generated successfully with {len(image_urls)} slides.")
    else:
        print(f"  Sending multi-slide container to Meta Instagram Graph API...")
        try:
            media_id = publish_carousel_to_instagram(image_urls, caption, is_emergency=is_manual, is_manual=is_manual)
            print(f"  ✔ CAROUSEL PUBLISHED TO INSTAGRAM! Media ID: {media_id}")

            # Post first student prompt comment
            comment_text = (
                "Drop your course and semester below if you have any questions! 💬\n"
                "Save this post & share with your classmates."
            )
            post_first_comment(media_id, comment_text)
        except Exception as e:
            print(f"  ❌ Instagram Carousel Publish Failed: {e}")
            raise e

    # Record in DB
    record_published_post(
        post_type="CAROUSEL",
        tier="TIER2_ROUTINE",
        category=cdata.get("category", "ROUTINE"),
        headline=headline,
        caption=caption,
        media_urls=image_urls,
        instagram_media_id=media_id,
        audio_track=None,
        scraped_item_ids=item_ids
    )

    return {
        "timestamp": timestamp,
        "type": "routine_carousel",
        "headline": headline,
        "slides_count": len(image_urls),
        "media_id": media_id
    }

def run_automated_crawler_cycle() -> int:
    """
    Crawls university portals, newspaper sources, and student communities every 6 hours.
    Deduplicates and indexes fresh notices into the database queue.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{timestamp}] 🕷️ RUNNING 6-HOUR MULTI-SOURCE CRAWLER PIPELINE...")
    new_items = run_crawler_pipeline()
    print(f"  ✔ 6-Hour crawl finished: {len(new_items)} fresh updates indexed into queue.")
    return len(new_items)

def execute_scheduled_publishing_cycle(dry_run: bool = False, is_manual: bool = False) -> Optional[Dict[str, Any]]:
    """
    Publishing Cycle:
    - Automatic mode (Scheduled every 12 hours): Strict limit of MAX_DAILY_POSTS (2/day).
    - Manual mode (Admin triggered): NO daily limit! Posts instantly.
    - Rule:
        * If 1 to 2 updates in queue -> formats and publishes as a 9:16 LOOPING VIDEO REEL with audio.
        * If multiple (3 or more) updates in queue -> formats and bundles into a CAROUSEL ALBUM.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    daily_count = get_daily_published_count()

    if not is_manual and daily_count >= MAX_DAILY_POSTS and not dry_run:
        print(f"\n[{timestamp}] ⏸️ [Scheduler] Daily cap reached ({daily_count}/{MAX_DAILY_POSTS} posts published today). Skipping 12-hour window.")
        return None

    waiting_items = get_all_waiting_items()
    if not waiting_items:
        if is_manual:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM scraped_items ORDER BY id DESC LIMIT 5")
            rows = cursor.fetchall()
            conn.close()
            if rows:
                waiting_items = [dict(r) for r in rows]
        if not waiting_items:
            print(f"\n[{timestamp}] 📭 No pending updates in queue for this publishing cycle.")
            return None

    total_waiting = len(waiting_items)
    mode_str = "MANUAL POST (NO DAILY LIMIT)" if is_manual else "12-HOUR SCHEDULED POST"
    print(f"\n[{timestamp}] ⏰ INITIATING {mode_str} CYCLE...")
    print(f"  Current daily status: {daily_count}/{MAX_DAILY_POSTS} posts published today (Manual bypass: {is_manual}).")
    print(f"  Queue contains {total_waiting} pending update(s).")

    if total_waiting <= 2:
        # User Mandate: 1-2 updates -> Looping video reel
        chosen_item = waiting_items[0]
        print(f"  ⚡ {total_waiting} update(s) detected (1-2 threshold) -> Publishing as LOOPING VIDEO REEL with background audio...")
        return publish_breaking_reel_cycle(chosen_item, dry_run=dry_run, is_manual=is_manual)
    else:
        # User Mandate: Multiple (3+) updates -> Multi-slide carousel album
        batch = waiting_items[:5]
        print(f"  📚 {total_waiting} updates detected (Multiple threshold) -> Bundling {len(batch)} circulars into a CAROUSEL ALBUM...")
        return publish_routine_carousel_cycle(items=batch, dry_run=dry_run, is_manual=is_manual)

# Backward-compatibility alias
run_automated_check_and_post_cycle = execute_scheduled_publishing_cycle
