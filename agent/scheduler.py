import sys
import argparse
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

if getattr(sys.stdout, 'encoding', None) != 'utf-8':
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from .config import CRAWL_INTERVAL_MINUTES, TIMEZONE, MAX_DAILY_REEL_UPLOADS
from .agent import (
    run_automated_crawler_cycle,
    publish_daily_7pm_news_carousel,
    run_curated_reels_scanner_cycle,
    publish_next_curated_reel_cycle,
    publish_breaking_reel_cycle
)
from .auto_commenter import process_comments

def scheduled_crawler_job():
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⏰ Scheduled Multi-Source Crawler Fired!")
    try:
        run_automated_crawler_cycle()
    except Exception as e:
        print(f"❌ Error during scheduled crawl: {e}")

def scheduled_daily_7pm_carousel_job():
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⏰ Scheduled 7:00 PM Daily News Carousel Fired!")
    try:
        publish_daily_7pm_news_carousel(dry_run=False, is_manual=False)
    except Exception as e:
        print(f"❌ Error during 7 PM daily carousel publish: {e}")

def scheduled_reels_scanner_job():
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔍 Scheduled Target Handles Reels Scanner Fired!")
    try:
        run_curated_reels_scanner_cycle()
    except Exception as e:
        print(f"❌ Error during reels scanning: {e}")

def scheduled_reels_publisher_job():
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🎬 Scheduled Curated Reels Publisher Fired (Max 15/day quota)!")
    try:
        publish_next_curated_reel_cycle(dry_run=False, max_to_post=1)
    except Exception as e:
        print(f"❌ Error during curated reels publishing: {e}")

def scheduled_comment_job():
    try:
        process_comments()
    except Exception as e:
        print(f"❌ Error in auto-comment responder: {e}")

def start_scheduler(crawl_immediately: bool = False):
    scheduler = BlockingScheduler(timezone=TIMEZONE)

    print("==================================================================")
    print("   🏛 HIMACHAL PRADESH UNIVERSITY — AUTONOMOUS PULSE AGENT 🏛")
    print(f"   Timezone: {TIMEZONE}")
    print(f"   Multi-Source Crawler: Runs every 60 minutes")
    print(f"   Daily News Carousel: Exactly 1 per day, published at 7:00 PM IST")
    print(f"   Curated Reels: 40 monitored handles, engagement filtered, max {MAX_DAILY_REEL_UPLOADS}/day")
    print("   Auto-Comment Responder: Active every 30 minutes")
    print("==================================================================")

    # 1. 60-Minute Portal & Newspaper Crawler
    scheduler.add_job(
        scheduled_crawler_job,
        trigger=IntervalTrigger(minutes=60, timezone=TIMEZONE),
        id="job_hpu_crawler",
        name="60-Minute HPU News Crawler",
        misfire_grace_time=180
    )

    # 2. Daily 7:00 PM News Carousel Job (Single Carousel Per Day)
    scheduler.add_job(
        scheduled_daily_7pm_carousel_job,
        trigger=CronTrigger(hour=19, minute=0, timezone=TIMEZONE),
        id="job_daily_7pm_carousel",
        name="Daily 7:00 PM News Carousel",
        misfire_grace_time=600
    )

    # 3. Curated Reels Scanner (Scans Categories 1 to 4 every 90 minutes)
    scheduler.add_job(
        scheduled_reels_scanner_job,
        trigger=IntervalTrigger(minutes=90, timezone=TIMEZONE),
        id="job_reels_scanner",
        name="90-Minute Curated Reels Scanner",
        misfire_grace_time=300
    )

    # 4. Curated Reels Publisher (Paced every 45 minutes between 9 AM and 10 PM)
    scheduler.add_job(
        scheduled_reels_publisher_job,
        trigger=CronTrigger(hour="9-22", minute="15,45", timezone=TIMEZONE),
        id="job_reels_publisher",
        name=f"Curated Reels Publisher (Max {MAX_DAILY_REEL_UPLOADS}/day)",
        misfire_grace_time=300
    )

    # 5. Comment Auto-Responder
    scheduler.add_job(
        scheduled_comment_job,
        trigger=IntervalTrigger(minutes=30, timezone=TIMEZONE),
        id="job_auto_comments",
        name="Auto Comment Responder",
        misfire_grace_time=60
    )

    if crawl_immediately:
        print("\n🚀 Executing initial crawl immediately upon startup...")
        scheduled_crawler_job()

    print("\n⚡ Autonomous HPU Pulse Agent is running in the background. Press Ctrl+C to stop.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\n🛑 Scheduler stopped by user.")
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
