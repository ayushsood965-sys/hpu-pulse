import json
import re
import requests
from typing import Dict, Any, List
from .config import GEMINI_API_KEY, GEMINI_MODEL, OPENROUTER_API_KEY, OPENROUTER_MODELS

def extract_json_from_response(text: str) -> dict:
    """Extracts JSON block from model response, handling nested structures and code fences."""
    try:
        clean = text.strip()
        first_brace = clean.find("{")
        last_brace = clean.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            json_str = clean[first_brace:last_brace + 1]
            return json.loads(json_str)
        return json.loads(clean)
    except Exception as e:
        print(f"[AI Triage] JSON parse fallback: {e}")
        return {}

def clean_text_no_urls(text: str) -> str:
    """Strips any URLs, website domains, and media sources completely."""
    clean = re.sub(r"https?://\S+", "", text)
    clean = re.sub(r"(?:www\.)?(?:nexams|nadmissions|hpushimla|hpuniv)\.(?:in|ac\.in|org)", "portal", clean, flags=re.IGNORECASE)
    clean = re.sub(r"(?:source|verified from|check on):\s*[\w\.\-/]+", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\s*-\s*(?:ANI\s*News|Amar\s*Ujala|Divya\s*Himachal|The\s*Tribune|Hindustan\s*Times|Times\s*of\s*India|Indian\s*Express|Jagran|News18).*$", "", clean, flags=re.IGNORECASE)
    return clean.strip()

def classify_and_synthesize_update(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Synthesizes raw university notices into human-style student updates like @hpuupdate.
    - Zero website links or sources
    - Highly concise, knowledgeable, student-friendly tone
    - Clean readable bullet points
    """
    title = clean_text_no_urls(item.get("title") or "")
    raw_text = clean_text_no_urls(item.get("raw_text") or "")
    ocr_text = clean_text_no_urls(item.get("ocr_text") or "")
    notice_date = item.get("notice_date") or "Latest Update"
    source = item.get("source") or "Portal"
    is_instagram = "instagram" in source.lower()

    ig_directive = ""
    if is_instagram:
        ig_directive = f"""
NOTE: This update was posted by student community account '{source}'.
Directly adapt and rephrase this update into our own original, authoritative voice for @hpu.pulse.
Preserve the exact examination names, semesters, dates, and instructions, but express them in a crisp, clean student-friendly manner.
DO NOT mention or credit any other Instagram page or source.
"""

    prompt = f"""
You are the student creator behind '@hpu.pulse', an authentic, highly respected student community page like @hpuupdate.
Rephrase and synthesize this university update into an authoritative, informative post for students.
{ig_directive}
Notice Content:
- Title: {title}
- Source: {source}
- Date: {notice_date}
- Content: {raw_text[:700]}
- Circular Details: {ocr_text[:700]}

STRICT USER MANDATES:
1. ZERO ULTRA-VAGUE POSTS:
   Never write generic statements like "Protest held on campus" or "Examination notice released".
   You MUST extract and include specific context:
   - WHAT: Exactly what happened or was officially declared.
   - WHERE: Specific location (e.g. Summerhill Campus, VC Office, Pink Petals, Law Auditorium, or specific colleges/districts).
   - WHEN: Exact date/time (e.g. Today morning, scheduled for tomorrow, application deadline date).
   - WHY / REASON: The core reason, demands, or background (e.g. protesting hostel room shortages, fee hike rollback, re-evaluation delay, syllabus completion, etc.).
   - ACTION / IMPACT: What students need to do, deadline to note, or admin response.
2. NO URLS OR WEBSITE LINKS:
   Never mention 'hpushimla.in', 'nexams', 'Download link', 'Source: ...'. Say "Available via student login" or "Check on the student portal".
3. Headline: Short, punchy, maximum 7 words (e.g. "SFI Protests at VC Office Over Hostels", "B.Sc 2nd Sem Results Declared").
4. KEY POINTS (3 to 4 points, max 18-20 words each):
   - Point 1: Core development (What happened)
   - Point 2: Specific Location & Timing (Where and When)
   - Point 3: Reasons, student demands, or criteria (Why)
   - Point 4: Action required / student impact (Next steps)
5. Carousel Slides (2 to 4 slides):
   - Slide 1 (Cover): Punchy title + short subtitle + badge
   - Slide 2: "What Happened" (2-3 detailed bullet points)
   - Slide 3: "Key Reasons & Details" (2-3 detailed bullet points with Where/When/Why)
   - Slide 4: "Next Steps" (Actionable guidance for students)

Return ONLY a valid JSON object matching this schema:
{{
  "tier": "TIER1_BREAKING" or "TIER2_ROUTINE",
  "category": "EXAM" or "RESULT" or "ADMISSION" or "HOLIDAY" or "GENERAL",
  "badge": "BREAKING NEWS" or "RESULT OUT" or "EXAM ALERT" or "ADMISSION UPDATE" or "CAMPUS ALERT",
  "headline": "...",
  "audio_track_id": "...",
  "key_points": [
    "...",
    "...",
    "..."
  ],
  "slides": [
    {{"title": "...", "subtitle": "...", "badge": "..."}},
    {{"heading": "...", "points": ["...", "..."]}},
    {{"heading": "...", "points": ["...", "..."]}}
  ],
  "caption": "..."
}}
"""

    if GEMINI_API_KEY and not GEMINI_API_KEY.startswith("your_"):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.4, "maxOutputTokens": 1000}
        }
        try:
            resp = requests.post(url, json=payload, timeout=25)
            if resp.status_code == 200:
                res_data = resp.json()
                candidate = res_data.get("candidates", [{}])[0]
                parts = candidate.get("content", {}).get("parts", [])
                raw_out = "\n".join([p.get("text", "") for p in parts if "text" in p])
                parsed = extract_json_from_response(raw_out)
                if parsed and "headline" in parsed:
                    if not parsed.get("key_points") and parsed.get("slides"):
                        # Extract key points from first slide with points
                        for s in parsed["slides"]:
                            if s.get("points"):
                                parsed["key_points"] = s["points"]
                                break
                    return parsed
        except Exception as e:
            print(f"[AI Triage] Gemini API warning: {e}")

    # OpenRouter Fallback
    if OPENROUTER_API_KEY and not OPENROUTER_API_KEY.startswith("your_"):
        for model in OPENROUTER_MODELS:
            try:
                res = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
                    json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.4},
                    timeout=20
                )
                if res.status_code == 200:
                    raw_out = res.json()["choices"][0]["message"]["content"]
                    parsed = extract_json_from_response(raw_out)
                    if parsed and "headline" in parsed:
                        if not parsed.get("key_points") and parsed.get("slides"):
                            for s in parsed["slides"]:
                                if s.get("points"):
                                    parsed["key_points"] = s["points"]
                                    break
                        return parsed
            except Exception:
                continue

    # Clean Fallback with real context extraction
    is_breaking = item.get("priority") == "TIER1_BREAKING"
    badge = "BREAKING NEWS" if is_breaking else "OFFICIAL UPDATE"
    headline = title[:50] or "HPU University Notice"

    # Contextual extraction from available text
    desc_clean = clean_text_no_urls(item.get("summary") or raw_text or "")
    where_match = re.search(r"(?:at|in|near)\s+([A-Z][a-zA-Z\s]{3,25}(?:Campus|Secretariat|Office|Auditorium|Lawns|Shimla|Summerhill))", desc_clean)
    location_str = where_match.group(0) if where_match else "HPU Summerhill Campus"

    points = [
        f"{title[:80]}",
        f"Location: {location_str} | Date: {notice_date}",
        "Details: Check your student login account for full departmental instructions",
        "Save this post & share with your classmates to stay updated"
    ]

    return {
        "tier": "TIER1_BREAKING" if is_breaking else "TIER2_ROUTINE",
        "category": item.get("category", "GENERAL"),
        "badge": badge,
        "headline": headline,
        "audio_track_id": "cornfield_chase" if is_breaking else "reflections",
        "key_points": points,
        "slides": [
            {"title": headline, "subtitle": f"Date: {notice_date}", "badge": badge},
            {"heading": "What You Need to Know", "points": points[:2]},
            {"heading": "Key Details & Action", "points": points[2:]}
        ],
        "caption": (
            f"📢 {badge}: {headline}\n\n"
            f"Here is what students need to know:\n"
            f"• {points[0]}\n"
            f"• {points[1]}\n"
            f"• {points[2]}\n\n"
            f"Check your student portal for individual scorecards and schedules.\n"
            f"Tag your batchmates below! 👇\n\n"
            f"#hpu #hpushimla #hpuupdates #hpuresult #hpuexams #himachalpradeshuniversity #shimla"
        )
    }

def bundle_routine_carousels(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Combines multiple routine circulars into a single clean human-style carousel like @hpuupdates.
    Zero URLs, concise points, knowledgeable tone.
    """
    if not items:
        return {}

    first = items[0]
    category = first.get("category", "ACADEMIC")
    
    # Format items for prompt
    notices_formatted = []
    for idx, it in enumerate(items[:4], 1):
        clean_t = clean_text_no_urls(it.get("title", ""))
        clean_c = clean_text_no_urls(it.get("raw_text", "") or it.get("ocr_text", "") or "")[:200]
        notices_formatted.append(f"{idx}. Title: {clean_t}\n   Details: {clean_c}")

    prompt = f"""
You are the student creator behind '@hpu.pulse', an authentic student community page like @hpuupdates.
Synthesize and rephrase these university notices into an easy-to-read, concise Instagram carousel album.

Notices to summarize:
{chr(10).join(notices_formatted)}

STRICT USER RULES:
1. NEVER mention any URLs, website domains, download links, or source citations (DO NOT mention 'hpushimla.in', 'nexams', 'nadmissions', 'Source: ...'). If referring to where to check, say "Available via student login" or "Check on the student portal".
2. Tone: Friendly, concise, knowledgeable, written by a human student admin just like @hpuupdates.
3. Carousel Slides structure:
   - Slide 1 (Cover):
     "title": Punchy, clear cover title (e.g. "HPU RESULT UPDATES", "UG & PG DATE SHEETS OUT", "ADMISSION COUNSELING SCHEDULE")
     "subtitle": Short one-line summary (e.g. "Latest Semester & Examination Circulars")
     "badge": Short uppercase tag without emojis (e.g. "RESULTS DECLARED", "EXAM NOTICE", "ADMISSION ALERT")
   - Next 2-3 Slides:
     "heading": Short title for that notice / group (e.g. "B.Sc & B.Com 2nd Sem Results", "Re-evaluation Window")
     "points": 2 to 3 concise, highly readable bullet points explaining what happened, who is affected, and what action to take (max 15 words per bullet). No emojis.
   - Last Slide:
     "heading": "Important Note"
     "points": ["Check your student login for detailed scorecards", "Save this post for reference", "Share with batchmates"]
4. Instagram Caption:
   - Engaging hook (e.g. "Important update for HPU students! 📢")
   - Clean bullet list of what was declared/released
   - Call to action ("Tag your classmates below 👇")
   - Relevant hashtags (#hpu #hpushimla #hpuupdates #hpuresults #hpuexams #himachalpradeshuniversity #shimla)
   - ZERO URLs or sources.

Return ONLY a valid JSON object matching this schema:
{{
  "tier": "TIER2_ROUTINE",
  "category": "{category}",
  "badge": "RESULTS DECLARED" or "EXAM NOTICE" or "ADMISSION ALERT",
  "headline": "HPU Latest Updates",
  "slides": [
    {{"title": "...", "subtitle": "...", "badge": "..."}},
    {{"heading": "...", "points": ["...", "..."]}},
    {{"heading": "...", "points": ["...", "..."]}}
  ],
  "caption": "..."
}}
"""

    if GEMINI_API_KEY and not GEMINI_API_KEY.startswith("your_"):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.4, "maxOutputTokens": 1000}
        }
        try:
            resp = requests.post(url, json=payload, timeout=25)
            if resp.status_code == 200:
                res_data = resp.json()
                candidate = res_data.get("candidates", [{}])[0]
                parts = candidate.get("content", {}).get("parts", [])
                raw_out = "\n".join([p.get("text", "") for p in parts if "text" in p])
                parsed = extract_json_from_response(raw_out)
                if parsed and "slides" in parsed:
                    return parsed
        except Exception as e:
            print(f"[AI Triage] Gemini bundle carousel warning: {e}")

    # OpenRouter High-Speed Fallback
    if OPENROUTER_API_KEY and not OPENROUTER_API_KEY.startswith("your_"):
        for model in OPENROUTER_MODELS:
            try:
                res = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
                    json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.4},
                    timeout=15
                )
                if res.status_code == 200:
                    raw_out = res.json()["choices"][0]["message"]["content"]
                    parsed = extract_json_from_response(raw_out)
                    if parsed and "slides" in parsed:
                        return parsed
            except Exception:
                continue

    # Fallback if AI unavailable
    titles = [clean_text_no_urls(it.get("title", "")) for it in items]
    slides = [
        {
            "title": f"HPU {category} UPDATES",
            "subtitle": f"{len(items)} Important Notices Released",
            "badge": f"{category} UPDATES"
        }
    ]

    for idx, it in enumerate(items[:3], start=1):
        clean_t = clean_text_no_urls(it.get("title", ""))
        slides.append({
            "heading": f"Update {idx}: {it.get('category', 'Notice')}",
            "points": [
                clean_t[:70],
                "Check your student login portal for detailed lists",
                "Ensure to submit any applications before deadlines"
            ]
        })

    slides.append({
        "heading": "Important Note",
        "points": [
            "Check all details under your student portal login",
            "Save this post so you don't lose it",
            "Share with your batchmates who need this"
        ]
    })

    caption = (
        f"📢 HPU {category} UPDATES!\n\n"
        f"Here are the latest notices released today:\n" +
        "\n".join([f"• {t[:85]}" for t in titles[:4]]) +
        f"\n\nCheck your student account for individual marks & forms.\n"
        f"Tag your friends who need to see this! 👇\n\n"
        f"#hpu #hpushimla #hpuupdates #hpuresults #hpuexams #himachalpradeshuniversity #shimla"
    )

    return {
        "tier": "TIER2_ROUTINE",
        "category": category,
        "badge": f"{category} OUT",
        "headline": f"HPU {category} Updates ({len(items)} Notices)",
        "slides": slides,
        "caption": caption
    }
