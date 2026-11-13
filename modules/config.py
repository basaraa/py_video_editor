"""Configuration constants and general utility helpers."""

import os
import shutil

VIDEO_EXTENSIONS = {".mkv", ".avi", ".mp4", ".mov", ".m4v", ".ts", ".m2ts", ".webm"}

# Normalization table for language codes (ISO 639-1, 639-2/B, 639-2/T and abbreviations)
LANG_MAP = {
    "cs": "cze", "ces": "cze", "cze": "cze", "cz": "cze", "czech": "cze",
    "sk": "slo", "slk": "slo", "slo": "slo", "slovak": "slo",
    "en": "eng", "eng": "eng", "english": "eng",
    "zh": "chi", "zho": "chi", "chi": "chi", "chinese": "chi",
    "de": "ger", "deu": "ger", "ger": "ger", "german": "ger",
    "fr": "fre", "fra": "fre", "fre": "fre", "french": "fre",
    "es": "spa", "spa": "spa", "spanish": "spa",
    "it": "ita", "ita": "ita", "italian": "ita",
    "ru": "rus", "rus": "rus", "russian": "rus",
    "pl": "pol", "pol": "pol", "polish": "pol",
    "hu": "hun", "hun": "hun", "hungarian": "hun",
    "uk": "ukr", "ukr": "ukr", "ukrainian": "ukr",
    "ja": "jpn", "jpn": "jpn", "japanese": "jpn",
    "ko": "kor", "kor": "kor", "korean": "kor",
    "pt": "por", "por": "por", "portuguese": "por",
    "nl": "dut", "nld": "dut", "dut": "dut", "dutch": "dut",
    "sv": "swe", "swe": "swe", "swedish": "swe",
    "da": "dan", "dan": "dan", "danish": "dan",
    "fi": "fin", "fin": "fin", "finnish": "fin",
    "no": "nor", "nor": "nor", "nob": "nor", "nno": "nor", "norwegian": "nor",
    "tr": "tur", "tur": "tur", "turkish": "tur",
    "ro": "rum", "ron": "rum", "rum": "rum", "romanian": "rum",
    "hr": "hrv", "hrv": "hrv", "croatian": "hrv",
    "sr": "srp", "srp": "srp", "serbian": "srp",
    "bg": "bul", "bul": "bul", "bulgarian": "bul",
    "el": "gre", "ell": "gre", "gre": "gre", "greek": "gre",
    "ar": "ara", "ara": "ara", "arabic": "ara",
}


def norm_lang(code):
    """Normalize ISO 639-1/2 language tags and common names to 3-letter codes."""
    if not code:
        return "und"
    c = str(code).strip().lower().split("-")[0].split("_")[0]
    return LANG_MAP.get(c, c or "und")


def tool_exists(name):
    """Return True if an external CLI binary is available in PATH or standard Windows install dir."""
    if shutil.which(name) is not None:
        return True
    if name == "mkvextract" and os.path.exists(r"C:\Program Files\mkvtoolnix\mkvextract.exe"):
        return True
    return False


def get_video_files(folder=".", recursive=False):
    """List video files in folder (optionally scanning subdirectories)."""
    if not recursive:
        return sorted(f for f in os.listdir(folder) if os.path.splitext(f)[1].lower() in VIDEO_EXTENSIONS)
    matches = []
    for root, _, files in os.walk(folder):
        for f in files:
            if os.path.splitext(f)[1].lower() in VIDEO_EXTENSIONS:
                matches.append(os.path.relpath(os.path.join(root, f), folder))
    return sorted(matches)


def format_time(seconds, ms=True):
    """Format seconds as HH:MM:SS or HH:MM:SS.mmm."""
    seconds = max(0.0, float(seconds or 0))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if ms:
        milli = int(round((seconds - int(seconds)) * 1000))
        if milli >= 1000:
            s += 1
            milli = 0
        if s >= 60:
            s = 0
            m += 1
        if m >= 60:
            m = 0
            h += 1
        return f"{h:02d}:{m:02d}:{s:02d}.{milli:03d}"
    return f"{h:02d}:{m:02d}:{s:02d}"


def parse_time(text):
    """Parse HH:MM:SS(.mmm), MM:SS, or raw seconds into float seconds."""
    text = str(text).strip().replace(",", ".")
    if not text:
        return 0.0
    if ":" in text:
        p = text.split(":")
        if len(p) == 3:
            return float(p[0]) * 3600 + float(p[1]) * 60 + float(p[2])
        if len(p) == 2:
            return float(p[0]) * 60 + float(p[1])
    return float(text)


def even(n):
    """Round integer down to nearest even number."""
    n = int(n)
    return n if n % 2 == 0 else n - 1
