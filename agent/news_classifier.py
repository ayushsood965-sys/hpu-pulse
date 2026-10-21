import json
import re
import requests
from typing import Dict, Any, List
from .config import GEMINI_API_KEY, GEMINI_MODEL, OPENROUTER_API_KEY, OPENROUTER_MODELS

BADGE_MAP_TO_HINDI = {
    "BREAKING NEWS": "ताज़ा अपडेट",
    "BREAKING": "ताज़ा अपडेट",
    "RESULT OUT": "परीक्षा परिणाम",
    "RESULTS DECLARED": "परीक्षा परिणाम",
    "RESULT": "परीक्षा परिणाम",
    "EXAM ALERT": "परीक्षा सूचना",
    "EXAM NOTICE": "परीक्षा सूचना",
    "EXAM": "परीक्षा सूचना",
    "ADMISSION ALERT": "प्रवेश सूचना",
    "ADMISSION UPDATE": "प्रवेश सूचना",
    "ADMISSION": "प्रवेश सूचना",
    "CAMPUS ALERT": "परिसर अलर्ट",
    "HOLIDAY": "अवकाश सूचना",
    "OFFICIAL UPDATE": "आधिकारिक सूचना",
    "UPDATE": "आधिकारिक सूचना",
}

CATEGORY_MAP_TO_HINDI = {
    "EXAM": "परीक्षा",
    "RESULT": "परिणाम",
    "ADMISSION": "प्रवेश",
    "HOLIDAY": "अवकाश",
    "ACADEMIC": "शैक्षणिक",
    "GENERAL": "सामान्य",
    "BREAKING": "ताज़ा"
}

def is_hindi_text(text: str) -> bool:
    """Returns True if the text contains Devanagari characters (\u0900-\u097F)."""
    return bool(re.search(r'[\u0900-\u097F]', text or ""))

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

def sanitize_language_consistency(parsed: dict, is_hindi: bool, fallback_title: str) -> dict:
    """Enforces strict language parity so that Hindi news has 100% Hindi card texts & badges."""
    if not parsed or not isinstance(parsed, dict):
        return parsed

    if is_hindi:
        # 1. Translate badge if English
        badge = parsed.get("badge", "")
        if not is_hindi_text(badge):
            upper_b = badge.upper()
            matched = False
            for eng_k, hin_v in BADGE_MAP_TO_HINDI.items():
                if eng_k in upper_b:
                    parsed["badge"] = hin_v
                    matched = True
                    break
            if not matched:
                parsed["badge"] = "ताज़ा अपडेट"

        # 2. Check headline
        headline = parsed.get("headline", "")
        if not is_hindi_text(headline) and is_hindi_text(fallback_title):
            parsed["headline"] = fallback_title[:60]

        # 3. Check Slides
        if "slides" in parsed and isinstance(parsed["slides"], list):
            for idx, s in enumerate(parsed["slides"]):
                if not isinstance(s, dict):
                    continue
                if idx == 0:
                    if not is_hindi_text(s.get("title", "")) and is_hindi_text(fallback_title):
                        s["title"] = fallback_title[:60]
                    if not is_hindi_text(s.get("subtitle", "")):
                        s["subtitle"] = "नवीनतम महत्वपूर्ण सूचना"
                    if not is_hindi_text(s.get("badge", "")):
                        s["badge"] = parsed.get("badge", "आधिकारिक सूचना")
                else:
                    heading = s.get("heading", "")
                    if not is_hindi_text(heading):
                        if idx == len(parsed["slides"]) - 1:
                            s["heading"] = "महत्वपूर्ण निर्देश"
                        elif idx == 1:
                            s["heading"] = "मुख्य विवरण"
                        else:
                            s["heading"] = "आवश्यक बिंदु व दिशा-निर्देश"

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

    if is_hindi:
        lang_mandate = """
CRITICAL LANGUAGE MANDATE:
The source notice is in HINDI.
You MUST write 100% of ALL fields in HINDI (शुद्ध व सरल हिंदी):
- 'headline': Short, punchy headline in HINDI (max 8 words, e.g. "शोध: औषधीय पौधों से तैयार होंगे चांदी के कण", "बीएससी द्वितीय सेमेस्टर का परिणाम घोषित").
- 'badge': Short uppercase category tag in HINDI (e.g. "ताज़ा अपडेट", "परीक्षा परिणाम", "परीक्षा सूचना", "प्रवेश सूचना", "शोध अपडेट").
- 'key_points': ALL 3-4 bullet points MUST BE IN HINDI.
- 'slides': Slide titles, subtitles, headings, and bullet points MUST ALL BE IN HINDI.
- 'caption': Instagram caption MUST BE 100% IN HINDI.
ABSOLUTELY NO ENGLISH HEADLINES, BADGES, OR SLIDE BULLETS FOR HINDI NOTICES.
"""
    else:
        lang_mandate = """
CRITICAL LANGUAGE MANDATE:
The source notice is in ENGLISH.
You MUST write 100% of ALL fields in ENGLISH:
- 'headline': Short, punchy headline in ENGLISH (max 7 words).
- 'badge': Short uppercase category tag in ENGLISH (e.g. "BREAKING NEWS", "RESULT OUT", "EXAM ALERT", "ADMISSION UPDATE").
- 'key_points': ALL 3-4 bullet points MUST BE IN ENGLISH.
- 'slides': Slide titles, subtitles, headings, and bullet points MUST ALL BE IN ENGLISH.
- 'caption': Instagram caption MUST BE 100% IN ENGLISH.
ABSOLUTELY NO HINDI HEADLINES, BADGES, OR SLIDE BULLETS FOR ENGLISH NOTICES.
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
3. Headline: Short, punchy, maximum 7-8 words.
4. KEY POINTS (3 to 4 points, max 18-20 words each):
   - Point 1: Core development (What happened)
   - Point 2: Specific Location & Timing (Where and When)
   - Point 3: Reasons, student demands, or criteria (Why)
   - Point 4: Action required / student impact (Next steps)
5. Carousel Slides (2 to 4 slides):
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

    # Clean Fallback with real context extraction and full language consistency
    is_breaking = item.get("priority") == "TIER1_BREAKING"

    if is_hindi:
        badge = "ताज़ा अपडेट" if is_breaking else "आधिकारिक सूचना"
        headline = title[:60] or "एचपीयू विश्वविद्यालय सूचना"
        location_str = "एचपीयू समरहिल परिसर, शिमला"
        points = [
            f"{title[:80]}",
            f"स्थान: {location_str} | दिनांक: {notice_date}",
            "विवरण: विस्तृत विभागीय निर्देशों के लिए अपने छात्र पोर्टल पर लॉगिन करें",
            "यह पोस्ट सेव करें और अपने सहपाठियों के साथ शेयर करें"
        ]
        return {
            "tier": "TIER1_BREAKING" if is_breaking else "TIER2_ROUTINE",
            "category": item.get("category", "GENERAL"),
            "badge": badge,
            "headline": headline,
            "audio_track_id": "cornfield_chase" if is_breaking else "reflections",
            "key_points": points,
            "slides": [
                {"title": headline, "subtitle": f"दिनांक: {notice_date}", "badge": badge},
                {"heading": "मुख्य जानकारी", "points": points[:2]},
                {"heading": "विस्तृत विवरण और निर्देश", "points": points[2:]}
            ],
            "caption": (
                f"📢 {badge}: {headline}\n\n"
                f"छात्रों के लिए मुख्य बिंदु:\n"
                f"• {points[0]}\n"
                f"• {points[1]}\n"
                f"• {points[2]}\n\n"
                f"विस्तृत जानकारी के लिए आधिकारिक छात्र पोर्टल पर लॉगिन करें।\n"
                f"अपने सहपाठियों को नीचे कमेंट्स में टैग करें! 👇\n\n"
                f"#hpu #hpushimla #hpuupdates #hpuresult #hpuexams #himachalpradeshuniversity #shimla"
            )
        }

    # English Fallback
    badge = "BREAKING NEWS" if is_breaking else "OFFICIAL UPDATE"
    headline = title[:50] or "HPU University Notice"
    desc_clean = clean_text_no_urls(summary or raw_text or "")
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
    Strict Language Parity: Hindi source -> 100% Hindi card & caption; English source -> 100% English.
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
    category_hi = CATEGORY_MAP_TO_HINDI.get(category, "नवीनतम")
    
    # Format items for prompt
    notices_formatted = []
    for idx, it in enumerate(items[:4], 1):
        clean_t = clean_text_no_urls(it.get("title", ""))
        clean_c = clean_text_no_urls(it.get("raw_text", "") or it.get("ocr_text", "") or "")[:200]
        notices_formatted.append(f"{idx}. Title: {clean_t}\n   Details: {clean_c}")

    if is_hindi:
        lang_mandate = f"""
CRITICAL LANGUAGE MANDATE:
The source notices are written in HINDI.
You MUST write 100% of all fields in HINDI (शुद्ध व सरल हिंदी):
- Slide 1 (Cover):
  "title": In HINDI (e.g. "एचपीयू {category_hi} अपडेट्स", "आज की महत्वपूर्ण अधिसूचनाएं")
  "subtitle": In HINDI (e.g. "नवीनतम महत्वपूर्ण सूचनाएं व सर्कुलर")
  "badge": In HINDI (e.g. "परीक्षा परिणाम", "परीक्षा सूचना", "प्रवेश सूचना", "आधिकारिक अपडेट")
- Detail Slides:
  "heading": In HINDI (e.g. "शोध व लैब अपग्रेड", "परीक्षा फॉर्म की तिथि")
  "points": 2 to 3 concise bullet points in HINDI per slide (max 15 words per point).
- Last Slide:
  "heading": "महत्वपूर्ण निर्देश"
  "points": ["विस्तृत अंकों व फॉर्म के लिए छात्र पोर्टल देखें", "भविष्य के लिए यह पोस्ट सेव करें", "सहपाठियों के साथ शेयर करें"]
- 'headline': In HINDI (e.g. "एचपीयू ताज़ा अपडेट्स")
- 'caption': Must be 100% in HINDI.
ABSOLUTELY NO ENGLISH HEADINGS, ENGLISH BADGES, OR ENGLISH BULLETS FOR HINDI NOTICES.
"""
    else:
        lang_mandate = f"""
CRITICAL LANGUAGE MANDATE:
The source notices are written in ENGLISH.
You MUST write 100% of all fields in ENGLISH:
- Slide 1 (Cover): "title", "subtitle", "badge" in ENGLISH.
- Detail Slides: "heading" and "points" in ENGLISH.
- Last Slide: "heading": "Important Note", "points" in ENGLISH.
- 'headline': In ENGLISH.
- 'caption': Must be 100% in ENGLISH.
ABSOLUTELY NO HINDI HEADINGS, BADGES, OR BULLETS FOR ENGLISH NOTICES.
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
3. Carousel Slides structure:
   - Slide 1 (Cover): Punchy title + short subtitle + category badge
   - Next 2-3 Slides: Short heading + 2 to 3 concise, highly readable bullet points explaining what happened, who is affected, and what action to take (max 15 words per bullet). No emojis.
   - Last Slide: Summary guidance / Important Note
4. Instagram Caption:
   - Engaging hook
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

    # Fallback if AI unavailable with strict language consistency
    titles = [clean_text_no_urls(it.get("title", "")) for it in items]

    if is_hindi:
        badge_hi = f"{category_hi} अपडेट"
        cover_title = f"एचपीयू {category_hi} अपडेट्स"
        slides = [
            {
                "title": cover_title,
                "subtitle": f"{len(items)} महत्वपूर्ण अधिसूचनाएं जारी",
                "badge": badge_hi
            }
        ]

        for idx, it in enumerate(items[:3], start=1):
            clean_t = clean_text_no_urls(it.get("title", ""))
            slides.append({
                "heading": f"अपडेट {idx}: {clean_t[:40]}",
                "points": [
                    clean_t[:70],
                    "विस्तृत सूची व जानकारी के लिए छात्र पोर्टल देखें",
                    "अंतिम तिथि से पहले आवश्यक प्रक्रिया पूर्ण करें"
                ]
            })

        slides.append({
            "heading": "महत्वपूर्ण निर्देश",
            "points": [
                "सभी विवरण अपने छात्र पोर्टल लॉगिन पर जांचें",
                "भविष्य के संदर्भ के लिए यह पोस्ट सेव करें",
                "अपने सहपाठियों के साथ अवश्य शेयर करें"
            ]
        })

        caption = (
            f"📢 एचपीयू {category_hi} अपडेट्स!\n\n"
            f"आज जारी की गई महत्वपूर्ण अधिसूचनाएं:\n" +
            "\n".join([f"• {t[:85]}" for t in titles[:4]]) +
            f"\n\nविस्तृत जानकारी और फॉर्म के लिए छात्र पोर्टल पर लॉगिन करें।\n"
            f"अपने सहपाठियों को नीचे कमेंट्स में टैग करें! 👇\n\n"
            f"#hpu #hpushimla #hpuupdates #hpuresults #hpuexams #himachalpradeshuniversity #shimla"
        )

        return {
            "tier": "TIER2_ROUTINE",
            "category": category,
            "badge": badge_hi,
            "headline": f"एचपीयू {category_hi} अपडेट्स ({len(items)} सूचनाएं)",
            "slides": slides,
            "caption": caption
        }

    # English Routine Fallback
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
