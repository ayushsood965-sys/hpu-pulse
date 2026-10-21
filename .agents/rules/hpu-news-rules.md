---
trigger: always_on
---

# HPU Agent Workspace Rules
- Always preserve the existing `wob-agent` modular structure (`card_renderer.py`, `reel_generator.py`, `audio_library.py`, `scheduler.py`, `db.py`).
- Never publish scraped content without first checking `db.py` for URL/content-hash deduplication.
- All official HPU PDF circulars must be parsed via OCR fallback (`pypdf`/`pdfplumber` + `pytesseract` or Gemini Vision) since HPU uploads scanned notices.
- Tier 1 (Urgent/Holidays/Exam Postponements) = Immediate Reel with audio from `agent/audio/`.
- Tier 2 (Results/Routine Notices) = Batched every 60–120 minutes into categorized Carousels.