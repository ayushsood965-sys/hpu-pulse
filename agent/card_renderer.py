import os
import re
import uuid
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from .config import OUTPUT_DIR, INSTAGRAM_HANDLE

WIDTH = 1080
HEIGHT = 1350

# Modern Dark Slate / Obsidian Aesthetic (Inspired by top Indian news & student update pages)
THEME = {
    "bg": (11, 15, 25),             # Deep Obsidian (#0B0F19)
    "card_bg": (19, 27, 46),        # Sleek Glassmorphism Inset (#131B2E)
    "card_border": (42, 58, 84),    # Subtle Slate Border (#2A3A54)
    "outer_border": (28, 38, 56),   # Crisp framing border
    "corner_accent": (59, 130, 246),# Corner Accent Marks (#3B82F6)
    "primary": (255, 255, 255),     # Crisp Pure White Headline
    "body": (241, 245, 249),        # High-Readability Off-White (#F1F5F9)
    "muted": (148, 163, 184),       # Slate Secondary (#94A3B8)
    "dim": (100, 116, 139),         # Muted Subtext (#64748B)
    "footer": (203, 213, 225)       # Footer Text (#CBD5E1)
}

BADGE_COLORS = {
    "BREAKING": {
        "bg": (220, 38, 38),
        "fg": (255, 255, 255),
        "dot": (254, 202, 202),
        "glow": (127, 29, 29),
        "bullet": (239, 68, 68)
    },
    "RESULT": {
        "bg": (16, 185, 129),
        "fg": (255, 255, 255),
        "dot": (209, 250, 229),
        "glow": (6, 95, 70),
        "bullet": (52, 211, 153)
    },
    "EXAM": {
        "bg": (245, 158, 11),
        "fg": (15, 23, 42),
        "dot": (254, 243, 199),
        "glow": (146, 64, 14),
        "bullet": (251, 191, 36)
    },
    "ADMISSION": {
        "bg": (6, 182, 212),
        "fg": (15, 23, 42),
        "dot": (207, 250, 254),
        "glow": (21, 94, 117),
        "bullet": (34, 211, 238)
    },
    "HOLIDAY": {
        "bg": (239, 68, 68),
        "fg": (255, 255, 255),
        "dot": (254, 202, 202),
        "glow": (153, 27, 27),
        "bullet": (248, 113, 113)
    },
    "GENERAL": {
        "bg": (99, 102, 241),
        "fg": (255, 255, 255),
        "dot": (224, 231, 255),
        "glow": (55, 48, 163),
        "bullet": (129, 140, 248)
    }
}

FONTS_DIR = Path(__file__).resolve().parent / "assets" / "fonts"

def clean_display_text(text: str) -> str:
    """
    Cleans and preserves English, Hindi (Devanagari \u0900-\u097F), Rupee (₹ \u20B9),
    and standard punctuation, while stripping emojis and control characters.
    """
    if not text:
        return ""
    cleaned = str(text)
    cleaned = cleaned.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    cleaned = cleaned.replace("—", " - ").replace("–", " - ")
    cleaned = re.sub(r'https?://\S+', '', cleaned)
    cleaned = re.sub(r'(?:www\.)?(?:nexams|nadmissions|hpushimla|hpuniv)\S+', 'portal', cleaned)
    cleaned = re.sub(r'\s*-\s*(?:ANI\s*News|Amar\s*Ujala|Divya\s*Himachal|The\s*Tribune|Hindustan\s*Times|Times\s*of\s*India|Indian\s*Express|Jagran|News18).*$', '', cleaned, flags=re.IGNORECASE)

    # Allow ASCII printable, Devanagari block (\u0900-\u097F), Rupee sign (\u20B9), Hindi danda (\u0964, \u0965)
    allowed_pattern = r'[^\x20-\x7E\u0900-\u097F\u20B9\u0964\u0965]+'
    cleaned = re.sub(allowed_pattern, ' ', cleaned).strip()
    return re.sub(r'\s+', ' ', cleaned)

# Backward-compatibility alias
clean_ascii_text = clean_display_text

def is_hindi_text(text: str) -> bool:
    """Returns True if the text contains Devanagari characters."""
    return bool(re.search(r'[\u0900-\u097F]', text or ""))

def get_font(font_type: str, size: int) -> ImageFont.FreeTypeFont:
    """
    Loads modern bundled fonts (Poppins, Inter) with system fallbacks.
    font_type: 'bold', 'semibold', 'medium', 'regular'
    """
    font_map = {
        "bold": "Poppins-Bold.ttf",
        "semibold": "Poppins-SemiBold.ttf",
        "medium": "Poppins-Medium.ttf",
        "regular": "Poppins-Regular.ttf"
    }

    target_name = font_map.get(font_type.lower(), "Poppins-Bold.ttf")

    candidates = [
        FONTS_DIR / target_name,
        FONTS_DIR / "Inter.ttf",
        Path("C:/Windows/Fonts") / ("segoeuib.ttf" if "bold" in font_type.lower() else "segoeui.ttf"),
        Path("C:/Windows/Fonts") / ("arialbd.ttf" if "bold" in font_type.lower() else "arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu") / ("DejaVuSans-Bold.ttf" if "bold" in font_type.lower() else "DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation") / ("LiberationSans-Bold.ttf" if "bold" in font_type.lower() else "LiberationSans-Regular.ttf")
    ]

    for p in candidates:
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size)
            except Exception:
                pass

    try:
        return ImageFont.truetype(target_name, size)
    except Exception:
        return ImageFont.load_default()

def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.ImageDraw) -> list:
    """Wraps text into visual lines within max_width."""
    words = text.split()
    if not words:
        return []
    lines = []
    current_line = []
    for word in words:
        test_line = " ".join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=font)
        w = bbox[2] - bbox[0]
        if w <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
    if current_line:
        lines.append(" ".join(current_line))
    return lines

def draw_ambient_background(img: Image.Image, draw: ImageDraw.ImageDraw, badge_key: str):
    """Draws sleek gaussian blurred ambient corner glows and crisp framing borders."""
    colors = BADGE_COLORS.get(badge_key, BADGE_COLORS["GENERAL"])
    rgb_glow = colors["glow"]
    glow_rgba = (rgb_glow[0], rgb_glow[1], rgb_glow[2], 115)

    # Soft glowing radial atmosphere
    glow_overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(glow_overlay)
    g_draw.ellipse([WIDTH - 360, -160, WIDTH + 200, 400], fill=glow_rgba)
    g_draw.ellipse([-200, HEIGHT - 400, 360, HEIGHT + 160], fill=glow_rgba)
    glow_blurred = glow_overlay.filter(ImageFilter.GaussianBlur(85))
    img.paste(glow_blurred, (0, 0), glow_blurred)

    # Outer border framing
    draw.rectangle([28, 28, WIDTH - 28, HEIGHT - 28], outline=THEME["outer_border"], width=2)

    # Sleek modern corner tick marks
    corner_len = 24
    draw.line([(28, 28), (28 + corner_len, 28)], fill=THEME["corner_accent"], width=4)
    draw.line([(28, 28), (28, 28 + corner_len)], fill=THEME["corner_accent"], width=4)

    draw.line([(WIDTH - 28, 28), (WIDTH - 28 - corner_len, 28)], fill=THEME["corner_accent"], width=4)
    draw.line([(WIDTH - 28, 28), (WIDTH - 28, 28 + corner_len)], fill=THEME["corner_accent"], width=4)

    draw.line([(28, HEIGHT - 28), (28 + corner_len, HEIGHT - 28)], fill=THEME["corner_accent"], width=4)
    draw.line([(28, HEIGHT - 28), (28, HEIGHT - 28 - corner_len)], fill=THEME["corner_accent"], width=4)

    draw.line([(WIDTH - 28, HEIGHT - 28), (WIDTH - 28 - corner_len, HEIGHT - 28)], fill=THEME["corner_accent"], width=4)
    draw.line([(WIDTH - 28, HEIGHT - 28), (WIDTH - 28, HEIGHT - 28 - corner_len)], fill=THEME["corner_accent"], width=4)

BADGE_KEYWORDS = {
    "BREAKING": ["BREAKING", "ALERT", "URGENT", "ब्रेकिंग", "अलर्ट", "ताज़ा", "ताजा", "तत्काल", "महत्वपूर्ण"],
    "RESULT": ["RESULT", "MERIT", "SCORE", "परिणाम", "रिजल्ट", "मेरिट", "अंक"],
    "EXAM": ["EXAM", "DATESHEET", "DATE SHEET", "SCHEDULE", "परीक्षा", "डेटशीट", "समय सारणी", "टाइम टेबल"],
    "ADMISSION": ["ADMISSION", "COUNSEL", "SEAT", "प्रवेश", "दाखिला", "काउंसलिंग", "मेरिट सूची"],
    "HOLIDAY": ["HOLIDAY", "CLOSED", "CLOSURE", "छुट्टी", "अवकाश", "बंद"],
    "GENERAL": ["UPDATE", "NOTICE", "CIRCULAR", "अपडेट", "सूचना", "नोटिस", "रिसर्च", "शोध", "खोज"]
}

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

def draw_header(draw: ImageDraw.ImageDraw, badge_text: str, slide_num: int = 1, total_slides: int = 1, is_hindi: bool = False) -> str:
    """Renders top verified community header and category status badge in English or Hindi."""
    clean_badge = clean_display_text(badge_text).strip()
    is_hi = is_hindi or is_hindi_text(clean_badge)

    # Translate English badge to Hindi if the card context is in Hindi
    if is_hi and not is_hindi_text(clean_badge):
        upper_raw = clean_badge.upper()
        for eng_k, hin_v in BADGE_MAP_TO_HINDI.items():
            if eng_k in upper_raw:
                clean_badge = hin_v
                break
        if not is_hindi_text(clean_badge):
            clean_badge = "आधिकारिक सूचना"

    # Top Live Status Bar
    top_font = get_font("bold", 22)
    top_text = "एचपीयू शिमला  •  विद्यार्थी अपडेट्स" if is_hi else "HPU PULSE  •  STUDENT UPDATES"
    bbox = draw.textbbox((0, 0), top_text, font=top_font)
    tw = bbox[2] - bbox[0]

    # Glowing green status live dot
    dot_x = (WIDTH - tw) / 2 - 20
    dot_y = 74
    draw.ellipse([dot_x - 5, dot_y - 5, dot_x + 5, dot_y + 5], fill=(34, 197, 94))
    draw.text(((WIDTH - tw) / 2 + 5, 62), top_text, fill=THEME["muted"], font=top_font)

    # Accent divider line
    draw.line([(WIDTH / 2 - 80, 98), (WIDTH / 2 + 80, 98)], fill=THEME["card_border"], width=2)

    # Determine badge key
    if not clean_badge:
        clean_badge = "आधिकारिक सूचना" if is_hi else "OFFICIAL UPDATE"

    upper_badge = clean_badge.upper()
    badge_key = "GENERAL"
    for cat, kws in BADGE_KEYWORDS.items():
        if any(kw in upper_badge for kw in kws):
            badge_key = cat
            break
    colors = BADGE_COLORS[badge_key]

    # Category Pill Badge
    b_font = get_font("bold", 22)
    b_bbox = draw.textbbox((0, 0), clean_badge, font=b_font)
    bw = b_bbox[2] - b_bbox[0]
    bh = b_bbox[3] - b_bbox[1]

    dot_radius = 5
    dot_spacing = 14
    total_pill_w = bw + (dot_radius * 2) + dot_spacing + 48
    bx = (WIDTH - total_pill_w) / 2
    by = 124
    pill_h = bh + 24

    draw.rounded_rectangle([bx, by, bx + total_pill_w, by + pill_h], radius=14, fill=colors["bg"])
    
    # White/contrast status dot inside pill
    dot_cx = bx + 22 + dot_radius
    dot_cy = by + (pill_h / 2)
    draw.ellipse([dot_cx - dot_radius, dot_cy - dot_radius, dot_cx + dot_radius, dot_cy + dot_radius], fill=colors["dot"])

    # Badge text
    text_x = dot_cx + dot_radius + dot_spacing
    text_y = by + ((pill_h - bh) / 2) - 2
    draw.text((text_x, text_y), clean_badge, fill=colors["fg"], font=b_font)

    # Slide counter if carousel
    if total_slides > 1:
        prog_font = get_font("bold", 20)
        prog_text = f"{slide_num}/{total_slides}"
        p_bbox = draw.textbbox((0, 0), prog_text, font=prog_font)
        pw = p_bbox[2] - p_bbox[0]
        px = WIDTH - pw - 85
        draw.rounded_rectangle([px - 14, by + 2, px + pw + 14, by + pill_h - 2], radius=10, fill=THEME["card_bg"], outline=THEME["card_border"], width=1)
        draw.text((px, by + 8), prog_text, fill=THEME["primary"], font=prog_font)

    return badge_key

def draw_footer(draw: ImageDraw.ImageDraw, is_cover: bool = False, is_hindi: bool = False):
    """Draws crisp verified community footer in English or Hindi."""
    f_font = get_font("bold", 24)
    uni_name = "हिमाचल प्रदेश विश्वविद्यालय" if is_hindi else "Himachal Pradesh University"
    handle_text = f"{INSTAGRAM_HANDLE}  •  {uni_name}"
    f_bbox = draw.textbbox((0, 0), handle_text, font=f_font)
    fw = f_bbox[2] - f_bbox[0]
    draw.text(((WIDTH - fw) / 2, HEIGHT - 105), handle_text, fill=THEME["footer"], font=f_font)

    sub_font = get_font("regular", 20)
    sub_text = "यह पोस्ट सेव करें  •  सहपाठियों के साथ शेयर करें" if is_hindi else "Save this post  •  Share with your classmates"
    s_bbox = draw.textbbox((0, 0), sub_text, font=sub_font)
    sw = s_bbox[2] - s_bbox[0]
    draw.text(((WIDTH - sw) / 2, HEIGHT - 70), sub_text, fill=THEME["dim"], font=sub_font)

def parse_points(details: str, key_points: list = None) -> list:
    """
    Intelligently extracts a list of distinct structured points in English or Hindi.
    Prevents running a paragraph into visual lines that each get bulleted!
    """
    if key_points and isinstance(key_points, list) and len(key_points) > 0:
        cleaned_pts = [clean_display_text(str(p)) for p in key_points if clean_display_text(str(p))]
        if cleaned_pts:
            return cleaned_pts

    if not details:
        return ["Details available on official student portal.", "Check your student account for more instructions."]

    cleaned = clean_display_text(details)

    # Split by newlines, bullets, or numbers
    raw_splits = re.split(r'\n+|•|\b(?:\d+[\.\)]\s+)', cleaned)
    points = []
    for s in raw_splits:
        item = s.strip()
        if len(item) > 8:
            points.append(item)

    if not points:
        # Fallback split into sentences (handles English . ! ? and Hindi danda ।)
        sentences = re.split(r'(?<=[.!?।])\s+', cleaned)
        points = [st.strip() for st in sentences if len(st.strip()) > 8]

    return points[:4] if points else [cleaned[:100]]

def render_breaking_card(headline: str, category: str = "GENERAL", details: str = "", badge: str = "BREAKING NEWS", key_points: list = None) -> str:
    """
    Renders a stunning 1080x1350 card with Modern Dark Obsidian aesthetic,
    Poppins typography, and CORRECT bullet point indentation (NO multiple bullets on wrapped lines!).
    Supports both English and Hindi.
    """
    clean_h = clean_display_text(headline)
    points = parse_points(details, key_points)
    is_hi = is_hindi_text(f"{clean_h} {' '.join(points)} {badge} {details}")

    # Fallback safeguard against empty points
    if not points:
        if is_hi:
            points = [
                "विस्तृत जानकारी के लिए आधिकारिक छात्र पोर्टल पर लॉगिन करें।",
                "सभी आवश्यक दिशा-निर्देश पोर्टल पर उपलब्ध करा दिए गए हैं।"
            ]
        else:
            points = [
                "Details available on official student portal.",
                "Check your student account for more instructions."
            ]

    badge_key = "GENERAL"
    for cat, kws in BADGE_KEYWORDS.items():
        if any(kw in (badge or "").upper() for kw in kws) or any(kw in (category or "").upper() for kw in kws):
            badge_key = cat
            break

    img = Image.new("RGB", (WIDTH, HEIGHT), THEME["bg"])
    draw = ImageDraw.Draw(img)

    # 1. Ambient Background Glow & Framing
    draw_ambient_background(img, draw, badge_key)

    # 2. Header
    draw_header(draw, badge, is_hindi=is_hi)

    # 3. Clean Headline
    h_font = get_font("bold", 54)
    h_lines = wrap_text(clean_h, h_font, WIDTH - 180, draw)
    h_lines = h_lines[:3]  # Max 3 lines
    line_h = 72
    h_total_h = len(h_lines) * line_h
    y_start = 250

    for i, line in enumerate(h_lines):
        bbox = draw.textbbox((0, 0), line, font=h_font)
        lw = bbox[2] - bbox[0]
        draw.text(((WIDTH - lw) / 2, y_start + (i * line_h)), line, fill=THEME["primary"], font=h_font)

    # 4. Inset Frosted Content Panel
    box_top = y_start + h_total_h + 40
    box_bottom = HEIGHT - 165
    draw.rounded_rectangle(
        [65, box_top, WIDTH - 65, box_bottom],
        radius=22,
        fill=THEME["card_bg"],
        outline=THEME["card_border"],
        width=2
    )

    # Section header inside card
    sub_head_font = get_font("semibold", 24)
    sub_head_text = "मुख्य बिंदु और विवरण" if is_hi else "KEY DETAILS & UPDATES"
    draw.text((105, box_top + 32), sub_head_text, fill=THEME["muted"], font=sub_head_font)
    draw.line([(105, box_top + 64), (WIDTH - 105, box_top + 64)], fill=THEME["card_border"], width=1)

    # 5. FIXED BULLET POINTS RENDERING:
    p_font = get_font("medium", 30)
    bullet_color = BADGE_COLORS[badge_key]["bullet"]
    
    py = box_top + 88
    max_text_width = WIDTH - 270

    for pt in points[:4]:
        wrapped = wrap_text(pt, p_font, max_text_width, draw)
        if not wrapped:
            continue

        for line_i, line in enumerate(wrapped):
            # Check vertical space
            if py > box_bottom - 50:
                break

            if line_i == 0:
                # FIRST LINE ONLY: Draw bullet dot
                draw.ellipse([105, py + 12, 117, py + 24], fill=bullet_color)
                draw.text((135, py), line, fill=THEME["body"], font=p_font)
            else:
                # SUBSEQUENT WRAPPED LINES: Indented cleanly, NO bullet dot!
                draw.text((135, py), line, fill=THEME["body"], font=p_font)

            py += 44

        # Paragraph gap between distinct points
        py += 22

    # 6. Footer
    draw_footer(draw, is_cover=True, is_hindi=is_hi)

    out_path = OUTPUT_DIR / f"hpu_card_{uuid.uuid4().hex[:8]}.png"
    img.save(str(out_path), "PNG", quality=95)
    return str(out_path)

def render_carousel_slides(carousel_data: dict) -> list:
    """
    Renders 2-5 premium slides in Modern Dark Obsidian theme with Poppins fonts.
    Correct bullet rendering, sleek swipe indicators, zero URLs, full Hindi & English support.
    """
    slides = carousel_data.get("slides", [])
    badge = carousel_data.get("badge", "UPDATE")
    total = len(slides)
    slide_paths = []

    # Detect if the overall carousel data is in Hindi
    all_text = f"{badge} {carousel_data.get('headline', '')}"
    for s in slides:
        all_text += f" {s.get('title', '')} {s.get('subtitle', '')} {s.get('heading', '')} {' '.join(str(p) for p in s.get('points', []))}"
    is_hi_overall = is_hindi_text(all_text)

    badge_key = "GENERAL"
    for cat, kws in BADGE_KEYWORDS.items():
        if any(kw in (badge or "").upper() for kw in kws):
            badge_key = cat
            break

    bullet_color = BADGE_COLORS[badge_key]["bullet"]

    for idx, s in enumerate(slides, start=1):
        img = Image.new("RGB", (WIDTH, HEIGHT), THEME["bg"])
        draw = ImageDraw.Draw(img)

        # Ambient Glow & Framing
        draw_ambient_background(img, draw, badge_key)
        draw_header(draw, badge, slide_num=idx, total_slides=total, is_hindi=is_hi_overall)

        if idx == 1:
            # COVER SLIDE
            title = clean_display_text(s.get("title", carousel_data.get("headline", "HPU Update")))
            subtitle = clean_display_text(s.get("subtitle", ""))
            is_hi_cover = is_hi_overall or is_hindi_text(f"{title} {subtitle} {badge}")

            t_font = get_font("bold", 60)
            t_lines = wrap_text(title, t_font, WIDTH - 180, draw)
            total_th = len(t_lines) * 80
            y_start = (HEIGHT - total_th) / 2 - 40

            for i, line in enumerate(t_lines):
                bbox = draw.textbbox((0, 0), line, font=t_font)
                lw = bbox[2] - bbox[0]
                draw.text(((WIDTH - lw) / 2, y_start + (i * 80)), line, fill=THEME["primary"], font=t_font)

            if subtitle:
                sub_font = get_font("semibold", 32)
                s_bbox = draw.textbbox((0, 0), subtitle, font=sub_font)
                sw = s_bbox[2] - s_bbox[0]
                draw.text(((WIDTH - sw) / 2, y_start + total_th + 35), subtitle, fill=BADGE_COLORS[badge_key]["bullet"], font=sub_font)

            # Modern Swipe Cue Button Pill
            sw_font = get_font("bold", 24)
            sw_text = "पूरी जानकारी के लिए स्वाइप करें  >>" if is_hi_cover else "SWIPE FOR FULL DETAILS  >>"
            sw_bbox = draw.textbbox((0, 0), sw_text, font=sw_font)
            sw_w = sw_bbox[2] - sw_bbox[0]
            sw_h = sw_bbox[3] - sw_bbox[1]

            pill_w = sw_w + 50
            pill_h = sw_h + 26
            pill_x = (WIDTH - pill_w) / 2
            pill_y = HEIGHT - 210

            draw.rounded_rectangle(
                [pill_x, pill_y, pill_x + pill_w, pill_y + pill_h],
                radius=14,
                fill=THEME["card_bg"],
                outline=THEME["card_border"],
                width=2
            )
            draw.text(((WIDTH - sw_w) / 2, pill_y + 11), sw_text, fill=THEME["primary"], font=sw_font)
            draw_footer(draw, is_cover=True, is_hindi=is_hi_cover)

        else:
            # DETAIL SLIDES
            default_heading = "मुख्य विवरण" if is_hi_overall else "Key Information"
            heading = clean_display_text(s.get("heading") or default_heading)
            raw_points = s.get("points", [])
            points = [clean_display_text(str(p)) for p in raw_points if clean_display_text(str(p))]
            is_hi_detail = is_hi_overall or is_hindi_text(f"{heading} {' '.join(points)}")

            # CRITICAL SAFEGUARD: Never leave a content card blank!
            if not points:
                if is_hi_detail:
                    points = [
                        "विस्तृत जानकारी के लिए आधिकारिक छात्र पोर्टल पर लॉगिन करें।",
                        "सभी आवश्यक दिशा-निर्देश पोर्टल पर उपलब्ध करा दिए गए हैं।"
                    ]
                else:
                    points = [
                        "Details available on official student portal.",
                        "Check your student account for more instructions."
                    ]

            h_font = get_font("bold", 46)
            draw.text((85, 230), heading, fill=THEME["primary"], font=h_font)
            draw.line([(85, 292), (WIDTH - 85, 292)], fill=THEME["card_border"], width=2)

            box_top = 320
            box_bottom = HEIGHT - 165
            draw.rounded_rectangle(
                [65, box_top, WIDTH - 65, box_bottom],
                radius=20,
                fill=THEME["card_bg"],
                outline=THEME["card_border"],
                width=2
            )

            p_font = get_font("medium", 32)
            py = box_top + 45
            max_p_width = WIDTH - 260

            for pt in points:
                if not pt:
                    continue

                wrapped_pt = wrap_text(pt, p_font, max_p_width, draw)
                for line_i, line in enumerate(wrapped_pt):
                    if py > box_bottom - 50:
                        break

                    if line_i == 0:
                        # Draw bullet dot ONLY on the first line
                        draw.ellipse([100, py + 12, 112, py + 24], fill=bullet_color)
                        draw.text((128, py), line, fill=THEME["body"], font=p_font)
                    else:
                        # Indent subsequent wrapped lines without any bullet dot
                        draw.text((128, py), line, fill=THEME["body"], font=p_font)

                    py += 48

                # Paragraph gap between points
                py += 24

            draw_footer(draw, is_cover=False, is_hindi=is_hi_detail)

        slide_file = OUTPUT_DIR / f"slide_{uuid.uuid4().hex[:8]}_{idx}.png"
        img.save(str(slide_file), "PNG", quality=95)
        slide_paths.append(str(slide_file))

    return slide_paths
