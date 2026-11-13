"""Subtitle extraction and WebVTT-to-SRT conversion helpers."""

import os
import re
import shutil
import subprocess
import tempfile

from modules.config import norm_lang


def _mkvextract_bin():
    found = shutil.which("mkvextract")
    if found:
        return found
    win_default = r"C:\Program Files\mkvtoolnix\mkvextract.exe"
    return win_default if os.path.exists(win_default) else None


def vtt_text_to_srt(vtt_content):
    """Convert raw WebVTT text content into SRT format."""
    lines = vtt_content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out = []
    idx = 1
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if "-->" in line:
            break
        i += 1

    def fmt_ts(ts):
        ts = ts.replace(".", ",")
        p = ts.split(":")
        if len(p) == 2:
            return f"00:{p[0].zfill(2)}:{p[1]}"
        if len(p) == 3:
            return f"{p[0].zfill(2)}:{p[1].zfill(2)}:{p[2]}"
        return ts

    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        if "-->" not in line and i + 1 < len(lines) and "-->" in lines[i + 1]:
            i += 1
            line = lines[i].strip()

        if "-->" in line:
            parts = line.split("-->")
            if len(parts) == 2:
                start_str = parts[0].strip().split()[0]
                end_str = parts[1].strip().split()[0]
                timing = f"{fmt_ts(start_str)} --> {fmt_ts(end_str)}"
                i += 1
                text_lines = []
                while i < len(lines) and lines[i].strip():
                    t_line = re.sub(r"<[^>]+>", "", lines[i])
                    text_lines.append(t_line)
                    i += 1
                if text_lines:
                    out.append(f"{idx}\n{timing}\n" + "\n".join(text_lines) + "\n")
                    idx += 1
                continue
        i += 1
    return "\n".join(out)


def parse_mkv_subtitles_ebml(mkv_path):
    """Fallback pure-Python EBML parser for extracting text/WebVTT subtitle cues from MKV."""
    tracks = {}
    timecode_scale = 1000000
    cluster_time = 0
    try:
        with open(mkv_path, "rb") as f:
            f_size = os.path.getsize(mkv_path)

            def read_id():
                b = f.read(1)
                if not b:
                    return None
                b0 = b[0]
                if b0 == 0:
                    return None
                mask = 0x80
                length = 1
                while not (b0 & mask):
                    mask >>= 1
                    length += 1
                if length > 4:
                    return None
                val = b0
                if length > 1:
                    rest = f.read(length - 1)
                    if len(rest) != length - 1:
                        return None
                    for r in rest:
                        val = (val << 8) | r
                return val

            def read_len():
                b = f.read(1)
                if not b:
                    return None
                b0 = b[0]
                if b0 == 0:
                    return None
                mask = 0x80
                length = 1
                while not (b0 & mask):
                    mask >>= 1
                    length += 1
                val = b0 & (mask - 1)
                if length > 1:
                    rest = f.read(length - 1)
                    if len(rest) != length - 1:
                        return None
                    for r in rest:
                        val = (val << 8) | r
                if val == (1 << (7 * length)) - 1:
                    return -1
                return val

            curr_track_num = None
            while f.tell() < f_size:
                eid = read_id()
                if eid is None:
                    break
                elen = read_len()
                if elen is None:
                    break

                if eid in (0x1A45DFA3, 0x18538067, 0x1549A966, 0x1654AE6B, 0xAE, 0x1F43B675, 0xA0):
                    continue

                if elen < 0:
                    break

                data_pos = f.tell()
                if eid == 0x2AD7B1:
                    raw = f.read(elen)
                    timecode_scale = int.from_bytes(raw, "big") if raw else 1000000
                elif eid == 0xD7:
                    raw = f.read(elen)
                    curr_track_num = int.from_bytes(raw, "big") if raw else 0
                    if curr_track_num not in tracks:
                        tracks[curr_track_num] = {"codec": "", "lang": "und", "title": "", "cues": []}
                elif eid == 0x86:
                    raw = f.read(elen).decode("utf-8", errors="replace").strip()
                    if curr_track_num in tracks:
                        tracks[curr_track_num]["codec"] = raw
                elif eid in (0x22B59C, 0x22B59D):
                    raw = f.read(elen).decode("utf-8", errors="replace").strip().lower()
                    if curr_track_num in tracks:
                        tracks[curr_track_num]["lang"] = norm_lang(raw)
                elif eid == 0x536E:
                    raw = f.read(elen).decode("utf-8", errors="replace").strip()
                    if curr_track_num in tracks:
                        tracks[curr_track_num]["title"] = raw
                elif eid == 0xE7:
                    raw = f.read(elen)
                    cluster_time = int.from_bytes(raw, "big") if raw else 0
                elif eid in (0xA1, 0xA3):
                    raw = f.read(elen)
                    if len(raw) > 3:
                        b0 = raw[0]
                        if b0 != 0:
                            mask = 0x80
                            vl = 1
                            while not (b0 & mask):
                                mask >>= 1
                                vl += 1
                            t_num = b0 & (mask - 1)
                            for k in range(1, vl):
                                t_num = (t_num << 8) | raw[k]
                            if t_num in tracks and (
                                "WEBVTT" in tracks[t_num]["codec"].upper()
                                or "UTF8" in tracks[t_num]["codec"].upper()
                                or not tracks[t_num]["codec"]
                            ):
                                if len(raw) >= vl + 3:
                                    rel_time = int.from_bytes(raw[vl : vl + 2], "big", signed=True)
                                    payload = raw[vl + 3 :].decode("utf-8", errors="replace").strip()
                                    if payload:
                                        t_scale_ms = timecode_scale / 1000000.0
                                        start_ms = int((cluster_time + rel_time) * t_scale_ms)
                                        tracks[t_num]["cues"].append((start_ms, payload))
                else:
                    f.seek(data_pos + elen)
    except Exception:
        pass
    return tracks


def cues_to_srt(cues):
    """Convert parsed (start_ms, text) cues into SRT subtitle text."""
    cues.sort(key=lambda x: x[0])
    srt_blocks = []

    def fmt_time(ms):
        ms = max(0, ms)
        h = ms // 3600000
        ms %= 3600000
        m = ms // 60000
        ms %= 60000
        s = ms // 1000
        ms %= 1000
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    for i, (start_ms, text) in enumerate(cues, 1):
        if "-->" in text:
            vtt_block = vtt_text_to_srt(f"WEBVTT\n\n{text}")
            if vtt_block.strip():
                srt_blocks.append(vtt_block.strip())
                continue
        dur = min(4000, max(1200, cues[i][0] - start_ms)) if i < len(cues) else 3000
        clean_text = re.sub(r"<[^>]+>", "", text).strip()
        srt_blocks.append(f"{i}\n{fmt_time(start_ms)} --> {fmt_time(start_ms + dur)}\n{clean_text}\n")
    return "\n\n".join(srt_blocks)


def extract_webvtt_as_srt(mkv_file, stream_index, stream_lang="und", sub_track_index=None):
    """Safely extract a WebVTT track to SRT without language mismatch risk."""
    target_lang = norm_lang(stream_lang)

    # Method 1: mkvextract
    mkvextract = _mkvextract_bin()
    if mkvextract:
        try_ids = [stream_index] if sub_track_index is None else [stream_index, sub_track_index]
        for tid in try_ids:
            try:
                with tempfile.TemporaryDirectory() as td:
                    tmp_vtt = os.path.join(td, "sub.vtt")
                    subprocess.run(
                        [mkvextract, "tracks", mkv_file, f"{tid}:{tmp_vtt}"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        check=True,
                    )
                    if os.path.exists(tmp_vtt) and os.path.getsize(tmp_vtt) > 0:
                        with open(tmp_vtt, "r", encoding="utf-8", errors="replace") as vf:
                            res = vtt_text_to_srt(vf.read())
                            if res.strip():
                                return res
            except Exception:
                pass

    # Method 2: Python EBML parser fallback
    tracks = parse_mkv_subtitles_ebml(mkv_file)

    matched = [t for t in tracks.values() if t.get("cues") and norm_lang(t.get("lang")) == target_lang]
    if matched:
        return cues_to_srt(matched[0]["cues"])

    cues_tracks = [t for t in tracks.values() if t.get("cues")]
    if len(cues_tracks) == 1 and (target_lang == "und" or norm_lang(cues_tracks[0].get("lang")) in (target_lang, "und")):
        return cues_to_srt(cues_tracks[0]["cues"])

    return ""


def detect_unknown_subtitle_codecs(file):
    """Identify subtitle stream codec IDs that ffprobe could not determine."""
    try:
        r = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "verbose",
                "-analyzeduration", "200M", "-probesize", "200M",
                "-i", file, "-map", "0:s?", "-f", "null", "-",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        text = r.stderr
    except Exception:
        return {}

    result = {}
    pending_codec = None
    mapping = {
        "S_TEXT/WEBVTT": "webvtt",
        "S_TEXT/UTF8": "text",
        "S_TEXT/ASCII": "text",
        "S_TEXT/SSA": "ssa",
        "S_TEXT/ASS": "ass",
        "S_VOBSUB": "dvd_subtitle",
        "S_HDMV/PGS": "hdmv_pgs_subtitle",
        "S_DVBSUB": "dvb_subtitle",
    }
    for line in text.splitlines():
        m = re.search(r"Unknown/unsupported AVCodecID\s+([^\s]+)", line)
        if m:
            pending_codec = m.group(1).strip()
            continue
        m = re.search(r"Could not find codec parameters for stream\s+(\d+)", line)
        if m and pending_codec:
            idx = int(m.group(1))
            if pending_codec in mapping:
                result[idx] = mapping[pending_codec]
            pending_codec = None
    return result
