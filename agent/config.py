import os
from pathlib import Path
from dotenv import load_dotenv

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "generated_cards"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

AUDIO_DIR = BASE_DIR / "agent" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# Load environment variables
load_dotenv(BASE_DIR / ".env")

# Meta & Instagram Graph API
INSTAGRAM_ACCESS_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN", "").strip()
INSTAGRAM_ACCOUNT_ID = os.getenv("INSTAGRAM_ACCOUNT_ID", "").strip()
INSTAGRAM_HANDLE = os.getenv("INSTAGRAM_HANDLE", "@hpu.updates").strip()
PAGE_ID = os.getenv("PAGE_ID", "").strip()

# AI Engines
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash").strip()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODELS = [
    "minimax/minimax-m3.1-flash:free",
    "nvidia/nemotron-3.5-lightning:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free"
]

# Media Hosting
IMGBB_API_KEY = os.getenv("IMGBB_API_KEY", "").strip()
SERVER_URL = os.getenv("SERVER_URL", "http://localhost:8000").rstrip("/")

# Crawler & Scheduler (6h crawl, 12h post, max 2 daily posts)
CRAWL_INTERVAL_HOURS = int(os.getenv("CRAWL_INTERVAL_HOURS", "6"))
CRAWL_INTERVAL_MINUTES = int(os.getenv("CRAWL_INTERVAL_MINUTES", str(CRAWL_INTERVAL_HOURS * 60)))
POST_INTERVAL_HOURS = int(os.getenv("POST_INTERVAL_HOURS", "12"))
MAX_DAILY_POSTS = int(os.getenv("MAX_DAILY_POSTS", "2"))
ROUTINE_BATCH_INTERVAL_HOURS = float(os.getenv("ROUTINE_BATCH_INTERVAL_HOURS", "12"))
TIMEZONE = os.getenv("TIMEZONE", "Asia/Kolkata")
DB_PATH = BASE_DIR / "agent_data.db"

# Curated Reels Directory & Pipeline Settings
CURATED_REELS_DIR = OUTPUT_DIR / "curated_reels"
CURATED_REELS_DIR.mkdir(parents=True, exist_ok=True)

MAX_DAILY_REEL_UPLOADS = int(os.getenv("MAX_DAILY_REEL_UPLOADS", "15"))
REELS_LOOKBACK_DAYS = int(os.getenv("REELS_LOOKBACK_DAYS", "3"))
REELS_DATE_CUTOFF = os.getenv("REELS_DATE_CUTOFF", "2026-10-25")
DAILY_CAROUSEL_TIME = os.getenv("DAILY_CAROUSEL_TIME", "19:00")

# Target Instagram Handles for Reels Curation (Categories 1 to 4)
TARGET_REEL_HANDLES = [
    # Category 1: News, Circulars & Exam Alert Pages
    "hpuupdate", "hpudailyupdates", "hpushimla_official", "hpu_shimla_",
    "himachal_pradesh_university", "hpuexamupdates", "hpu_bulletin",
    "hpu_alerts", "hpu_hub", "scholarhubhpu",

    # Category 2: Student Organizations & Political Wings
    "abvp_hpu_unit", "abvp4hpu", "sfihpu", "sfihpu_shimla",
    "nsui.hpu.shimla", "nsui_hpu_official", "scahpu", "abvp_summerhill",
    "sfi_summerhill", "hpu_student_union",

    # Category 3: Departmental & Professional Wings
    "uit_hpu", "uit_shimla", "uils_hpu", "uils_shimla",
    "hpubs_shimla", "hpulawdept", "hpu_journalism", "hpu_biotech",
    "hpu_sports", "hpurc_dharamshala",

    # Category 4: Campus Life, Culture & Video Reels Creators
    "hpu_diaries", "hpushimladiaries", "summerhill_diaries", "hpu_vibes",
    "hpu_talks", "hpu_buzz", "hpu_confessions", "hpu_memes",
    "hpu_youth_festival", "summerhill_shimla"
]
