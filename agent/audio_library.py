import os
import random
import subprocess
from pathlib import Path
import imageio_ffmpeg
from .config import BASE_DIR, OUTPUT_DIR, AUDIO_DIR

# Top 10 Iconic Atmospheric & Motivational Tracks from the Instagram Library
INSTAGRAM_AUDIO_TRACKS = [
    {
        "id": "experience",
        "title": "Experience",
        "artist": "Ludovico Einaudi",
        "audio_name": "Ludovico Einaudi • Experience",
        "genre": "Neoclassical / Emotional Piano",
        "filename": "experience.mp3"
    },
    {
        "id": "cornfield_chase",
        "title": "Cornfield Chase",
        "artist": "Hans Zimmer",
        "audio_name": "Hans Zimmer • Cornfield Chase",
        "genre": "Cinematic Orchestral / Interstellar",
        "filename": "cornfield_chase.mp3"
    },
    {
        "id": "solitude",
        "title": "Solitude (Freats Slowed)",
        "artist": "M83",
        "audio_name": "M83 • Solitude (Freats Slowed)",
        "genre": "Slowed Atmospheric / Mindset",
        "filename": "solitude.mp3"
    },
    {
        "id": "reflections",
        "title": "Reflections",
        "artist": "Toshifumi Hinata",
        "audio_name": "Toshifumi Hinata • Reflections",
        "genre": "Introspective Piano & Strings",
        "filename": "reflections.mp3"
    },
    {
        "id": "time",
        "title": "Time",
        "artist": "Hans Zimmer",
        "audio_name": "Hans Zimmer • Time",
        "genre": "Cinematic Orchestral / Inception",
        "filename": "time.mp3"
    },
    {
        "id": "snowfall",
        "title": "Snowfall",
        "artist": "Øneheart x reidenshi",
        "audio_name": "Øneheart x reidenshi • Snowfall",
        "genre": "Atmospheric Ambient / Lo-Fi",
        "filename": "snowfall.mp3"
    },
    {
        "id": "idea22",
        "title": "Idea 22",
        "artist": "Gibran Alcocer",
        "audio_name": "Gibran Alcocer • Idea 22",
        "genre": "Virtuosic Piano / Viral Reel",
        "filename": "idea22.mp3"
    },
    {
        "id": "past_lives",
        "title": "Past Lives (Slowed)",
        "artist": "BØRNS",
        "audio_name": "BØRNS • Past Lives (Slowed)",
        "genre": "Ethereal Dream Pop",
        "filename": "past_lives.mp3"
    },
    {
        "id": "a_new_man",
        "title": "A New Man",
        "artist": "Ludwig Göransson",
        "audio_name": "Ludwig Göransson • Oppenheimer",
        "genre": "Intense Orchestral Tension",
        "filename": "a_new_man.mp3"
    },
    {
        "id": "the_long_dark",
        "title": "The Long Dark",
        "artist": "Cris Velasco",
        "audio_name": "Cris Velasco • Solitary Horizon",
        "genre": "Atmospheric Winter Soundscape",
        "filename": "the_long_dark.mp3"
    }
]

def get_track_by_id(track_id: str, duration_sec: int = 7) -> tuple:
    """Returns (audio_file_path, track_info_dict) trimmed to duration_sec."""
    track = next((t for t in INSTAGRAM_AUDIO_TRACKS if t["id"] == track_id), None)
    if not track:
        track = INSTAGRAM_AUDIO_TRACKS[0]
    
    source_mp3 = AUDIO_DIR / track["filename"]
    if not source_mp3.exists():
        # Fallback to any existing mp3
        any_mp3 = list(AUDIO_DIR.glob("*.mp3"))
        if any_mp3:
            source_mp3 = any_mp3[0]
        else:
            raise FileNotFoundError(f"No audio file found in {AUDIO_DIR}")

    out_mp3 = OUTPUT_DIR / f"trimmed_{track['id']}_{duration_sec}s.mp3"
    if not out_mp3.exists():
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        cmd = [
            ffmpeg, "-y",
            "-i", str(source_mp3),
            "-t", str(duration_sec),
            "-c:a", "libmp3lame",
            "-b:a", "192k",
            str(out_mp3)
        ]
        subprocess.run(cmd, capture_output=True, text=True)

    return str(out_mp3), track

def get_random_instagram_track(duration_sec: int = 7) -> tuple:
    """Selects a random track from the 10-track Instagram audio library."""
    track = random.choice(INSTAGRAM_AUDIO_TRACKS)
    return get_track_by_id(track["id"], duration_sec=duration_sec)
