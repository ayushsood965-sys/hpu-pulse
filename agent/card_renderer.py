import os
import uuid
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from .config import OUTPUT_DIR, INSTAGRAM_HANDLE

WIDTH = 1080
HEIGHT = 1350

import os
import re
import uuid
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from .config import OUTPUT_DIR, INSTAGRAM_HANDLE

WIDTH = 1080
HEIGHT = 1350

# Modern Light Green Student Aesthetic (Modeled on @hpuupdate / student community pages)
THEME = {
    "bg": (235, 247, 238),          # Light Mint Green Base (#EBF7EE)
    "bg_glow": (216, 242, 222),     # Soft Glowing Mint Green for corner effects
    "card_bg": (250, 254, 251),     # Crisp Inset Card Panel
    "border": (42, 98, 65),         # Deep Sage / Forest Green Framing Border (#2A6241)
    "inner_border": (195, 228, 204),# Soft Mint Accent Border (#C3E4CC)
    "primary": (0, 0, 0),           # Solid Black for bold headlines & titles
    "body": (15, 20, 25),           # Solid Deep Black for maximum reading clarity
    "muted": (40, 50, 45),          # Deep Charcoal Sage
    "accent": (25, 95, 55),         # Deep Emerald Green Accent
    "footer": (30, 35, 30),         # Solid dark footer text
    "bullet_dot": (34, 139, 74)     # Crisp Emerald Bullet Dot
}

BADGE_COLORS = {
    "BREAKING": {"bg": (220, 38, 38), "fg": (255, 255, 255), "dot": (254, 202, 202)},
    "RESULT": {"bg": (22, 128, 61), "fg": (255, 255, 255), "dot": (187, 247, 208)},
    "EXAM": {"bg": (180, 83, 9), "fg": (255, 255, 255), "dot": (254, 215, 170)},
    "ADMISSION": {"bg": (15, 118, 110), "fg": (255, 255, 255), "dot": (153, 246, 228)},
    "GENERAL": {"bg": (35, 95, 62), "fg": (255, 255, 255), "dot": (209, 250, 229)}
}

def clean_ascii_text(text: str) -> str:
    """Removes emojis and non-ascii glyphs that standard OS fonts cannot render."""
    cleaned = re.sub(r'[^\x00-\x7F]+', ' ', text).strip()
    return re.sub(r'\s+', ' ', cleaned)

def get_font(font_name: str, size: int):
    candidates = [
        Path("C:/Windows/Fonts") / font_name,
        Path("/usr/share/fonts/truetype/dejavu") / ("DejaVuSans-Bold.ttf" if "b." in font_name.lower() or "bold" in font_name.lower() else "DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation") / ("LiberationSans-Bold.ttf" if "b." in font_name.lower() or "bold" in font_name.lower() else "LiberationSans-Regular.ttf"),
        Path(font_name)
    ]
    for p in candidates:
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size)
            except Exception:
                pass
    try:
        return ImageFont.truetype(font_name, size)
    except Exception:
        return ImageFont.load_default()

def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.ImageDraw) -> list:
    words = text.split()
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

def draw_light_green_effects(draw: ImageDraw.ImageDraw):
    """Draws subtle soft green glowing circular background effects and decorative accents."""
    # Top-right soft ambient circle
    draw.ellipse([WIDTH - 240, -100, WIDTH + 140, 280], fill=THEME["bg_glow"])
    # Bottom-left soft ambient circle
    draw.ellipse([-120, HEIGHT - 260, 260, HEIGHT + 120], fill=THEME["bg_glow"])
    # Outer crisp border frame
    draw.rectangle([34, 34, WIDTH - 34, HEIGHT - 34], outline=THEME["border"], width=3)
    draw.rectangle([44, 44, WIDTH - 44, HEIGHT - 44], outline=THEME["inner_border"], width=1)
    # Corner accent marks
    corner_len = 28
    draw.line([(34, 34), (34 + corner_len, 34)], fill=THEME["accent"], width=5)
    draw.line([(34, 34), (34, 34 + corner_len)], fill=THEME["accent"], width=5)
    draw.line([(WIDTH - 34, 34), (WIDTH - 34 - corner_len, 34)], fill=THEME["accent"], width=5)
    draw.line([(WIDTH - 34, 34), (WIDTH - 34, 34 + corner_len)], fill=THEME["accent"], width=5)
    draw.line([(34, HEIGHT - 34), (34 + corner_len, HEIGHT - 34)], fill=THEME["accent"], width=5)
    draw.line([(34, HEIGHT - 34), (34, HEIGHT - 34 - corner_len)], fill=THEME["accent"], width=5)
    draw.line([(WIDTH - 34, HEIGHT - 34), (WIDTH - 34 - corner_len, HEIGHT - 34)], fill=THEME["accent"], width=5)
    draw.line([(WIDTH - 34, HEIGHT - 34), (WIDTH - 34, HEIGHT - 34 - corner_len)], fill=THEME["accent"], width=5)

def draw_header(draw: ImageDraw.ImageDraw, badge_text: str, slide_num: int = 1, total_slides: int = 1):
    # Top Community Banner
    top_font = get_font("arialbd.ttf", 25)
    top_text = "HPU SHIMLA  •  STUDENT UPDATES"
    bbox = draw.textbbox((0, 0), top_text, font=top_font)
    w = bbox[2] - bbox[0]
    draw.text(((WIDTH - w) / 2, 75), top_text, fill=THEME["accent"], font=top_font)

    # Decorative accent line
    draw.line([(WIDTH / 2 - 95, 114), (WIDTH / 2 + 95, 114)], fill=THEME["border"], width=2)

    # Clean badge text (strip emojis to avoid missing font square glyphs)
    clean_badge = clean_ascii_text(badge_text).upper()
    if not clean_badge:
        clean_badge = "OFFICIAL UPDATE"

    # Category matching
    badge_key = "GENERAL"
    for k in BADGE_COLORS:
        if k in clean_badge:
            badge_key = k
            break
    colors = BADGE_COLORS[badge_key]

    b_font = get_font("arialbd.ttf", 22)
    b_bbox = draw.textbbox((0, 0), clean_badge, font=b_font)
    bw = b_bbox[2] - b_bbox[0]
    bh = b_bbox[3] - b_bbox[1]
    
    # Pill with status dot
    dot_radius = 5
    dot_spacing = 16
    total_pill_w = bw + (dot_radius * 2) + dot_spacing + 44
    bx = (WIDTH - total_pill_w) / 2
    by = 142
    pill_h = bh + 22

    draw.rounded_rectangle([bx, by, bx + total_pill_w, by + pill_h], radius=14, fill=colors["bg"])
    
    # Antialiased status dot inside badge
    dot_cx = bx + 22 + dot_radius
    dot_cy = by + (pill_h / 2)
    draw.ellipse([dot_cx - dot_radius, dot_cy - dot_radius, dot_cx + dot_radius, dot_cy + dot_radius], fill=colors["dot"])

    # Badge text
    text_x = dot_cx + dot_radius + dot_spacing
    text_y = by + ((pill_h - bh) / 2) - 2
    draw.text((text_x, text_y), clean_badge, fill=colors["fg"], font=b_font)

    # Slide counter if carousel
    if total_slides > 1:
        prog_font = get_font("arialbd.ttf", 22)
        prog_text = f"{slide_num}/{total_slides}"
        p_bbox = draw.textbbox((0, 0), prog_text, font=prog_font)
        draw.text((WIDTH - (p_bbox[2] - p_bbox[0]) - 80, 150), prog_text, fill=THEME["primary"], font=prog_font)

def draw_footer(draw: ImageDraw.ImageDraw, is_cover: bool = False):
    f_font = get_font("arialbd.ttf", 26)
    handle_text = f"{INSTAGRAM_HANDLE}  •  HPU News & Student Alerts"
    f_bbox = draw.textbbox((0, 0), handle_text, font=f_font)
    fw = f_bbox[2] - f_bbox[0]
    draw.text(((WIDTH - fw) / 2, HEIGHT - 110), handle_text, fill=THEME["primary"], font=f_font)

    sub_font = get_font("arial.ttf", 21)
    sub_text = "Save this post  •  Share with your classmates"
    s_bbox = draw.textbbox((0, 0), sub_text, font=sub_font)
    sw = s_bbox[2] - s_bbox[0]
    draw.text(((WIDTH - sw) / 2, HEIGHT - 74), sub_text, fill=THEME["footer"], font=sub_font)

def render_breaking_card(headline: str, category: str = "GENERAL", details: str = "", badge: str = "BREAKING NEWS") -> str:
    """Renders a single 1080x1350 card with light green palette and solid black typography (zero URLs)."""
    img = Image.new("RGB", (WIDTH, HEIGHT), THEME["bg"])
    draw = ImageDraw.Draw(img)

    # Draw soft light green effects & framing
    draw_light_green_effects(draw)
    draw_header(draw, badge)

    # Clean, human headline in solid black
    clean_h = clean_ascii_text(headline)
    h_font = get_font("arialbd.ttf", 56)
    h_lines = wrap_text(clean_h, h_font, WIDTH - 180, draw)
    h_height = len(h_lines) * 75
    y_start = 305

    for i, line in enumerate(h_lines):
        bbox = draw.textbbox((0, 0), line, font=h_font)
        lw = bbox[2] - bbox[0]
        draw.text(((WIDTH - lw) / 2, y_start + (i * 75)), line, fill=THEME["primary"], font=h_font)

    # Inset light content panel with soft border
    box_top = y_start + h_height + 40
    box_bottom = HEIGHT - 180
    draw.rounded_rectangle([70, box_top, WIDTH - 70, box_bottom], radius=20, fill=THEME["card_bg"], outline=THEME["inner_border"], width=2)

    # Clean bullet points in solid black
    clean_details = clean_ascii_text(details)
    clean_details = re.sub(r'https?://\S+', '', clean_details)
    clean_details = re.sub(r'(?:www\.)?(?:nexams|nadmissions|hpushimla|hpuniv)\S+', 'student portal', clean_details)
    clean_details = re.sub(r'\s*-\s*(?:ANI\s*News|Amar\s*Ujala|Divya\s*Himachal|The\s*Tribune|Hindustan\s*Times|Times\s*of\s*India|Indian\s*Express|Jagran|News18).*$', '', clean_details, flags=re.IGNORECASE)
    clean_details = clean_details.strip()
    
    d_font = get_font("arialbd.ttf", 34)
    d_lines = wrap_text(clean_details, d_font, WIDTH - 240, draw)
    
    dy = box_top + 45
    for line in d_lines[:8]:
        draw.ellipse([105, dy + 12, 115, dy + 22], fill=THEME["bullet_dot"])
        draw.text((128, dy), line, fill=THEME["primary"], font=d_font)
        dy += 54

    draw_footer(draw, is_cover=True)

    out_path = OUTPUT_DIR / f"hpu_card_{uuid.uuid4().hex[:8]}.png"
    img.save(str(out_path), "PNG", quality=95)
    return str(out_path)

def render_carousel_slides(carousel_data: dict) -> list:
    """Renders 2-5 clean light-green slides with solid black text (zero URLs, human feel like @hpuupdates)."""
    slides = carousel_data.get("slides", [])
    badge = carousel_data.get("badge", "UPDATE")
    total = len(slides)
    slide_paths = []

    for idx, s in enumerate(slides, start=1):
        img = Image.new("RGB", (WIDTH, HEIGHT), THEME["bg"])
        draw = ImageDraw.Draw(img)

        # Draw light green effects & framing
        draw_light_green_effects(draw)
        draw_header(draw, badge, slide_num=idx, total_slides=total)

        if idx == 1:
            # COVER SLIDE
            title = clean_ascii_text(s.get("title", carousel_data.get("headline", "HPU Update")))
            subtitle = clean_ascii_text(s.get("subtitle", ""))

            t_font = get_font("arialbd.ttf", 62)
            t_lines = wrap_text(title, t_font, WIDTH - 180, draw)
            total_th = len(t_lines) * 82
            y_start = (HEIGHT - total_th) / 2 - 30

            for i, line in enumerate(t_lines):
                bbox = draw.textbbox((0, 0), line, font=t_font)
                lw = bbox[2] - bbox[0]
                draw.text(((WIDTH - lw) / 2, y_start + (i * 82)), line, fill=THEME["primary"], font=t_font)

            if subtitle:
                sub_font = get_font("arialbd.ttf", 34)
                s_bbox = draw.textbbox((0, 0), subtitle, font=sub_font)
                sw = s_bbox[2] - s_bbox[0]
                draw.text(((WIDTH - sw) / 2, y_start + total_th + 35), subtitle, fill=THEME["accent"], font=sub_font)

            # Swipe cue (clean ASCII, no emoji missing box)
            sw_font = get_font("arialbd.ttf", 28)
            sw_text = "SWIPE TO READ DETAILS  >>"
            sw_bbox = draw.textbbox((0, 0), sw_text, font=sw_font)
            sw_w = sw_bbox[2] - sw_bbox[0]
            draw.text(((WIDTH - sw_w) / 2, HEIGHT - 200), sw_text, fill=THEME["primary"], font=sw_font)

        else:
            # DETAIL SLIDES
            heading = clean_ascii_text(s.get("heading", "Key Information"))
            points = s.get("points", [])

            h_font = get_font("arialbd.ttf", 48)
            draw.text((90, 240), heading, fill=THEME["primary"], font=h_font)
            draw.line([(90, 305), (WIDTH - 90, 305)], fill=THEME["border"], width=3)

            box_top = 330
            box_bottom = HEIGHT - 180
            draw.rounded_rectangle([70, box_top, WIDTH - 70, box_bottom], radius=18, fill=THEME["card_bg"], outline=THEME["inner_border"], width=2)

            p_font = get_font("arialbd.ttf", 35)
            py = box_top + 45
            for pt in points:
                # Strip out any URLs or sources
                clean_pt = clean_ascii_text(pt)
                clean_pt = re.sub(r'https?://\S+', '', clean_pt)
                clean_pt = re.sub(r'(?:www\.)?(?:nexams|nadmissions|hpushimla|hpuniv)\S+', 'student portal', clean_pt)
                clean_pt = re.sub(r'(?:source|verified from|check on):\s*[\w\.\-/]+', '', clean_pt, flags=re.IGNORECASE)
                clean_pt = clean_pt.strip()
                if not clean_pt:
                    continue

                wrapped_pt = wrap_text(clean_pt, p_font, WIDTH - 240, draw)
                for line_i, line in enumerate(wrapped_pt):
                    if line_i == 0:
                        # Draw green status bullet dot
                        draw.ellipse([105, py + 12, 117, py + 24], fill=THEME["bullet_dot"])
                        draw.text((130, py), line, fill=THEME["primary"], font=p_font)
                    else:
                        draw.text((130, py), line, fill=THEME["primary"], font=p_font)
                    py += 52
                py += 26

        draw_footer(draw, is_cover=(idx == 1))

        slide_file = OUTPUT_DIR / f"slide_{uuid.uuid4().hex[:8]}_{idx}.png"
        img.save(str(slide_file), "PNG", quality=95)
        slide_paths.append(str(slide_file))

    return slide_paths

