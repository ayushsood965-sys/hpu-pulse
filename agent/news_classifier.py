import json
import re
import requests
from typing import Dict, Any, List
from .config import GEMINI_API_KEY, GEMINI_MODEL, OPENROUTER_API_KEY, OPENROUTER_MODELS

BADGE_MAP_TO_ENGLISH = {
    "ताज़ा अपडेट": "BREAKING NEWS",
    "ताजा अपडेट": "BREAKING NEWS",
    "परीक्षा परिणाम": "RESULT OUT",
    "परिणाम घोषित": "RESULTS DECLARED",
    "परीक्षा सूचना": "EXAM ALERT",
    "परीक्षा फॉर्म": "EXAM NOTICE",
    "प्रवेश सूचना": "ADMISSION ALERT",
    "परिसर अलर्ट": "CAMPUS ALERT",
    "अवकाश सूचना": "HOLIDAY ALERT",
    "आधिकारिक सूचना": "OFFICIAL UPDATE",
    "शोध अपडेट": "RESEARCH UPDATE",
    "नवीनतम अपडेट": "LATEST UPDATE",
    "शैक्षणिक अपडेट": "ACADEMIC UPDATE"
}

def is_hindi_text(text: str) -> bool:
    """Returns True if the text contains Devanagari characters (\u0900-\u097F)."""
    return bool(re.search(r'[\u0900-\u097F]', text or ""))

def clean_text_no_urls(text: str) -> str:
    """Strips any URLs, website domains, and media sources completely."""
    clean = re.sub(r"https?://\S+", "", text or "")
    clean = re.sub(r"(?:www\.)?(?:nexams|nadmissions|hpushimla|hpuniv)\.(?:in|ac\.in|org)", "portal", clean, flags=re.IGNORECASE)
    clean = re.sub(r"(?:source|verified from|check on):\s*[\w\.\-/]+", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\s*-\s*(?:ANI\s*News|Amar\s*Ujala|Divya\s*Himachal|The\s*Tribune|Hindustan\s*Times|Times\s*of\s*India|Indian\s*Express|Jagran|News18).*$", "", clean, flags=re.IGNORECASE)
    return clean.strip()

def translate_hindi_to_english(text: str, is_headline: bool = True) -> str:
    """
    Translates Hindi news headline or brief summary into clear, concise, professional English for students.
    Guarantees 0 Devanagari characters in returned string.
    """
    if not text or not is_hindi_text(text):
        return clean_text_no_urls(text or "").strip()

    clean_in = clean_text_no_urls(text).strip()

    # 1. Gemini Translation
    if GEMINI_API_KEY and not GEMINI_API_KEY.startswith("your_"):
        target_style = "concise, punchy news headline (max 8-10 words)" if is_headline else "concise 1-2 sentence news briefing"
        prompt = (
            f"You are a professional university news editor. Translate this Hindi text about Himachal Pradesh University (HPU Shimla) "
            f"into fluent, natural, professional English suitable for university students as a {target_style}. "
            f"Preserve examination titles, semesters, dates, and numbers accurately. "
            f"Output ONLY the English text with no quotes, notes, or explanation:\n\n{clean_in}"
        )
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 200}
        }
        try:
            resp = requests.post(url, json=payload, timeout=8)
            if resp.status_code == 200:
                res_data = resp.json()
                candidate = res_data.get("candidates", [{}])[0]
                parts = candidate.get("content", {}).get("parts", [])
                out = "\n".join([p.get("text", "") for p in parts if "text" in p]).strip()
                if out and not is_hindi_text(out):
                    return out.strip('"').strip("'")
        except Exception:
            pass

    # 2. OpenRouter Fallback
    if OPENROUTER_API_KEY and not OPENROUTER_API_KEY.startswith("your_"):
        for model in OPENROUTER_MODELS[:2]:
            try:
                res = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": f"Translate this Hindi news about Himachal Pradesh University to concise English: {clean_in}. Output only English."}],
                        "temperature": 0.2
                    },
                    timeout=8
                )
                if res.status_code == 200:
                    out = res.json()["choices"][0]["message"]["content"].strip()
                    if out and not is_hindi_text(out):
                        return out.strip('"').strip("'")
            except Exception:
                continue

    # 3. Rule-based / academic dictionary fallback
    t = clean_in
    subs = [
        (r'हिमाचल प्रदेश विश्वविद्यालय|हिमाचल विश्वविद्यालय|एचपीयू|वि\.वि\.|विवि', 'HPU'),
        (r'समरहिल परिसर|समरहिल', 'Summerhill Campus'),
        (r'परीक्षा परिणाम|परिणाम घोषित|परिणाम', 'Results Declared'),
        (r'परीक्षाएं|परीक्षाओं|परीक्षा', 'Examinations'),
        (r'प्रवेश परीक्षा|प्रवेश प्रक्रिया|प्रवेश', 'Admissions'),
        (r'अधिसूचना जारी|अधिसूचना', 'Official Notification Released'),
        (r'सत्र|सेमेस्टर', 'Semester'),
        (r'छात्रों|छात्र संघ|छात्र', 'Students'),
        (r'मेरिट सूची', 'Merit List'),
        (r'डेटशीट जारी|डेटशीट', 'Datesheet Released'),
        (r'आवेदन की अंतिम तिथि|अंतिम तिथि', 'Application Deadline'),
        (r'शुल्क|फीस', 'Fee'),
        (r'अवकाश|छुट्टी', 'Holiday Announcement'),
        (r'स्थगित', 'Postponed'),
        (r'जारी किया शेड्यूल|शेड्यूल', 'Schedule Announced'),
        (r'विश्वविद्यालय प्रशासन', 'University Administration'),
        (r'कुलपति', 'Vice Chancellor'),
    ]
    for pattern, rep in subs:
        t = re.sub(pattern, rep, t, flags=re.IGNORECASE)

    # Strip remaining Devanagari characters
    t = re.sub(r'[\u0900-\u097F]+', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    if len(t) < 8:
        return "HPU University Notice & Campus Update" if is_headline else "Official circular issued by university administration on student portal."
    return t

def translate_news_to_english_points(title: str, summary: str) -> tuple[str, list[str]]:
    """
    Translates Hindi news (from newspapers/competitors/portal) into a punchy English headline and 2-3 concise English bullet points.
    """
    clean_t = clean_text_no_urls(title)
    clean_s = clean_text_no_urls(summary)

    en_title = translate_hindi_to_english(clean_t, is_headline=True)

    if GEMINI_API_KEY and not GEMINI_API_KEY.startswith("your_"):
        prompt = (
            f"You are an editor for HPU student community @hpu.pulse. Synthesize this university news into:\n"
            f"1. A punchy English headline (max 9 words).\n"
            f"2. Exactly 2 to 3 concise English bullet points explaining the core details for students (max 16 words each).\n\n"
            f"Notice Title: {clean_t}\n"
            f"Details: {clean_s[:600]}\n\n"
            f"Return JSON strictly formatted as:\n"
            f'{{"headline": "...", "points": ["...", "..."]}}'
        )
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 300}
        }
        try:
            resp = requests.post(url, json=payload, timeout=8)
            if resp.status_code == 200:
                res_data = resp.json()
                candidate = res_data.get("candidates", [{}])[0]
                parts = candidate.get("content", {}).get("parts", [])
                raw_out = "\n".join([p.get("text", "") for p in parts if "text" in p])
                parsed = extract_json_from_response(raw_out)
                if parsed and parsed.get("headline") and parsed.get("points"):
                    h = parsed["headline"].strip()
                    pts = [p.strip() for p in parsed["points"] if p.strip()]
                    if not is_hindi_text(h) and not any(is_hindi_text(p) for p in pts):
                        return h, pts
        except Exception:
            pass

    # Fallback points
    en_summary = translate_hindi_to_english(clean_s, is_headline=False) if clean_s else ""
    pts = []
    if en_summary:
        raw_splits = [p.strip() for p in re.split(r'[.\n|]', en_summary) if len(p.strip()) > 15]
        pts = raw_splits[:3]
    if not pts:
        pts = [
            "Official notification released on the university student portal.",
            "Students can check individual details through their portal login.",
            "Contact departmental administration for further guidelines."
        ]
    return en_title, pts

def extract_json_from_response(text: str) -> dict:
    """Extracts JSON block from model response, handling nested structures and code fences."""
    try:
        clean = text.strip()
        # Clean any markdown code blocks
        clean = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.MULTILINE)
        clean = re.sub(r"\s*```$", "", clean, flags=re.MULTILINE).strip()
        first_brace = clean.find("{")
        last_brace = clean.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            json_str = clean[first_brace:last_brace + 1]
            return json.loads(json_str)
        return json.loads(clean)
    except Exception as e:
        return {}

def sanitize_language_consistency(parsed: dict, is_hindi: bool, fallback_title: str) -> dict:
    """
    Enforces strict English consistency for all carousel and post data.
    Guarantees 0 Devanagari text in headline, badge, slides, key_points, and caption.
    """
    if not parsed or not isinstance(parsed, dict):
        return parsed

    # 1. Enforce English Badge
    badge = parsed.get("badge", "")
    if is_hindi_text(badge):
        upper_b = badge.upper()
        matched = False
        for hin_k, eng_v in BADGE_MAP_TO_ENGLISH.items():
            if hin_k in upper_b or hin_k in badge:
                parsed["badge"] = eng_v
                matched = True
                break
        if not matched:
            parsed["badge"] = "CAMPUS UPDATE"

    # 2. Enforce English Headline
    headline = parsed.get("headline", "")
    if is_hindi_text(headline):
        parsed["headline"] = translate_hindi_to_english(headline, is_headline=True)

    # 3. Enforce English Key Points
    if "key_points" in parsed and isinstance(parsed["key_points"], list):
        clean_pts = []
        for pt in parsed["key_points"]:
            if is_hindi_text(str(pt)):
                clean_pts.append(translate_hindi_to_english(str(pt), is_headline=False))
            else:
                clean_pts.append(str(pt))
        parsed["key_points"] = clean_pts

    # 4. Enforce English Slides
    if "slides" in parsed and isinstance(parsed["slides"], list):
        for idx, s in enumerate(parsed["slides"]):
            if not isinstance(s, dict):
                continue
            if idx == 0:
                if is_hindi_text(s.get("title", "")):
                    s["title"] = translate_hindi_to_english(s.get("title", ""), is_headline=True)
                if is_hindi_text(s.get("subtitle", "")):
                    s["subtitle"] = translate_hindi_to_english(s.get("subtitle", ""), is_headline=False)
                if is_hindi_text(s.get("badge", "")):
                    s["badge"] = parsed.get("badge", "CAMPUS UPDATE")
            else:
                heading = s.get("heading", "")
                if is_hindi_text(heading):
                    s["heading"] = translate_hindi_to_english(heading, is_headline=True)
                if "points" in s and isinstance(s["points"], list):
                    s_pts = []
                    for pt in s["points"]:
                        if is_hindi_text(str(pt)):
                            s_pts.append(translate_hindi_to_english(str(pt), is_headline=False))
                        else:
                            s_pts.append(str(pt))
                    s["points"] = s_pts

    # 5. Enforce English Caption
    caption = parsed.get("caption", "")
    if is_hindi_text(caption):
        h = parsed.get("headline", "HPU University Update")
        b = parsed.get("badge", "CAMPUS UPDATE")
        pts = parsed.get("key_points", [])
        pts_str = "\n".join([f"• {p}" for p in pts[:4]])
        parsed["caption"] = (
            f"📢 {b}: {h}\n\n"
            f"Here is what students need to know:\n"
            f"{pts_str}\n\n"
            f"Check your student portal for individual scorecards and schedules.\n"
            f"Tag your batchmates below! 👇\n\n"
            f"#hpu #hpushimla #hpuupdates #hpuresult #hpuexams #himachalpradeshuniversity #shimla"
        )

    return parsed

    return parsed

def classify_and_synthesize_update(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Synthesizes raw university notices into human-style student updates like @hpuupdate.
    - Zero website links or sources
    - Highly concise, knowledgeable, student-friendly tone
    - Clean readable bullet points
    - Strict Language Parity: Hindi source -> 100% Hindi card & caption; English source -> 100% English.
    """
    title = clean_text_no_urls(item.get("title") or "")
    raw_text = clean_text_no_urls(item.get("raw_text") or "")
    ocr_text = clean_text_no_urls(item.get("ocr_text") or "")
    summary = clean_text_no_urls(item.get("summary") or "")
    notice_date = item.get("notice_date") or "Latest Update"
    source = item.get("source") or "Portal"
    is_instagram = "instagram" in source.lower()

    # Determine language from all available content
    combined_source = f"{title} {raw_text} {ocr_text} {summary}"
    is_hindi = is_hindi_text(combined_source)

    ig_directive = ""
    if is_instagram:
        ig_directive = f"""
NOTE: This update was posted by student community account '{source}'.
Directly adapt and rephrase this update into our own original, authoritative voice for @hpu.pulse.
Preserve the exact examination names, semesters, dates, and instructions, but express them in a crisp, clean student-friendly manner.
DO NOT mention or credit any other Instagram page or source.
"""

    lang_mandate = """
CRITICAL LANGUAGE MANDATE:
ALL OUTPUTS MUST BE 100% IN ENGLISH.
Even if the source notice, newspaper article (e.g. Amar Ujala, Divya Himachal, The Tribune), or competitor Instagram/Telegram post is written in Hindi (Devanagari script), you MUST translate and synthesize all headlines, badges, subtitles, bullet points, summaries, and captions strictly into clear, professional ENGLISH.
ABSOLUTELY NO HINDI (DEVANAGARI) SCRIPT OR HINDI WORDS IN THE OUTPUT.
- 'headline': Short, punchy headline in ENGLISH (max 7-8 words).
- 'badge': Short uppercase category tag in ENGLISH (e.g. "BREAKING NEWS", "RESULT OUT", "EXAM ALERT", "ADMISSION UPDATE").
- 'key_points': ALL 3-4 bullet points MUST BE IN ENGLISH.
- 'slides': Slide titles, subtitles, headings, and bullet points MUST ALL BE IN ENGLISH.
- 'caption': Instagram caption MUST BE 100% IN ENGLISH.
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
{lang_mandate}
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
3. Headline: Short, punchy, maximum 7-8 words in ENGLISH.
4. KEY POINTS (3 to 4 points in ENGLISH, max 18-20 words each):
   - Point 1: Core development (What happened)
   - Point 2: Specific Location & Timing (Where and When)
   - Point 3: Reasons, student demands, or criteria (Why)
   - Point 4: Action required / student impact (Next steps)
5. Carousel Slides (2 to 4 slides in ENGLISH):
   - Slide 1 (Cover): Punchy title + short subtitle + badge
   - Slide 2: Heading + 2-3 detailed bullet points
   - Slide 3: Heading + 2-3 detailed bullet points
   - Slide 4: Heading + Actionable guidance for students

Return ONLY a valid JSON object matching this schema:
{{
  "tier": "TIER1_BREAKING" or "TIER2_ROUTINE",
  "category": "EXAM" or "RESULT" or "ADMISSION" or "HOLIDAY" or "GENERAL",
  "badge": "...",
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
                        for s in parsed["slides"]:
                            if s.get("points"):
                                parsed["key_points"] = s["points"]
                                break
                    return sanitize_language_consistency(parsed, is_hindi, title)
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
                        return sanitize_language_consistency(parsed, is_hindi, title)
            except Exception:
                continue

    # Clean Fallback with real context extraction in 100% English
    is_breaking = item.get("priority") == "TIER1_BREAKING"
    badge = "BREAKING NEWS" if is_breaking else "OFFICIAL UPDATE"
    
    # Translate headline if in Hindi
    if is_hindi_text(title):
        en_title = translate_hindi_to_english(title, is_headline=True)
    else:
        en_title = title[:60] or "HPU University Notice"

    desc_clean = clean_text_no_urls(summary or raw_text or "")
    if is_hindi_text(desc_clean):
        desc_clean = translate_hindi_to_english(desc_clean, is_headline=False)

    where_match = re.search(r"(?:at|in|near)\s+([A-Z][a-zA-Z\s]{3,25}(?:Campus|Secretariat|Office|Auditorium|Lawns|Shimla|Summerhill))", desc_clean)
    location_str = where_match.group(0) if where_match else "HPU Summerhill Campus"

    points = [
        f"{en_title[:80]}",
        f"Location: {location_str} | Date: {notice_date}",
        "Details: Check your student login account for full departmental instructions",
        "Save this post & share with your classmates to stay updated"
    ]

    return {
        "tier": "TIER1_BREAKING" if is_breaking else "TIER2_ROUTINE",
        "category": item.get("category", "GENERAL"),
        "badge": badge,
        "headline": en_title,
        "audio_track_id": "cornfield_chase" if is_breaking else "reflections",
        "key_points": points,
        "slides": [
            {"title": en_title, "subtitle": f"Date: {notice_date}", "badge": badge},
            {"heading": "What You Need to Know", "points": points[:2]},
            {"heading": "Key Details & Action", "points": points[2:]}
        ],
        "caption": (
            f"📢 {badge}: {en_title}\n\n"
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
    Combines multiple routine circulars into a single clean human-style carousel in 100% English like @hpuupdates.
    Zero URLs, concise points, knowledgeable tone.
    """
    if not items:
        return {}

    first = items[0]
    category = first.get("category", "ACADEMIC")

    # Detect if bundle items are in Hindi
    combined_bundle_text = " ".join([
        f"{it.get('title', '')} {it.get('raw_text', '')} {it.get('ocr_text', '')} {it.get('summary', '')}"
        for it in items
    ])
    is_hindi = is_hindi_text(combined_bundle_text)
    
    # Format items for prompt with translation if needed
    notices_formatted = []
    for idx, it in enumerate(items[:4], 1):
        clean_t = clean_text_no_urls(it.get("title", ""))
        clean_c = clean_text_no_urls(it.get("raw_text", "") or it.get("ocr_text", "") or "")[:200]
        notices_formatted.append(f"{idx}. Title: {clean_t}\n   Details: {clean_c}")

    lang_mandate = f"""
CRITICAL LANGUAGE MANDATE:
ALL OUTPUTS MUST BE 100% IN ENGLISH.
Even if the source notices are written in HINDI (e.g. from regional newspapers like Amar Ujala / Divya Himachal or Telegram channels), you MUST translate and write 100% of all fields in ENGLISH:
- Slide 1 (Cover): "title", "subtitle", "badge" in ENGLISH.
- Detail Slides: "heading" and "points" in ENGLISH.
- Last Slide: "heading": "Important Note", "points" in ENGLISH.
- 'headline': In ENGLISH.
- 'caption': Must be 100% in ENGLISH.
ABSOLUTELY NO HINDI (DEVANAGARI) HEADINGS, BADGES, OR BULLETS.
"""

    prompt = f"""
You are the student creator behind '@hpu.pulse', an authentic student community page like @hpuupdates.
Synthesize and rephrase these university notices into an easy-to-read, concise Instagram carousel album.

Notices to summarize:
{chr(10).join(notices_formatted)}

STRICT USER RULES:
{lang_mandate}
1. NEVER mention any URLs, website domains, download links, or source citations (DO NOT mention 'hpushimla.in', 'nexams', 'nadmissions', 'Source: ...'). If referring to where to check, say "Available via student login" or "Check on the student portal".
2. Tone: Friendly, concise, knowledgeable, written by a human student admin just like @hpuupdates.
3. Carousel Slides structure (100% English):
   - Slide 1 (Cover): Punchy title + short subtitle + category badge
   - Next 2-3 Slides: Short heading + 2 to 3 concise, highly readable bullet points explaining what happened, who is affected, and what action to take (max 15 words per bullet). No emojis.
   - Last Slide: Summary guidance / Important Note
4. Instagram Caption:
   - Engaging hook in English
   - Clean bullet list of what was declared/released
   - Call to action ("Tag your classmates below 👇")
   - Relevant hashtags (#hpu #hpushimla #hpuupdates #hpuresults #hpuexams #himachalpradeshuniversity #shimla)
   - ZERO URLs or sources.

Return ONLY a valid JSON object matching this schema:
{{
  "tier": "TIER2_ROUTINE",
  "category": "{category}",
  "badge": "...",
  "headline": "...",
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
                    return sanitize_language_consistency(parsed, is_hindi, items[0].get("title", ""))
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
                        return sanitize_language_consistency(parsed, is_hindi, items[0].get("title", ""))
            except Exception:
                continue

    # English Routine Fallback (Strictly English)
    en_titles = []
    for it in items:
        raw_t = clean_text_no_urls(it.get("title", ""))
        if is_hindi_text(raw_t):
            en_titles.append(translate_hindi_to_english(raw_t, is_headline=True))
        else:
            en_titles.append(raw_t)

    slides = [
        {
            "title": f"HPU {category} UPDATES",
            "subtitle": f"{len(items)} Important Notices Released",
            "badge": f"{category} UPDATES"
        }
    ]

    for idx, (it, en_t) in enumerate(zip(items[:3], en_titles[:3]), start=1):
        slides.append({
            "heading": f"Update {idx}: {it.get('category', 'Notice')}",
            "points": [
                en_t[:70],
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
        "\n".join([f"• {t[:85]}" for t in en_titles[:4]]) +
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
