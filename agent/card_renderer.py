import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from .config import OUTPUT_DIR, INSTAGRAM_HANDLE

WIDTH = 1080
HEIGHT = 1350

# White Background & Light Green Palette with Dark Green Text
THEME = {
    "bg": (255, 255, 255),               # Pure Clean White Canvas (#FFFFFF)
    "card_bg": (244, 251, 247),          # Soft Pastel Mint Inset Panel (#F4FBF7)
    "card_border": (187, 247, 208),      # Delicate Light Green Border (#BBF7D0)
    "outer_border": (220, 245, 230),     # Subtle Outer Framing (#DCF5E6)
    "corner_accent": (74, 222, 128),     # Crisp Light Green Corner Accents (#4ADE80)
    "primary": (10, 54, 34),             # Deep Dark Forest Green Headline (#0A3622)
    "body": (19, 78, 74),                # High-Contrast Dark Pine Text (#134E4A)
    "muted": (22, 101, 52),              # Medium Dark Forest Green (#166534)
    "dim": (74, 120, 90),                # Muted Olive-Green Subtext (#4A785A)
    "footer": (21, 128, 61),             # Vibrant Forest Green Footer (#15803D)
    "badge_bg": (220, 252, 231),         # Pastel Mint Pill (#DCFCE7)
    "badge_border": (134, 239, 172)      # Mint Pill Border (#86EFAC)
}

# Category Pill Colors tailored to Light Green & Dark Green Palette
BADGE_COLORS = {
    "BREAKING": {
        "bg": (254, 242, 242),           # Light Red Pastel
        "border": (252, 165, 165),
        "fg": (153, 27, 27),             # Dark Red Text
        "dot": (239, 68, 68),
        "bullet": (220, 38, 38)
    },
    "RESULT": {
        "bg": (220, 252, 231),           # Soft Emerald Pastel
        "border": (134, 239, 172),
        "fg": (6, 95, 70),               # Deep Emerald Text
        "dot": (16, 185, 129),
        "bullet": (5, 150, 105)
    },
    "EXAM": {
        "bg": (254, 249, 195),           # Soft Amber Pastel
        "border": (253, 224, 71),
        "fg": (113, 63, 18),             # Dark Bronze Text
        "dot": (234, 179, 8),
        "bullet": (202, 138, 4)
    },
    "ADMISSION": {
        "bg": (224, 242, 254),           # Soft Sky Pastel
        "border": (186, 230, 253),
        "fg": (12, 74, 110),             # Deep Navy Text
        "dot": (14, 165, 233),
        "bullet": (2, 132, 199)
    },
    "HOLIDAY": {
        "bg": (255, 237, 213),           # Soft Orange Pastel
        "border": (253, 186, 116),
        "fg": (154, 52, 18),
        "dot": (249, 115, 22),
        "bullet": (234, 88, 12)
    },
    "GENERAL": {
        "bg": (220, 252, 231),           # Classic Light Green Mint
        "border": (134, 239, 172),
        "fg": (6, 78, 59),               # Deep Dark Green Text
        "dot": (16, 185, 129),
        "bullet": (16, 185, 129)
    }
}

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
LOGO_PATH = ASSETS_DIR / "hpu_logo.png"
MOUNTAIN_BG_PATH = ASSETS_DIR / "hpu_mountains_bg.png"

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

    allowed_pattern = r'[^\x20-\x7E\u0900-\u097F\u20B9\u0964\u0965]+'
    cleaned = re.sub(allowed_pattern, ' ', cleaned).strip()
    return re.sub(r'\s+', ' ', cleaned)

clean_ascii_text = clean_display_text

def is_hindi_text(text: str) -> bool:
    """Returns True if the text contains Devanagari characters."""
    return bool(re.search(r'[\u0900-\u097F]', text or ""))

def get_font(font_type: str, size: int, is_hindi: bool = False):
    """
    Loads appropriate font for Hindi (Noto Sans Devanagari / Nirmala UI)
    or English (Poppins / Inter).
    """
    if is_hindi:
        candidates = [
            FONTS_DIR / ("NotoSansDevanagari-Bold.ttf" if "bold" in font_type.lower() else "NotoSansDevanagari-Medium.ttf"),
            Path("C:/Windows/Fonts/Nirmala.ttc"),
            FONTS_DIR / "Poppins-Bold.ttf",
            FONTS_DIR / "Inter.ttf"
        ]
    else:
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
            Path("C:/Windows/Fonts/segoeuib.ttf" if "bold" in font_type.lower() else "C:/Windows/Fonts/segoeui.ttf"),
            Path("C:/Windows/Fonts/arialbd.ttf" if "bold" in font_type.lower() else "C:/Windows/Fonts/arial.ttf")
        ]

    for p in candidates:
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size)
            except Exception:
                pass

    return ImageFont.load_default()

def wrap_text(text: str, font, max_width: int, draw) -> list:
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

def create_base_canvas(badge_key: str = "GENERAL") -> Image.Image:
    """
    Creates a premium white canvas with:
    1. Faded light-green Himalayan mountain ridges at the bottom.
    2. Faded central HPU crest watermark (~5% opacity).
    3. Crisp modern outer framing border with light green corner accent marks.
    """
    img = Image.new("RGBA", (WIDTH, HEIGHT), (255, 255, 255, 255))

    # 1. Blend faded mountain landscape
    if MOUNTAIN_BG_PATH.exists():
        try:
            mt_img = Image.open(MOUNTAIN_BG_PATH).convert("RGBA")
            mt_img = mt_img.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
            alpha = mt_img.split()[3]
            faded_alpha = alpha.point(lambda p: int(p * 0.70))
            mt_img.putalpha(faded_alpha)
            img.alpha_composite(mt_img)
        except Exception as e:
            print(f"[Renderer] Mountain background blend warning: {e}")

    # 2. Add subtle HPU watermark in the center
    if LOGO_PATH.exists():
        try:
            logo_wm = Image.open(LOGO_PATH).convert("RGBA")
            wm_size = 480
            logo_wm = logo_wm.resize((wm_size, wm_size), Image.Resampling.LANCZOS)
            r, g, b, a = logo_wm.split()
            subtle_a = a.point(lambda p: int(p * 0.055))
            logo_wm.putalpha(subtle_a)
            wm_x = (WIDTH - wm_size) // 2
            wm_y = (HEIGHT - wm_size) // 2 - 20
            img.alpha_composite(logo_wm, (wm_x, wm_y))
        except Exception as e:
            print(f"[Renderer] Logo watermark warning: {e}")

    canvas = img.convert("RGB")
    draw = ImageDraw.Draw(canvas)

    # 3. Outer framing border
    draw.rectangle([28, 28, WIDTH - 28, HEIGHT - 28], outline=THEME["outer_border"], width=2)

    # 4. Corner accent marks (Light Green)
    corner_len = 24
    ca = THEME["corner_accent"]
    draw.line([(28, 28), (28 + corner_len, 28)], fill=ca, width=4)
    draw.line([(28, 28), (28, 28 + corner_len)], fill=ca, width=4)
    draw.line([(WIDTH - 28, 28), (WIDTH - 28 - corner_len, 28)], fill=ca, width=4)
    draw.line([(WIDTH - 28, 28), (WIDTH - 28, 28 + corner_len)], fill=ca, width=4)
    draw.line([(28, HEIGHT - 28), (28 + corner_len, HEIGHT - 28)], fill=ca, width=4)
    draw.line([(28, HEIGHT - 28), (28, HEIGHT - 28 - corner_len)], fill=ca, width=4)
    draw.line([(WIDTH - 28, HEIGHT - 28), (WIDTH - 28 - corner_len, HEIGHT - 28)], fill=ca, width=4)
    draw.line([(WIDTH - 28, HEIGHT - 28), (WIDTH - 28, HEIGHT - 28 - corner_len)], fill=ca, width=4)

    return canvas

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

def draw_official_header(canvas: Image.Image, badge_text: str, is_hindi: bool = False, slide_num: int = 1, total_slides: int = 1) -> str:
    """
    Renders top header:
    - Official circular HPU emblem in top center.
    - Official University Name: 'हिमाचल प्रदेश विश्वविद्यालय, शिमला' / 'HIMACHAL PRADESH UNIVERSITY • SHIMLA'.
    - Community Sub-tag: 'HPU PULSE • STUDENT PORTAL UPDATES'.
    - Centered category badge pill with status dot.
    - Optional slide counter pill (e.g. '1/4').
    """
    draw = ImageDraw.Draw(canvas)
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

    if not clean_badge:
        clean_badge = "आधिकारिक सूचना" if is_hi else "OFFICIAL UPDATE"

    # 1. Official HPU Logo at top center
    logo_size = 80
    logo_y = 48
    bc_cx = WIDTH // 2
    bc_cy = logo_y + (logo_size // 2)

    if LOGO_PATH.exists():
        try:
            logo_img = Image.open(LOGO_PATH).convert("RGBA")
            logo_img = logo_img.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
            badge_circle_r = (logo_size // 2) + 5
            draw.ellipse(
                [bc_cx - badge_circle_r, bc_cy - badge_circle_r, bc_cx + badge_circle_r, bc_cy + badge_circle_r],
                fill=(255, 255, 255),
                outline=THEME["card_border"],
                width=2
            )
            canvas.paste(logo_img, (bc_cx - logo_size // 2, bc_cy - logo_size // 2), logo_img)
        except Exception:
            pass

    # 2. University Title
    title_text = "हिमाचल प्रदेश विश्वविद्यालय, शिमला" if is_hi else "HIMACHAL PRADESH UNIVERSITY • SHIMLA"
    t_font = get_font("bold", 22, is_hindi=is_hi)
    t_bbox = draw.textbbox((0, 0), title_text, font=t_font)
    tw = t_bbox[2] - t_bbox[0]
    draw.text(((WIDTH - tw) // 2, logo_y + logo_size + 14), title_text, fill=THEME["primary"], font=t_font)

    # Sub-tag
    sub_font = get_font("semibold", 14, is_hindi=False)
    sub_tag = "HPU PULSE  •  STUDENT PORTAL UPDATES"
    st_bbox = draw.textbbox((0, 0), sub_tag, font=sub_font)
    stw = st_bbox[2] - st_bbox[0]
    draw.text(((WIDTH - stw) // 2, logo_y + logo_size + 44), sub_tag, fill=THEME["muted"], font=sub_font)

    # 3. Category status badge pill
    upper_badge = clean_badge.upper()
    badge_key = "GENERAL"
    for cat, kws in BADGE_KEYWORDS.items():
        if any(kw in upper_badge for kw in kws):
            badge_key = cat
            break
    col = BADGE_COLORS.get(badge_key, BADGE_COLORS["GENERAL"])

    b_font = get_font("bold", 21, is_hindi=is_hi)
    b_bbox = draw.textbbox((0, 0), clean_badge, font=b_font)
    bw = b_bbox[2] - b_bbox[0]
    bh = b_bbox[3] - b_bbox[1]

    pill_w = bw + 50
    pill_h = bh + 20
    pill_x = (WIDTH - pill_w) // 2
    pill_y = logo_y + logo_size + 76

    draw.rounded_rectangle([pill_x, pill_y, pill_x + pill_w, pill_y + pill_h], radius=12, fill=col["bg"], outline=col["border"], width=1)
    draw.ellipse([pill_x + 16, pill_y + 11, pill_x + 25, pill_y + 20], fill=col["dot"])
    draw.text((pill_x + 34, pill_y + 4), clean_badge, fill=col["fg"], font=b_font)

    # 4. Slide progress counter
    if total_slides > 1:
        prog_font = get_font("bold", 20, is_hindi=False)
        prog_text = f"{slide_num}/{total_slides}"
        p_bbox = draw.textbbox((0, 0), prog_text, font=prog_font)
        pw = p_bbox[2] - p_bbox[0]
        px = WIDTH - pw - 85
        draw.rounded_rectangle([px - 14, pill_y, px + pw + 14, pill_y + pill_h], radius=10, fill=THEME["card_bg"], outline=THEME["card_border"], width=1)
        draw.text((px, pill_y + 5), prog_text, fill=THEME["primary"], font=prog_font)

    return badge_key

# Backward-compatibility alias
draw_header = draw_official_header

def draw_official_footer(draw: ImageDraw.ImageDraw, is_cover: bool = False, is_hindi: bool = False):
    """Draws crisp verified community footer in English or Hindi."""
    f_font = get_font("bold", 23, is_hindi=False)
    handle_text = f"{INSTAGRAM_HANDLE}  •  Shimla, Himachal Pradesh"
    f_bbox = draw.textbbox((0, 0), handle_text, font=f_font)
    fw = f_bbox[2] - f_bbox[0]
    draw.text(((WIDTH - fw) / 2, HEIGHT - 100), handle_text, fill=THEME["footer"], font=f_font)

    sub_font = get_font("medium", 19, is_hindi=is_hindi)
    sub_text = "यह पोस्ट सेव करें और सहपाठियों के साथ शेयर करें" if is_hindi else "Save this post  •  Share with your classmates"
    s_bbox = draw.textbbox((0, 0), sub_text, font=sub_font)
    sw = s_bbox[2] - s_bbox[0]
    draw.text(((WIDTH - sw) / 2, HEIGHT - 68), sub_text, fill=THEME["dim"], font=sub_font)

draw_footer = draw_official_footer

def parse_points(details: str, key_points: list = None) -> list:
    """Intelligently extracts a list of distinct structured points in English or Hindi."""
    if key_points and isinstance(key_points, list) and len(key_points) > 0:
        cleaned_pts = [clean_display_text(str(p)) for p in key_points if clean_display_text(str(p))]
        if cleaned_pts:
            return cleaned_pts

    if not details:
        return ["Details available on official student portal.", "Check your student account for more instructions."]

    cleaned = clean_display_text(details)
    raw_splits = re.split(r'\n+|•|\b(?:\d+[\.\)]\s+)', cleaned)
    points = []
    for s in raw_splits:
        item = s.strip()
        if len(item) > 8:
            points.append(item)

    if not points:
        sentences = re.split(r'(?<=[.!?।])\s+', cleaned)
        points = [st.strip() for st in sentences if len(st.strip()) > 8]

    return points[:4] if points else [cleaned[:100]]

def render_breaking_card(headline: str, category: str = "GENERAL", details: str = "", badge: str = "BREAKING NEWS", key_points: list = None) -> str:
    """
    Renders a stunning 1080x1350 card with:
    - Pure white background with faded mountains and HPU seal.
    - Dark green typography for headline and body text.
    - Soft pastel mint content panel with light green border.
    - Fully supports English and Hindi.
    """
    clean_h = clean_display_text(headline)
    points = parse_points(details, key_points)
    is_hi = is_hindi_text(f"{clean_h} {' '.join(points)} {badge} {details}")

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

    upper_b = (badge or "").upper()
    badge_key = "GENERAL"
    for cat, kws in BADGE_KEYWORDS.items():
        if any(kw in upper_b for kw in kws) or any(kw in (category or "").upper() for kw in kws):
            badge_key = cat
            break

    # 1. Base Canvas with Mountains & Watermark
    canvas = create_base_canvas(badge_key)
    draw = ImageDraw.Draw(canvas)

    # 2. Header with Logo & Badge
    draw_official_header(canvas, badge, is_hindi=is_hi)

    # 3. Clean Headline in Dark Forest Green
    h_font = get_font("bold", 54, is_hindi=is_hi)
    h_lines = wrap_text(clean_h, h_font, WIDTH - 170, draw)
    h_lines = h_lines[:3]
    line_h = 74
    y_start = 250

    for i, line in enumerate(h_lines):
        bbox = draw.textbbox((0, 0), line, font=h_font)
        lw = bbox[2] - bbox[0]
        draw.text(((WIDTH - lw) / 2, y_start + (i * line_h)), line, fill=THEME["primary"], font=h_font)

    # 4. Inset Soft Mint Content Panel
    box_top = y_start + (len(h_lines) * line_h) + 40
    box_bottom = HEIGHT - 155
    draw.rounded_rectangle(
        [65, box_top, WIDTH - 65, box_bottom],
        radius=22,
        fill=THEME["card_bg"],
        outline=THEME["card_border"],
        width=2
    )

    # Sub-header inside card
    sub_head_font = get_font("semibold", 24, is_hindi=is_hi)
    sub_head_text = "मुख्य बिंदु और आधिकारिक विवरण" if is_hi else "KEY DETAILS & OFFICIAL UPDATES"
    draw.text((105, box_top + 30), sub_head_text, fill=THEME["muted"], font=sub_head_font)
    draw.line([(105, box_top + 64), (WIDTH - 105, box_top + 64)], fill=THEME["card_border"], width=1)

    # 5. Bullet Points in Dark Pine with Emerald Dots
    p_font = get_font("medium", 30, is_hindi=is_hi)
    bullet_color = BADGE_COLORS[badge_key]["bullet"]
    py = box_top + 88
    max_text_width = WIDTH - 270

    for pt in points[:4]:
        wrapped = wrap_text(pt, p_font, max_text_width, draw)
        if not wrapped:
            continue

        for line_i, line in enumerate(wrapped):
            if py > box_bottom - 45:
                break

            if line_i == 0:
                draw.ellipse([105, py + 12, 117, py + 24], fill=bullet_color)
                draw.text((135, py), line, fill=THEME["body"], font=p_font)
            else:
                draw.text((135, py), line, fill=THEME["body"], font=p_font)

            py += 44

        py += 24

    # 6. Footer
    draw_official_footer(draw, is_cover=True, is_hindi=is_hi)

    out_path = OUTPUT_DIR / f"hpu_card_{uuid.uuid4().hex[:8]}.png"
    canvas.save(str(out_path), "PNG", quality=95)
    return str(out_path)

def render_carousel_slides(carousel_data: dict) -> list:
    """
    Renders 2-5 premium slides in:
    - Pure white background with faded mountains and HPU logo.
    - Dark green typography for headline and body text.
    - Light green category accents, borders, and badge styling.
    - Full support for Hindi and English.
    """
    slides = carousel_data.get("slides", [])
    badge = carousel_data.get("badge", "UPDATE")
    total = len(slides)
    slide_paths = []

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
        # 1. Base Canvas with Mountains & Watermark
        canvas = create_base_canvas(badge_key)
        draw = ImageDraw.Draw(canvas)

        # 2. Header with Logo, Title, and Badge
        draw_official_header(canvas, badge, is_hindi=is_hi_overall, slide_num=idx, total_slides=total)

        if idx == 1:
            # COVER SLIDE
            title = clean_display_text(s.get("title", carousel_data.get("headline", "HPU Update")))
            subtitle = clean_display_text(s.get("subtitle", ""))
            is_hi_cover = is_hi_overall or is_hindi_text(f"{title} {subtitle} {badge}")

            t_font = get_font("bold", 58, is_hindi=is_hi_cover)
            t_lines = wrap_text(title, t_font, WIDTH - 180, draw)
            total_th = len(t_lines) * 78
            y_start = (HEIGHT - total_th) / 2 - 30

            for i, line in enumerate(t_lines):
                bbox = draw.textbbox((0, 0), line, font=t_font)
                lw = bbox[2] - bbox[0]
                draw.text(((WIDTH - lw) / 2, y_start + (i * 78)), line, fill=THEME["primary"], font=t_font)

            if subtitle:
                sub_font = get_font("semibold", 30, is_hindi=is_hi_cover)
                s_bbox = draw.textbbox((0, 0), subtitle, font=sub_font)
                sw = s_bbox[2] - s_bbox[0]
                draw.text(((WIDTH - sw) / 2, y_start + total_th + 32), subtitle, fill=THEME["muted"], font=sub_font)

            # Swipe cue button pill (Soft mint background, light green border, dark green text)
            sw_font = get_font("bold", 23, is_hindi=is_hi_cover)
            sw_text = "पूरी जानकारी के लिए स्वाइप करें  >>" if is_hi_cover else "SWIPE FOR FULL DETAILS  >>"
            sw_bbox = draw.textbbox((0, 0), sw_text, font=sw_font)
            sw_w = sw_bbox[2] - sw_bbox[0]
            sw_h = sw_bbox[3] - sw_bbox[1]

            pill_w = sw_w + 50
            pill_h = sw_h + 24
            pill_x = (WIDTH - pill_w) / 2
            pill_y = HEIGHT - 205

            draw.rounded_rectangle(
                [pill_x, pill_y, pill_x + pill_w, pill_y + pill_h],
                radius=14,
                fill=THEME["card_bg"],
                outline=THEME["card_border"],
                width=2
            )
            draw.text(((WIDTH - sw_w) / 2, pill_y + 10), sw_text, fill=THEME["primary"], font=sw_font)
            draw_official_footer(draw, is_cover=True, is_hindi=is_hi_cover)

        else:
            # DETAIL SLIDES
            default_heading = "मुख्य विवरण" if is_hi_overall else "Key Information"
            heading = clean_display_text(s.get("heading") or default_heading)
            raw_points = s.get("points", [])
            points = [clean_display_text(str(p)) for p in raw_points if clean_display_text(str(p))]
            is_hi_detail = is_hi_overall or is_hindi_text(f"{heading} {' '.join(points)}")

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

            h_font = get_font("bold", 44, is_hindi=is_hi_detail)
            draw.text((85, 230), heading, fill=THEME["primary"], font=h_font)
            draw.line([(85, 290), (WIDTH - 85, 290)], fill=THEME["card_border"], width=2)

            box_top = 315
            box_bottom = HEIGHT - 155
            draw.rounded_rectangle(
                [65, box_top, WIDTH - 65, box_bottom],
                radius=20,
                fill=THEME["card_bg"],
                outline=THEME["card_border"],
                width=2
            )

            p_font = get_font("medium", 30, is_hindi=is_hi_detail)
            py = box_top + 45
            max_p_width = WIDTH - 260

            for pt in points:
                if not pt:
                    continue

                wrapped_pt = wrap_text(pt, p_font, max_p_width, draw)
                for line_i, line in enumerate(wrapped_pt):
                    if py > box_bottom - 45:
                        break

                    if line_i == 0:
                        draw.ellipse([100, py + 12, 112, py + 24], fill=bullet_color)
                        draw.text((128, py), line, fill=THEME["body"], font=p_font)
                    else:
                        draw.text((128, py), line, fill=THEME["body"], font=p_font)

                    py += 46

                py += 24

            draw_official_footer(draw, is_cover=False, is_hindi=is_hi_detail)

        slide_file = OUTPUT_DIR / f"slide_{uuid.uuid4().hex[:8]}_{idx}.png"
        canvas.save(str(slide_file), "PNG", quality=95)
        slide_paths.append(str(slide_file))

    return slide_paths

def render_daily_roundup_carousel(news_items: list) -> list:
    """
    Renders the Single Daily News Roundup Carousel (posted at 7:00 PM IST).
    Each slide represents one news story:
    - Bold, clear headline
    - Inset card with brief bullet-point explanation that fits cleanly
    - Official HPU crest header + Category badge pill
    - Source & date attribution in footer
    Meta Graph API hard limit: 2 to 10 images.
    """
    if not news_items:
        return []

    # Meta Graph API accepts max 10 images per carousel
    items_to_render = news_items[:10]
    total = len(items_to_render)

    # If only 1 item, duplicate into 2 slides (Overview + Key Actionables) since carousel requires >= 2
    if total == 1:
        it = items_to_render[0]
        items_to_render = [it, it]
        total = 2

    slide_paths = []

    for idx, item in enumerate(items_to_render, start=1):
        title = clean_display_text(item.get("title", "HPU University Update"))
        summary = clean_display_text(item.get("summary") or item.get("raw_text") or "")
        category = (item.get("category") or "GENERAL").upper()
        source = clean_display_text(item.get("source") or "HPU Portal")
        notice_date = clean_display_text(item.get("notice_date") or datetime.now().strftime("%d %b %Y"))

        is_hi = is_hindi_text(f"{title} {summary}")

        badge_key = "GENERAL"
        for cat, kws in BADGE_KEYWORDS.items():
            if any(kw in category for kw in kws):
                badge_key = cat
                break

        canvas = create_base_canvas(badge_key)
        draw = ImageDraw.Draw(canvas)

        # 1. Header
        badge_text = category
        draw_official_header(canvas, badge_text, is_hindi=is_hi, slide_num=idx, total_slides=total)

        # 2. Headline
        h_font = get_font("bold", 42, is_hindi=is_hi)
        max_h_width = WIDTH - 160
        h_lines = wrap_text(title, h_font, max_h_width, draw)
        
        # Limit headline lines to max 3
        if len(h_lines) > 3:
            h_lines = h_lines[:3]
            if not h_lines[-1].endswith("..."):
                h_lines[-1] = h_lines[-1][:max(10, len(h_lines[-1]) - 3)] + "..."

        hy = 230
        for hl in h_lines:
            draw.text((80, hy), hl, fill=THEME["primary"], font=h_font)
            hy += 52

        # 3. Divider line
        hy += 12
        draw.line([(80, hy), (WIDTH - 80, hy)], fill=THEME["card_border"], width=2)
        hy += 20

        # 4. Inset Briefing Panel
        box_top = hy
        box_bottom = HEIGHT - 155
        draw.rounded_rectangle(
            [65, box_top, WIDTH - 65, box_bottom],
            radius=18,
            fill=THEME["card_bg"],
            outline=THEME["card_border"],
            width=2
        )

        # Section Subtitle inside card
        sub_title = "संक्षिप्त विवरण एवं मुख्य बिंदु" if is_hi else "Key Highlights & Briefing"
        st_font = get_font("bold", 24, is_hindi=is_hi)
        draw.text((95, box_top + 28), sub_title, fill=THEME["muted"], font=st_font)
        draw.ellipse([80, box_top + 36, 88, box_top + 44], fill=THEME["corner_accent"])

        # Extract/split summary into brief bullet points
        points = []
        if summary:
            raw_pts = [p.strip() for p in re.split(r'[।.\n|]', summary) if len(p.strip()) > 15]
            points = raw_pts[:4]
        if not points:
            if is_hi:
                points = [
                    "विश्वविद्यालय द्वारा इस संबंध में विस्तृत अधिसूचना जारी की गई है।",
                    "छात्र अपने लॉगिन पोर्टल पर जाकर पूरी जानकारी देख सकते हैं।",
                    "संबंधित विभाग से अधिक जानकारी प्राप्त की जा सकती है।"
                ]
            else:
                points = [
                    "Detailed official notification published on university portal.",
                    "Students can log into their portal accounts to check further guidelines.",
                    "Contact the concerned department or examination branch for assistance."
                ]

        p_font = get_font("medium", 28, is_hindi=is_hi)
        py = box_top + 80
        max_p_width = WIDTH - 240
        bullet_col = BADGE_COLORS.get(badge_key, BADGE_COLORS["GENERAL"])["bullet"]

        for pt in points[:4]:
            wrapped_pt = wrap_text(pt, p_font, max_p_width, draw)
            for line_i, line in enumerate(wrapped_pt):
                if py > box_bottom - 70:
                    break
                if line_i == 0:
                    draw.ellipse([92, py + 10, 104, py + 22], fill=bullet_col)
                    draw.text((120, py), line, fill=THEME["body"], font=p_font)
                else:
                    draw.text((120, py), line, fill=THEME["body"], font=p_font)
                py += 44
            py += 18

        # Inset source & date attribution badge at the bottom of the card
        src_tag = f"स्रोत: {source} • {notice_date}" if is_hi else f"Source: {source} • {notice_date}"
        src_font = get_font("semibold", 18, is_hindi=is_hi)
        draw.text((95, box_bottom - 42), src_tag, fill=THEME["dim"], font=src_font)

        # 5. Footer
        draw_official_footer(draw, is_cover=False, is_hindi=is_hi)

        out_slide = OUTPUT_DIR / f"daily_news_{uuid.uuid4().hex[:8]}_{idx}.png"
        canvas.save(str(out_slide), "PNG", quality=95)
        slide_paths.append(str(out_slide))

    return slide_paths
