import os
import sys
import time
import uuid
import sqlite3
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from fastapi import FastAPI, Request, Response, BackgroundTasks, Header, Cookie, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from agent.config import (
    OUTPUT_DIR,
    CRAWL_INTERVAL_HOURS,
    CRAWL_INTERVAL_MINUTES,
    POST_INTERVAL_HOURS,
    MAX_DAILY_POSTS,
    ROUTINE_BATCH_INTERVAL_HOURS,
    TIMEZONE,
    DB_PATH,
    INSTAGRAM_HANDLE,
    SERVER_URL
)
from agent.scrapers import run_crawler_pipeline
from agent.agent import (
    publish_breaking_reel_cycle,
    publish_routine_carousel_cycle,
    run_automated_crawler_cycle,
    execute_scheduled_publishing_cycle,
    run_automated_check_and_post_cycle
)
from agent.auto_commenter import process_comments
from agent.db import init_db, purge_stale_pending_items, get_daily_published_count

app = FastAPI(title="HPU Pulse — Autonomous Agent Control Center")

# Security & Password Protection
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "Ayush1994*").strip()
ACTIVE_SESSIONS = set()

class LoginRequest(BaseModel):
    password: str

# Mount generated_cards directory for public media streaming
app.mount("/generated_cards", StaticFiles(directory=str(OUTPUT_DIR)), name="generated_cards")

# Circular Log Buffer
MAX_LOGS = 600
system_logs: List[Dict[str, str]] = []

def log_event(message: str, level: str = "INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = {"timestamp": ts, "message": message, "level": level}
    system_logs.append(entry)
    if len(system_logs) > MAX_LOGS:
        system_logs.pop(0)
    try:
        sys.__stdout__.write(f"[{ts}] [{level}] {message}\n")
        sys.__stdout__.flush()
    except Exception:
        pass

class StdoutLogInterceptor:
    def __init__(self, original, default_level="INFO"):
        self.original = original
        self.default_level = default_level
        self.buffer = ""

    def write(self, s):
        try:
            self.original.write(s)
            self.original.flush()
        except Exception:
            pass
        self.buffer += s
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            line = line.strip()
            if line and not line.startswith("["):
                if self.default_level == "ERROR":
                    lvl = "ERROR"
                else:
                    lvl = "ERROR" if any(x in line.lower() for x in ["error", "fail", "exception", "traceback"]) else ("WARN" if "warn" in line.lower() else "INFO")
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                system_logs.append({"timestamp": ts, "message": line, "level": lvl})
                if len(system_logs) > MAX_LOGS:
                    system_logs.pop(0)

    def flush(self):
        try:
            self.original.flush()
        except Exception:
            pass

sys.stdout = StdoutLogInterceptor(sys.stdout, default_level="INFO")
sys.stderr = StdoutLogInterceptor(sys.stderr, default_level="ERROR")

_token_cache = {"valid": None, "error": None, "checked_at": 0}

def check_meta_token_status(token: str) -> dict:
    global _token_cache
    now = time.time()
    if _token_cache["checked_at"] and (now - _token_cache["checked_at"] < 30) and _token_cache["valid"] is not None:
        return _token_cache

    if not token or token.startswith("your_"):
        _token_cache = {"valid": False, "error": "No token configured in .env", "checked_at": now}
        return _token_cache

    try:
        import requests
        res = requests.get(f"https://graph.facebook.com/v21.0/me?access_token={token}", timeout=4)
        data = res.json()
        if "error" in data:
            err_msg = data["error"].get("message", "Token expired or invalid")
            _token_cache = {"valid": False, "error": err_msg, "checked_at": now}
        else:
            _token_cache = {"valid": True, "name": data.get("name"), "id": data.get("id"), "checked_at": now}
    except Exception as e:
        _token_cache = {"valid": False, "error": str(e), "checked_at": now}
    return _token_cache

def safe_crawl_cycle():
    try:
        run_automated_crawler_cycle()
    except Exception as e:
        log_event(f"❌ 6-Hour Automated Crawler Failed: {e}", level="ERROR")

def safe_scheduled_post_cycle(dry_run: bool = False, is_manual: bool = False):
    try:
        execute_scheduled_publishing_cycle(dry_run=dry_run, is_manual=is_manual)
    except Exception as e:
        log_event(f"❌ Post Cycle Failed: {e}", level="ERROR")

def safe_carousel_cycle(items=None, category=None, dry_run=False, is_manual=True):
    try:
        publish_routine_carousel_cycle(items=items, category=category, dry_run=dry_run, is_manual=is_manual)
    except Exception as e:
        log_event(f"❌ Routine Carousel Publish Failed: {e}", level="ERROR")

def safe_reel_cycle(item=None, dry_run=False, is_manual=True):
    try:
        publish_breaking_reel_cycle(item=item, dry_run=dry_run, is_manual=is_manual)
    except Exception as e:
        log_event(f"❌ Video Reel Publish Failed: {e}", level="ERROR")

def safe_comments_cycle():
    try:
        process_comments()
    except Exception as e:
        log_event(f"❌ Comment Responder Failed: {e}", level="ERROR")

class AgentManager:
    def __init__(self):
        self.scheduler: BackgroundScheduler = None
        self.is_running: bool = False
        self.start_time: float = time.time()
        self.last_action: str = "Initialized"

    def start(self):
        if self.is_running and self.scheduler and self.scheduler.running:
            return

        self.scheduler = BackgroundScheduler(timezone=TIMEZONE)

        # 1. Multi-source crawler every 6 hours
        self.scheduler.add_job(
            safe_crawl_cycle,
            trigger=IntervalTrigger(hours=CRAWL_INTERVAL_HOURS, timezone=TIMEZONE),
            id="job_crawl_check",
            name=f"Multi-Source Crawler (Every {CRAWL_INTERVAL_HOURS}h)",
            misfire_grace_time=300
        )

        # 2. 12-Hour Scheduled Post Worker (Max 2 posts daily: 1-2 Reel, 3+ Carousel)
        self.scheduler.add_job(
            safe_scheduled_post_cycle,
            trigger=IntervalTrigger(hours=POST_INTERVAL_HOURS, timezone=TIMEZONE),
            id="job_scheduled_post",
            name=f"12-Hour Post Worker (Max {MAX_DAILY_POSTS}/day)",
            misfire_grace_time=300
        )

        # 3. Instagram comment auto-responder
        self.scheduler.add_job(
            safe_comments_cycle,
            trigger=IntervalTrigger(minutes=30, timezone=TIMEZONE),
            id="job_comments",
            name="Instagram Comment Auto-Responder",
            misfire_grace_time=60
        )

        self.scheduler.start()
        self.is_running = True
        self.last_action = "Agent Started"
        log_event(f"✦ 24/7 Autonomous HPU News Agent Started (Crawl every {CRAWL_INTERVAL_HOURS}h | Posts every {POST_INTERVAL_HOURS}h | Max {MAX_DAILY_POSTS} posts daily)")

    def stop(self):
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        self.is_running = False
        self.last_action = "Agent Paused"
        log_event("🛑 Agent Background Scheduler Stopped by Admin", level="WARN")

    def restart(self):
        log_event("🔄 Restarting HPU Agent & Scheduler...")
        self.stop()
        time.sleep(1)
        self.start()
        self.last_action = "Agent Restarted"

agent_manager = AgentManager()

@app.on_event("startup")
def on_startup():
    init_db()
    purged = purge_stale_pending_items()
    if purged:
        log_event(f"🧹 Purged {purged} stale items from database on startup.")
    agent_manager.start()

@app.on_event("shutdown")
def on_shutdown():
    agent_manager.stop()

# Authentication Helpers
def verify_auth(request: Request, authorization: Optional[str] = Header(None), hpu_auth_session: Optional[str] = Cookie(None)):
    token = None
    if hpu_auth_session and hpu_auth_session in ACTIVE_SESSIONS:
        return True
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        if token in ACTIVE_SESSIONS:
            return True
    return False

@app.post("/api/auth/login")
def login(req: LoginRequest, response: Response):
    if req.password == DASHBOARD_PASSWORD:
        token = secrets.token_hex(24)
        ACTIVE_SESSIONS.add(token)
        response.set_cookie(
            key="hpu_auth_session",
            value=token,
            max_age=86400 * 30, # 30 days
            httponly=False,
            samesite="lax"
        )
        log_event("🔐 Admin logged in to control center", level="INFO")
        return {"success": True, "token": token}
    return JSONResponse(status_code=401, content={"success": False, "error": "Invalid Password"})

@app.get("/api/auth/check")
def check_auth(request: Request, authorization: Optional[str] = Header(None), hpu_auth_session: Optional[str] = Cookie(None)):
    is_valid = verify_auth(request, authorization, hpu_auth_session)
    return {"authenticated": is_valid}

@app.post("/api/auth/logout")
def logout(response: Response, hpu_auth_session: Optional[str] = Cookie(None)):
    if hpu_auth_session in ACTIVE_SESSIONS:
        ACTIVE_SESSIONS.remove(hpu_auth_session)
    response.delete_cookie("hpu_auth_session")
    return {"success": True}

@app.get("/", response_class=HTMLResponse)
def get_dashboard():
    index_path = Path(__file__).parent / "templates" / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>HPU Agent Control Center</h1>")

@app.get("/api/status")
def get_status(request: Request, authorization: Optional[str] = Header(None), hpu_auth_session: Optional[str] = Cookie(None)):
    if not verify_auth(request, authorization, hpu_auth_session):
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT count(*) FROM scraped_items")
    total_indexed = cursor.fetchone()[0]

    cursor.execute("SELECT count(*) FROM published_posts")
    published_count = cursor.fetchone()[0]

    cursor.execute("SELECT count(*) FROM batch_queue WHERE status = 'WAITING'")
    queued_count = cursor.fetchone()[0]

    try:
        cursor.execute("SELECT count(*) FROM comment_replies")
        replies_count = cursor.fetchone()[0]
    except Exception:
        replies_count = 0

    cursor.execute("""
        SELECT b.id, s.title, b.category, s.scraped_at, s.source
        FROM batch_queue b JOIN scraped_items s ON b.scraped_item_id = s.id
        WHERE b.status = 'WAITING' 
        ORDER BY 
            CASE 
                WHEN s.source LIKE 'Instagram%' THEN 1
                WHEN s.source LIKE '%News%' OR s.source LIKE '%Amar Ujala%' OR s.source LIKE '%Divya Himachal%' OR s.source LIKE '%Tribune%' THEN 2
                ELSE 3
            END ASC,
            b.enqueued_at DESC 
        LIMIT 25
    """)
    queued_rows = cursor.fetchall()
    queued_items = [{
        "id": r[0], 
        "title": r[1], 
        "category": r[2], 
        "scraped_at": r[3],
        "source": r[4] if len(r) > 4 else "Portal"
    } for r in queued_rows]

    cursor.execute("""
        SELECT id, post_type, tier, category, headline, instagram_media_id, published_at, audio_track
        FROM published_posts ORDER BY id DESC LIMIT 10
    """)
    post_rows = cursor.fetchall()
    recent_posts = [{
        "id": r[0],
        "post_type": r[1],
        "tier": r[2],
        "category": r[3],
        "headline": r[4],
        "media_id": r[5],
        "published_at": r[6],
        "audio_track": r[7],
        "url": f"https://www.instagram.com/p/{r[5]}/" if r[5] and not r[5].startswith("dry_run") else "#"
    } for r in post_rows]

    conn.close()

    # Uptime Calculation
    uptime_seconds = int(time.time() - agent_manager.start_time)
    hours, remainder = divmod(uptime_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    days, hours = divmod(hours, 24)
    if days > 0:
        uptime_str = f"{days}d {hours}h {minutes}m {seconds}s"
    else:
        uptime_str = f"{hours}h {minutes}m {seconds}s"

    # Next scheduled jobs
    next_jobs = []
    if agent_manager.is_running and agent_manager.scheduler:
        try:
            for job in sorted(agent_manager.scheduler.get_jobs(), key=lambda j: j.next_run_time or datetime.max.replace(tzinfo=timezone.utc)):
                if job.next_run_time:
                    next_jobs.append({
                        "name": job.name,
                        "next_run": job.next_run_time.strftime("%I:%M %p (%d %b)")
                    })
        except Exception:
            pass

    daily_posts = get_daily_published_count()
    import agent.config as cfg
    token_status = check_meta_token_status(cfg.INSTAGRAM_ACCESS_TOKEN)

    return {
        "status": "Running" if agent_manager.is_running else "Stopped",
        "is_running": agent_manager.is_running,
        "uptime": uptime_str,
        "uptime_seconds": uptime_seconds,
        "last_action": agent_manager.last_action,
        "instagram_handle": INSTAGRAM_HANDLE,
        "token_status": token_status,
        "total_indexed": total_indexed,
        "published_count": published_count,
        "queued_count": queued_count,
        "replies_count": replies_count,
        "daily_posts_count": daily_posts,
        "max_daily_posts": MAX_DAILY_POSTS,
        "crawl_interval_hours": CRAWL_INTERVAL_HOURS,
        "post_interval_hours": POST_INTERVAL_HOURS,
        "next_jobs": next_jobs,
        "queued_items": queued_items,
        "recent_posts": recent_posts,
        "logs": system_logs[-80:]
    }

# Agent Controls
@app.post("/api/start")
def start_scheduler_api(request: Request, authorization: Optional[str] = Header(None), hpu_auth_session: Optional[str] = Cookie(None)):
    if not verify_auth(request, authorization, hpu_auth_session):
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})
    agent_manager.start()
    return {"message": "Agent Background Scheduler Started"}

@app.post("/api/stop")
def stop_scheduler_api(request: Request, authorization: Optional[str] = Header(None), hpu_auth_session: Optional[str] = Cookie(None)):
    if not verify_auth(request, authorization, hpu_auth_session):
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})
    agent_manager.stop()
    return {"message": "Agent Background Scheduler Paused"}

@app.post("/api/restart")
def restart_scheduler_api(request: Request, authorization: Optional[str] = Header(None), hpu_auth_session: Optional[str] = Cookie(None)):
    if not verify_auth(request, authorization, hpu_auth_session):
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})
    agent_manager.restart()
    return {"message": "Agent Background Scheduler Restarted"}

class TokenUpdateRequest(BaseModel):
    token: str
    account_id: Optional[str] = None

@app.post("/api/settings/update-instagram-token")
def update_instagram_token(req: TokenUpdateRequest, request: Request, authorization: Optional[str] = Header(None), hpu_auth_session: Optional[str] = Cookie(None)):
    if not verify_auth(request, authorization, hpu_auth_session):
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    new_token = req.token.strip()
    if not new_token:
        return JSONResponse(status_code=400, content={"error": "Token cannot be empty"})

    import agent.config as cfg
    import agent.poster as pst
    cfg.INSTAGRAM_ACCESS_TOKEN = new_token
    pst.INSTAGRAM_ACCESS_TOKEN = new_token
    os.environ["INSTAGRAM_ACCESS_TOKEN"] = new_token

    global _token_cache
    _token_cache = {"valid": None, "error": None, "checked_at": 0}

    if req.account_id and req.account_id.strip():
        cfg.INSTAGRAM_ACCOUNT_ID = req.account_id.strip()
        pst.INSTAGRAM_ACCOUNT_ID = req.account_id.strip()
        os.environ["INSTAGRAM_ACCOUNT_ID"] = req.account_id.strip()

    # Update local .env
    env_file = Path(__file__).resolve().parent / ".env"
    if env_file.exists():
        content = env_file.read_text(encoding="utf-8")
        if "INSTAGRAM_ACCESS_TOKEN=" in content:
            content = re.sub(r'INSTAGRAM_ACCESS_TOKEN=.*', f'INSTAGRAM_ACCESS_TOKEN={new_token}', content)
        else:
            content += f"\nINSTAGRAM_ACCESS_TOKEN={new_token}\n"
        if req.account_id and req.account_id.strip():
            if "INSTAGRAM_ACCOUNT_ID=" in content:
                content = re.sub(r'INSTAGRAM_ACCOUNT_ID=.*', f'INSTAGRAM_ACCOUNT_ID={req.account_id.strip()}', content)
            else:
                content += f"\nINSTAGRAM_ACCOUNT_ID={req.account_id.strip()}\n"
        env_file.write_text(content, encoding="utf-8")

    # Sync to Coolify API
    coolify_token = "10|NFtP1Hcm6ltyrzQOvEfWZzcZFVDmRUKpKI7yQlUB"
    try:
        import requests
        headers = {"Authorization": f"Bearer {coolify_token}"}
        url = "http://169.58.12.127:8000/api/v1/applications/cqcddy6kofhetzhaicfwo9xc/envs"
        requests.patch(url, headers=headers, json={"key": "INSTAGRAM_ACCESS_TOKEN", "value": new_token}, timeout=5)
        if req.account_id and req.account_id.strip():
            requests.patch(url, headers=headers, json={"key": "INSTAGRAM_ACCOUNT_ID", "value": req.account_id.strip()}, timeout=5)
    except Exception as e:
        print(f"[Coolify Sync] Env sync note: {e}")

    log_event("🔑 INSTAGRAM_ACCESS_TOKEN updated successfully by Admin!", level="INFO")
    return {"success": True, "message": "Instagram Access Token updated and active!"}

@app.post("/api/crawl-now")
def trigger_crawl(background_tasks: BackgroundTasks, request: Request, authorization: Optional[str] = Header(None), hpu_auth_session: Optional[str] = Cookie(None)):
    if not verify_auth(request, authorization, hpu_auth_session):
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})
    log_event("⚡ Manual Crawl Triggered from Admin Dashboard...")
    background_tasks.add_task(safe_crawl_cycle)
    return {"message": "Multi-Source Crawl Dispatched!"}

@app.post("/api/publish-queue-now")
def trigger_queue_post(background_tasks: BackgroundTasks, request: Request, authorization: Optional[str] = Header(None), hpu_auth_session: Optional[str] = Cookie(None)):
    if not verify_auth(request, authorization, hpu_auth_session):
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})
    log_event("⚡ Manual Post Queue Triggered (No daily limit • 1-2 Reel / 3+ Carousel)...")
    background_tasks.add_task(safe_scheduled_post_cycle, False, True)
    return {"message": "Instant Queue Post Dispatched (No Daily Limit)!"}

@app.post("/api/publish-carousel-now")
def trigger_carousel(background_tasks: BackgroundTasks, request: Request, authorization: Optional[str] = Header(None), hpu_auth_session: Optional[str] = Cookie(None)):
    if not verify_auth(request, authorization, hpu_auth_session):
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})
    log_event("⚡ Manual Carousel Publish Triggered (Instant Live Post)...")
    background_tasks.add_task(safe_carousel_cycle, None, None, False, True)
    return {"message": "Instant Carousel Post Dispatched to Live Instagram!"}

@app.post("/api/publish-reel-now")
def trigger_reel(background_tasks: BackgroundTasks, request: Request, authorization: Optional[str] = Header(None), hpu_auth_session: Optional[str] = Cookie(None)):
    if not verify_auth(request, authorization, hpu_auth_session):
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})
    log_event("⚡ Manual Video Reel Publish Triggered (Instant Live Post)...")
    background_tasks.add_task(safe_reel_cycle, None, False, True)
    return {"message": "Instant Video Reel Dispatched to Live Instagram!"}

@app.post("/api/scan-comments")
def trigger_comments(background_tasks: BackgroundTasks, request: Request, authorization: Optional[str] = Header(None), hpu_auth_session: Optional[str] = Cookie(None)):
    if not verify_auth(request, authorization, hpu_auth_session):
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})
    log_event("⚡ Manual Comment Responder Triggered from Admin Dashboard...")
    background_tasks.add_task(safe_comments_cycle)
    return {"message": "Instagram Comment Responder Dispatched!"}

@app.post("/api/clear-logs")
def clear_logs(request: Request, authorization: Optional[str] = Header(None), hpu_auth_session: Optional[str] = Cookie(None)):
    if not verify_auth(request, authorization, hpu_auth_session):
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})
    global system_logs
    system_logs.clear()
    log_event("Terminal logs cleared by Admin.")
    return {"message": "Logs cleared"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
