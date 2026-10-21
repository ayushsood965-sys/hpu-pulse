import sys
import argparse
import sqlite3

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from agent.scrapers import run_crawler_pipeline
from agent.agent import (
    publish_breaking_reel_cycle,
    publish_routine_carousel_cycle,
    run_automated_check_and_post_cycle
)
from agent.scheduler import start_scheduler
from agent.auto_commenter import process_comments
from agent.config import DB_PATH

def show_history():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("\n=================== RECENT PUBLISHED POSTS ===================")
    cursor.execute("SELECT id, post_type, tier, headline, instagram_media_id, published_at FROM published_posts ORDER BY id DESC LIMIT 10")
    posts = cursor.fetchall()
    if not posts:
        print("No posts published yet.")
    for p in posts:
        print(f"[{p['published_at']}] (ID: {p['id']}) [{p['post_type']}] [{p['tier']}] IG Media: {p['instagram_media_id']}")
        print(f"  Headline: \"{p['headline']}\"\n")

    print("=================== PENDING BATCH QUEUE ===================")
    cursor.execute("""
        SELECT b.id, s.title, b.category, b.enqueued_at 
        FROM batch_queue b JOIN scraped_items s ON b.scraped_item_id = s.id 
        WHERE b.status = 'WAITING' ORDER BY b.enqueued_at ASC LIMIT 10
    """)
    queue = cursor.fetchall()
    if not queue:
        print("Batch queue is currently empty.")
    for q in queue:
        print(f"  [{q['category']}] {q['title'][:75]} (Enqueued: {q['enqueued_at']})")

    conn.close()
    print("============================================================")

def main():
    parser = argparse.ArgumentParser(
        description="Himachal Pradesh University (HPU) Autonomous Instagram News Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  python main.py --schedule       # Starts 24/7 autonomous daemon (30-min crawl + immediate Reels + batch Carousels)
  python main.py --crawl          # Runs 30-minute multi-source crawl once
  python main.py --carousel       # Generates & publishes a routine carousel batch immediately
  python main.py --reel           # Generates & publishes a 9:16 breaking reel with music immediately
  python main.py --comments       # Scans & auto-replies to student comments
  python main.py --dry-run        # Tests generation & card rendering without publishing
  python main.py --history        # Displays recent posts & queued batch items from database
"""
    )
    parser.add_argument("--schedule", action="store_true", help="Start 24/7 autonomous growth scheduler")
    parser.add_argument("--crawl", action="store_true", help="Run multi-source crawler pipeline once")
    parser.add_argument("--carousel", action="store_true", help="Generate & publish a routine carousel batch")
    parser.add_argument("--reel", action="store_true", help="Generate & publish a breaking 9:16 video reel with music")
    parser.add_argument("--comments", action="store_true", help="Scan & auto-reply to student comments")
    parser.add_argument("--dry-run", action="store_true", help="Test card generation & video rendering without publishing")
    parser.add_argument("--history", action="store_true", help="Display recent database history")
    parser.add_argument("--now", action="store_true", help="Trigger an initial crawl immediately upon starting scheduler")

    args = parser.parse_args()

    if args.history:
        show_history()
    elif args.crawl:
        run_crawler_pipeline()
    elif args.carousel:
        publish_routine_carousel_cycle(dry_run=args.dry_run)
    elif args.reel:
        publish_breaking_reel_cycle(dry_run=args.dry_run)
    elif args.comments:
        process_comments()
    elif args.schedule:
        start_scheduler(crawl_immediately=args.now)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
