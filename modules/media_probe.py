"""FFprobe media stream inspection and hardware capability detection."""

import json
import subprocess

from modules.config import norm_lang


def ffprobe_json(file):
    """Run ffprobe on a media file and return parsed JSON stream/format metadata."""
    cmd = ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", file]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise RuntimeError(r.stderr.strip() or f"ffprobe failed: {file}")
    return json.loads(r.stdout)


def parse_fps(value):
    """Parse rational frame rate string (e.g. '24000/1001') into float."""
    try:
        if "/" in str(value):
            a, b = str(value).split("/", 1)
            return float(a) / float(b) if float(b) else 0.0
        return float(value)
    except Exception:
        return 0.0


def _extract_audio_streams(data):
    out = []
    a_idx = 0
    for s in data.get("streams", []):
        if s.get("codec_type") != "audio":
            continue
        codec = (s.get("codec_name") or "none").lower()
        tags = s.get("tags", {}) or {}
        raw_lang = tags.get("language") or "und"
        channels = int(s.get("channels") or 2)
        out.append({
            "index": s.get("index"),
            "audio_index": a_idx,
            "codec": codec,
            "language": norm_lang(raw_lang),
            "orig_lang": raw_lang,
            "title": tags.get("title", ""),
            "channels": channels,
            "channel_layout": s.get("channel_layout", ""),
            "default": int((s.get("disposition", {}) or {}).get("default", 0) or 0),
        })
        a_idx += 1
    return out


def audio_streams(file):
    """Return list of audio stream dicts for a media file."""
    try:
        data = ffprobe_json(file)
    except Exception:
        return []
    return _extract_audio_streams(data)


def audio_languages(file):
    """Return sorted normalized audio languages only if file has > 1 audio track."""
    streams = audio_streams(file)
    if len(streams) <= 1:
        return []
    return sorted({x["language"] for x in streams})


def subtitle_streams(file):
    """Return list of subtitle stream dicts for a media file."""
    data = ffprobe_json(file)
    out = []
    for s in data.get("streams", []):
        if s.get("codec_type") != "subtitle":
            continue
        codec = (s.get("codec_name") or "none").lower()
        tags = s.get("tags", {}) or {}
        raw_lang = tags.get("language") or "und"
        out.append({
            "index": s.get("index"),
            "codec": codec,
            "language": norm_lang(raw_lang),
            "orig_lang": raw_lang,
            "title": tags.get("title", ""),
            "default": int((s.get("disposition", {}) or {}).get("default", 0) or 0),
        })
    return out


def subtitle_languages(file):
    """Return sorted list of normalized subtitle languages in a media file."""
    return sorted({x["language"] for x in subtitle_streams(file)})


def get_media_info(file):
    """Probe video, audio, and HDR metadata for a media file."""
    data = ffprobe_json(file)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if not video:
        raise RuntimeError("Video stream not found")
    duration = float(video.get("duration") or data.get("format", {}).get("duration") or 0)

    all_audio = _extract_audio_streams(data)
    audio = all_audio[0] if all_audio else None

    # Detection of HDR vs SDR
    color_trc = (video.get("color_transfer") or video.get("color_trc") or "").lower()
    color_primaries = (video.get("color_primaries") or "").lower()
    side_data = video.get("side_data_list", [])
    has_dovi = any("dovi" in str(sd.get("side_data_type", "")).lower() for sd in side_data)
    has_hdr_meta = any(
        "mastering display" in str(sd.get("side_data_type", "")).lower()
        or "content light level" in str(sd.get("side_data_type", "")).lower()
        for sd in side_data
    )

    is_hdr = (
        color_trc in ("smpte2084", "arib-std-b67")
        or has_dovi
        or has_hdr_meta
        or (color_primaries == "bt2020" and "10" in str(video.get("pix_fmt", "")) and color_trc not in ("bt709", "smpte170m", "bt470bg"))
    )

    return {
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "duration": duration,
        "fps": parse_fps(video.get("r_frame_rate", "0/1")),
        "video_codec": video.get("codec_name", ""),
        "pix_fmt": video.get("pix_fmt", ""),
        "audio_codec": audio.get("codec", "") if audio else "",
        "audio_streams": all_audio,
        "audio_count": len(all_audio),
        "is_hdr": is_hdr,
        "hdr_type": "HDR" if is_hdr else "SDR",
    }


def supports_nvenc():
    """Check whether ffmpeg supports NVIDIA hevc_nvenc hardware encoding."""
    try:
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return "hevc_nvenc" in r.stdout
    except Exception:
        return False
