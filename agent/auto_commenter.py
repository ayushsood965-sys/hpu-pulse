import sys
import requests
from datetime import datetime
from .config import INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_ACCOUNT_ID, GEMINI_API_KEY, GEMINI_MODEL
from .db import is_comment_replied, record_comment_reply

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

BASE_URL = "https://graph.facebook.com/v21.0"

def generate_student_reply(comment_text: str) -> str:
    """Uses Gemini 2.5 Flash to provide an empathetic, helpful student response."""
    lower = comment_text.lower()

    # Fast rules
    if "pdf" in lower or "link" in lower:
        return "You can check the full notice and download circulars directly from your student portal login! 📄"
    elif "result" in lower or "gazette" in lower:
        return "Semester gazette results are live under your student login, check your scorecards! 🎓"
    elif "admission" in lower or "merit" in lower:
        return "Check the latest merit lists and counselling cutoffs on the admission portal! 🏛"

    if GEMINI_API_KEY and not GEMINI_API_KEY.startswith("your_"):
        prompt = f"""
You are the helpful student admin for @hpu.pulse, a student community page on Instagram like @hpuupdate.
A student commented: "{comment_text}"
Provide a polite, warm, 1-sentence response like a fellow student helping them out.
DO NOT include any URLs or website domains. Keep it concise.
Do not wrap in quotes.
"""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 60}
        }
        try:
            resp = requests.post(url, json=payload, timeout=12)
            if resp.status_code == 200:
                return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip().strip('"')
        except Exception:
            pass

    return "Check your student login portal for detailed lists and roll numbers! ✨"

def process_comments():
    """Scans recent Instagram posts, detects student questions, and replies automatically."""
    if not INSTAGRAM_ACCESS_TOKEN or not INSTAGRAM_ACCOUNT_ID or INSTAGRAM_ACCESS_TOKEN.startswith("your_"):
        print("  [Auto-Commenter] Meta credentials not configured. Skipping live comment scan.")
        return

    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 💬 Scanning recent posts for student comments...")

    url = f"{BASE_URL}/{INSTAGRAM_ACCOUNT_ID}/media?fields=id,caption&limit=5&access_token={INSTAGRAM_ACCESS_TOKEN}"
    try:
        res = requests.get(url, timeout=15).json()
        posts = res.get("data", [])
    except Exception as e:
        print(f"  [Auto-Commenter] Error fetching posts: {e}")
        return

    total_replied = 0

    for post in posts:
        post_id = post["id"]
        c_url = f"{BASE_URL}/{post_id}/comments?fields=id,text,username,timestamp&access_token={INSTAGRAM_ACCESS_TOKEN}"
        try:
            c_res = requests.get(c_url, timeout=15).json()
            comments = c_res.get("data", [])
        except Exception:
            continue

        for c in comments:
            comment_id = c["id"]
            username = c.get("username", "")
            text = c.get("text", "")

            if is_comment_replied(comment_id):
                continue

            reply = generate_student_reply(text)
            reply_url = f"{BASE_URL}/{comment_id}/replies"
            payload = {"message": reply, "access_token": INSTAGRAM_ACCESS_TOKEN}
            r_res = requests.post(reply_url, data=payload, timeout=15).json()

            if "id" in r_res:
                print(f"  ✔ Replied to @{username}: \"{reply}\"")
                record_comment_reply(comment_id, post_id, username, text, reply)
                total_replied += 1

    print(f"  💬 Comment check completed. Replied to {total_replied} comments.")

if __name__ == "__main__":
    process_comments()
