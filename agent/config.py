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

# Crawler & Scheduler
CRAWL_INTERVAL_MINUTES = int(os.getenv("CRAWL_INTERVAL_MINUTES", "30"))
ROUTINE_BATCH_INTERVAL_HOURS = float(os.getenv("ROUTINE_BATCH_INTERVAL_HOURS", "1.5"))
TIMEZONE = os.getenv("TIMEZONE", "Asia/Kolkata")
DB_PATH = BASE_DIR / "agent_data.db"
