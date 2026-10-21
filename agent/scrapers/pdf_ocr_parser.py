import io
import re
import base64
import requests
from typing import Dict, Optional
import pypdf
from ..config import GEMINI_API_KEY, GEMINI_MODEL

def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extracts digital text from PDF bytes using pypdf."""
    text_parts = []
    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        for page in reader.pages[:4]: # Check first 4 pages
            extracted = page.extract_text()
            if extracted:
                text_parts.append(extracted.strip())
    except Exception as e:
        print(f"[PDF Parser] Error reading PDF stream: {e}")

    full_text = "\n".join(text_parts).strip()
    return full_text

def parse_scanned_pdf_with_gemini_vision(pdf_bytes: bytes, filename: str = "circular.pdf") -> str:
    """
    Fallback for scanned PDFs that contain zero digital text.
    Sends raw PDF bytes directly to Gemini 2.5 Flash which natively supports PDF OCR.
    """
    if not GEMINI_API_KEY:
        return ""

    try:
        b64_pdf = base64.b64encode(pdf_bytes[:4 * 1024 * 1024]).decode("utf-8") # Max 4MB sample
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
        
        prompt = (
            "You are an expert OCR parser for official university circulars from Himachal Pradesh University (HPU Shimla). "
            "Transcribe this scanned circular completely and extract: "
            "1. Official Notice/Ref Number\n"
            "2. Notice Date\n"
            "3. Subject / Heading\n"
            "4. Main Action/Decision (e.g. Exam postponed, Result declared, Holiday declared, Form date extended)\n"
            "5. All affected courses/classes\n"
            "Keep the transcription clear and structured."
        )

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": "application/pdf",
                                "data": b64_pdf
                            }
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 800
            }
        }

        resp = requests.post(url, json=payload, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        print(f"[PDF OCR Vision] Gemini vision OCR failed: {e}")
    return ""

def process_circular_pdf(media_bytes: bytes) -> Dict[str, str]:
    """
    Primary pipeline for HPU circular attachments (PDF or Images):
    1. Detects if it's an Image (JPEG/PNG) vs PDF.
    2. If Image, calls Gemini Vision with image MIME.
    3. If PDF, tries digital text extraction first.
    4. If scanned PDF, calls Gemini Vision OCR fallback.
    """
    if not media_bytes or len(media_bytes) < 10:
        return {"mode": "empty", "text": ""}

    # Check for JPEG or PNG magic headers
    if media_bytes.startswith(b"\xff\xd8\xff") or media_bytes.startswith(b"\x89PNG"):
        mime = "image/jpeg" if media_bytes.startswith(b"\xff\xd8\xff") else "image/png"
        print(f"  [Circular Parser] Scanned image circular detected ({mime}). Invoking Vision OCR...")
        if not GEMINI_API_KEY:
            return {"mode": "image", "text": ""}
        try:
            b64_img = base64.b64encode(media_bytes[:4 * 1024 * 1024]).decode("utf-8")
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
            prompt = (
                "You are an expert OCR parser for official university circulars from Himachal Pradesh University (HPU Shimla). "
                "Transcribe this circular image and extract: Notice No, Date, Subject, Main Decision, and Affected Courses."
            )
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt},
                            {"inline_data": {"mime_type": mime, "data": b64_img}}
                        ]
                    }
                ],
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": 600}
            }
            resp = requests.post(url, json=payload, timeout=25)
            if resp.status_code == 200:
                txt = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                return {"mode": "image_ocr", "text": txt}
        except Exception as e:
            print(f"  [Circular Parser] Image OCR failed: {e}")
        return {"mode": "image", "text": ""}

    # If it's a PDF:
    if media_bytes.startswith(b"%PDF"):
        digital_text = extract_text_from_pdf(media_bytes)
        if len(digital_text) > 60:
            return {"mode": "digital", "text": digital_text}
        
        print("  [PDF Parser] Scanned circular detected (no digital text). Invoking OCR fallback...")
        ocr_text = parse_scanned_pdf_with_gemini_vision(media_bytes)
        return {"mode": "ocr_vision" if ocr_text else "empty", "text": ocr_text or digital_text}

    return {"mode": "unknown", "text": ""}
