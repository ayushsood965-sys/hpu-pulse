import sys
import time
from datetime import datetime
from typing import Optional, List, Dict, Any

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from .config import INSTAGRAM_HANDLE
from .scrapers import run_crawler_pipeline
from .news_classifier import classify_and_synthesize_update, bundle_routine_carousels
from .card_renderer import render_breaking_card, render_carousel_slides
from .reel_generator import create_looping_reel
from .uploader import upload_image, upload_video
from .poster import publish_to_instagram, publish_carousel_to_instagram, publish_reel_to_instagram, post_first_comment
from .db import (
    get_pending_tier1_items,
    get_waiting_batch_items,
    record_published_post,
    mark_items_published
)

def publish_breaking_reel_cycle(item: Optional[Dict[str, Any]] = None, dry_run: bool = False) -> Optional[Dict[str, Any]]:
    """
    Renders and publishes an immediate 9:16 Looped Video Reel with Instagram audio
    for Tier 1 Emergency / Breaking News (Weather holiday, exam postponed, fee rollback, etc.).
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{timestamp}] 🚨 INITIATING TIER 1 BREAKING REEL CYCLE...")

    if not item:
        pending = get_pending_tier1_items()
        if not pending:
            print("  No pending Tier 1 items to publish right now.")
            return None
        item = pending[0]

    item_id = item.get("id")
    print(f"  Processing breaking update [ID: {item_id}]: {item.get('title')[:70]}")

    # Step 1: AI Synthesis
    ai_content = classify_and_synthesize_update(item)
    headline = ai_content.get("headline", item.get("title")[:60])
    badge = ai_content.get("badge", "🔴 BREAKING ALERT")
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
        media_id = publish_reel_to_instagram(video_url, caption, audio_name=audio_name, is_emergency=True)
        print(f"  ✔ BREAKING REEL PUBLISHED TO INSTAGRAM! Media ID: {media_id}")

        # Post friendly student comment
        first_comment = (
            "Drop your questions or branch/semester in the comments below! 👇\n"
            "Save this post so you don't miss any upcoming dates."
        )
        post_first_comment(media_id, first_comment)

    # Record in DB
    record_published_post(
        post_type="REEL",
        tier="TIER1_BREAKING",
        category=item.get("category", "BREAKING"),
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

def publish_routine_carousel_cycle(items: Optional[List[Dict[str, Any]]] = None, category: Optional[str] = None, dry_run: bool = False) -> Optional[Dict[str, Any]]:
    """
    Renders and publishes a 1080x1350 multi-slide Instagram Carousel
    batching together similar routine academic notices (Results, Merit lists, Datesheets).
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{timestamp}] 📚 INITIATING TIER 2 ROUTINE CAROUSEL BATCH CYCLE...")

    if not items:
        waiting = get_waiting_batch_items(category=category)
        if not waiting:
            print("  No waiting batch items in queue.")
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
    image_urls = []
    for spath in slide_paths:
        url = upload_image(spath)
        image_urls.append(url)
        time.sleep(0.5)

    # Step 4: Publish Carousel
    if dry_run:
        media_id = f"dry_run_carousel_{int(time.time())}"
        print(f"  [DRY RUN] Carousel generated successfully with {len(image_urls)} slides.")
    else:
        media_id = publish_carousel_to_instagram(image_urls, caption, is_emergency=False)
        print(f"  ✔ CAROUSEL PUBLISHED TO INSTAGRAM! Media ID: {media_id}")

        # Post first student prompt comment
        comment_text = (
            "Drop your course and semester below if you have any questions! 💬\n"
            "Save this post & share with your classmates."
        )
        post_first_comment(media_id, comment_text)

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

def run_automated_check_and_post_cycle(dry_run: bool = False) -> Dict[str, Any]:
    """
    Called every 30 minutes by scheduler:
    1. Runs multi-source crawler pipeline.
    2. If any Tier 1 Breaking News was found, publishes immediately!
    3. Checks batch queue: if enough items exist or batch interval elapsed, publishes Carousel.
    """
    new_items = run_crawler_pipeline()

    results = {
        "crawled_new": len(new_items),
        "published_reels": 0,
        "published_carousels": 0
    }

    # 1. Immediate Tier 1 Breaking Check
    pending_tier1 = get_pending_tier1_items()
    for item in pending_tier1:
        res = publish_breaking_reel_cycle(item, dry_run=dry_run)
        if res:
            results["published_reels"] += 1

    # 2. Tier 2 Carousel Batch Check
    waiting_batch = get_waiting_batch_items()
    if len(waiting_batch) >= 2:
        res = publish_routine_carousel_cycle(items=waiting_batch[:4], dry_run=dry_run)
        if res:
            results["published_carousels"] += 1

    return results
