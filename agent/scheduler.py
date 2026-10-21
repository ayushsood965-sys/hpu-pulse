import sys
import argparse
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from .config import CRAWL_INTERVAL_MINUTES, ROUTINE_BATCH_INTERVAL_HOURS, TIMEZONE
from .agent import (
    run_automated_check_and_post_cycle,
    publish_breaking_reel_cycle,
    publish_routine_carousel_cycle
)
from .auto_commenter import process_comments

def scheduled_crawler_job():
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⏰ Scheduled 30-Minute Crawler Fired!")
    try:
        run_automated_check_and_post_cycle(dry_run=False)
    except Exception as e:
        print(f"❌ Error during scheduled crawl: {e}")

def scheduled_batch_carousel_job():
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⏰ Scheduled Batch Carousel Job Fired!")
    try:
        publish_routine_carousel_cycle(dry_run=False)
    except Exception as e:
        print(f"❌ Error during carousel batching: {e}")

def scheduled_comment_job():
    try:
        process_comments()
    except Exception as e:
        print(f"❌ Error in auto-comment responder: {e}")

def start_scheduler(crawl_immediately: bool = False):
    scheduler = BlockingScheduler(timezone=TIMEZONE)

    print("==================================================================")
    print("   🏛 HIMACHAL PRADESH UNIVERSITY — AUTONOMOUS NEWS AGENT 🏛")
    print(f"   Timezone: {TIMEZONE}")
    print(f"   Multi-Source Crawler: Runs every {CRAWL_INTERVAL_MINUTES} minutes")
    print(f"   Tier 1 Breaking Reel: Publishes IMMEDIATELY on detection")
    print(f"   Tier 2 Routine Carousel: Batches every {ROUTINE_BATCH_INTERVAL_HOURS} hours")
    print("   Auto-Comment Responder: Active every 30 minutes")
    print("==================================================================")

    # 1. 30-Minute Portal & News Crawler (also triggers immediate Tier 1 Reels)
    scheduler.add_job(
        scheduled_crawler_job,
        trigger=IntervalTrigger(minutes=CRAWL_INTERVAL_MINUTES, timezone=TIMEZONE),
        id="job_hpu_crawler",
        name="30-Minute HPU News Crawler",
        misfire_grace_time=120
    )
    print(f"  🕷 Crawler: Active every {CRAWL_INTERVAL_MINUTES} minutes")

    # 2. Batch Carousel Worker
    scheduler.add_job(
        scheduled_batch_carousel_job,
        trigger=IntervalTrigger(hours=ROUTINE_BATCH_INTERVAL_HOURS, timezone=TIMEZONE),
        id="job_carousel_batcher",
        name="Routine Carousel Batcher",
        misfire_grace_time=300
    )
    print(f"  📚 Routine Carousel Batcher: Active every {ROUTINE_BATCH_INTERVAL_HOURS} hours")

    # 3. Comment Auto-Responder
    scheduler.add_job(
        scheduled_comment_job,
        trigger=IntervalTrigger(minutes=30, timezone=TIMEZONE),
        id="job_auto_comments",
        name="Auto Comment Responder",
        misfire_grace_time=60
    )
    print("  💬 Auto-Comment Responder: Active every 30 minutes")

    if crawl_immediately:
        print("\n🚀 Executing initial crawl immediately upon startup...")
        scheduled_crawler_job()

    print("\n⚡ Autonomous HPU News Agent is running in the background. Press Ctrl+C to stop.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\n🛑 Scheduler stopped by user.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HPU News & Updates Scheduler")
    parser.add_argument("--now", action="store_true", help="Crawl and check immediately on start")
    parser.add_argument("--carousel", action="store_true", help="Publish a routine carousel batch immediately")
    parser.add_argument("--reel", action="store_true", help="Publish a breaking reel immediately")
    parser.add_argument("--comments", action="store_true", help="Run comment responder once")
    args = parser.parse_args()

    if args.comments:
        process_comments()
    elif args.carousel:
        publish_routine_carousel_cycle(dry_run=False)
    elif args.reel:
        publish_breaking_reel_cycle(dry_run=False)
    else:
        start_scheduler(crawl_immediately=args.now)
