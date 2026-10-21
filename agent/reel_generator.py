import os
import uuid
import subprocess
from pathlib import Path
import numpy as np
import imageio_ffmpeg
from PIL import Image
from .config import OUTPUT_DIR
from .card_renderer import WIDTH as CARD_W, HEIGHT as CARD_H
from .audio_library import get_random_instagram_track, get_track_by_id

REEL_W = 1080
REEL_H = 1920
FPS = 24
DURATION_SEC = 7
TOTAL_FRAMES = FPS * DURATION_SEC

def create_looping_reel(card_image_path: str, track_id: str = None) -> tuple:
    """
    Renders a 9:16 vertical 1080x1920 MP4 video reel with breathing motion
    AND multiplexes an iconic trending audio track from the 10-track Instagram library.
    Returns: (reel_video_path, track_info_dict)
    """
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    card_img = Image.open(card_image_path).convert("RGBA")

    raw_video_path = OUTPUT_DIR / f"raw_video_{uuid.uuid4().hex[:6]}.mp4"
    final_reel_path = OUTPUT_DIR / f"hpu_reel_{uuid.uuid4().hex[:8]}.mp4"

    # Base 9:16 canvas with Academic Prussian Navy background
    bg_sample = card_img.getpixel((20, 20))
    base_canvas = Image.new("RGBA", (REEL_W, REEL_H), bg_sample)
    card_y = (REEL_H - CARD_H) // 2
    base_canvas.paste(card_img, (0, card_y), card_img)

    # Step 1: Render video frames via imageio_ffmpeg
    writer = imageio_ffmpeg.write_frames(
        str(raw_video_path),
        (REEL_W, REEL_H),
        fps=FPS,
        codec="libx264",
        pix_fmt_in="rgba",
        macro_block_size=None,
        output_params=["-pix_fmt", "yuv420p", "-crf", "19", "-preset", "fast"]
    )
    writer.send(None)

    for f in range(TOTAL_FRAMES):
        t = f / TOTAL_FRAMES
        # Smooth breathing pulse zoom
        scale = 1.0 + 0.02 * np.sin(np.pi * t)

        scaled_w = int(REEL_W * scale)
        scaled_h = int(REEL_H * scale)
        scaled = base_canvas.resize((scaled_w, scaled_h), Image.Resampling.BILINEAR)

        left = (scaled_w - REEL_W) // 2
        top = (scaled_h - REEL_H) // 2
        frame = scaled.crop((left, top, left + REEL_W, top + REEL_H))

        writer.send(np.array(frame).tobytes())

    writer.close()

    # Step 2: Select audio track from 10-track library
    if track_id:
        audio_path, track_info = get_track_by_id(track_id, duration_sec=DURATION_SEC)
    else:
        audio_path, track_info = get_random_instagram_track(duration_sec=DURATION_SEC)

    # Step 3: Multiplex audio and video into final MP4
    clean_raw = str(raw_video_path).replace("\\", "/")
    clean_audio = str(audio_path).replace("\\", "/")
    clean_out = str(final_reel_path).replace("\\", "/")

    mux_cmd = [
        ffmpeg, "-y",
        "-i", clean_raw,
        "-i", clean_audio,
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        clean_out
    ]
    mux_res = subprocess.run(mux_cmd, capture_output=True, text=True)
    if mux_res.returncode != 0:
        raise RuntimeError(f"FFmpeg muxing failed: {mux_res.stderr}")

    try:
        os.remove(raw_video_path)
    except Exception:
        pass

    return str(final_reel_path), track_info
