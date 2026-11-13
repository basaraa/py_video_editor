import base64
import os
import subprocess

from modules.config import even, norm_lang
from modules.media_probe import subtitle_streams, supports_nvenc


def clamp_crop(info, vals):
    w, h = info["width"], info["height"]
    unit = vals.get("mode", "pixels")

    def cv(v, base):
        return round(base * float(v) / 100.0) if unit == "percent" else int(round(float(v)))

    left = max(0, cv(vals.get("left", 0), w))
    right = max(0, cv(vals.get("right", 0), w))
    top = max(0, cv(vals.get("top", 0), h))
    bottom = max(0, cv(vals.get("bottom", 0), h))
    if left + right >= w - 2:
        right = max(0, w - left - 2)
    if top + bottom >= h - 2:
        bottom = max(0, h - top - 2)
    x, y = left, top
    cw, ch = even(w - left - right), even(h - top - bottom)
    if cw < 2:
        cw = 2
    if ch < 2:
        ch = 2
    return x, y, cw, ch


def get_crop_for_file(file, info, options):
    if file in options.get("crop_overrides", {}):
        v = options["crop_overrides"][file]
        x, y, w, h = clamp_crop(info, v)
        return {"enabled": True, "x": x, "y": y, "w": w, "h": h}
    if options.get("crop_enabled"):
        x, y, w, h = clamp_crop(info, options["crop_global"])
        return {"enabled": True, "x": x, "y": y, "w": w, "h": h}
    return {"enabled": False, "x": 0, "y": 0, "w": info["width"], "h": info["height"]}


def get_cut_for_file(file, options):
    if file in options.get("cut_overrides", {}):
        return options["cut_overrides"][file]
    if options.get("cut_enabled"):
        return options["cut_global"]
    return {"enabled": False, "start": 0.0, "end": 0.0}


def get_target_resolution(info, options):
    return tuple(options.get("resolution_profiles", {}).get(
        f"{info['width']}x{info['height']}", (info["width"], info["height"])
    ))


def quality_encoder_args(options):
    q = int(options.get("quality", 27))
    encoder = options.get("encoder", "auto")
    if encoder in ("auto", "nvenc") and supports_nvenc():
        return ["-c:v", "hevc_nvenc", "-preset", options.get("nvenc_preset", "p5"),
                "-rc", "vbr", "-cq", str(q), "-b:v", "0"]
    return ["-c:v", "libx265", "-preset", "medium", "-crf", str(q)]


def build_video_filter(file, info, options):
    filters = []
    cut = get_cut_for_file(file, options)
    crop = get_crop_for_file(file, info, options)
    target_w, target_h = get_target_resolution(info, options)

    if cut["enabled"]:
        filters += [f"trim=start={cut['start']:.6f}:end={cut['end']:.6f}", "setpts=PTS-STARTPTS"]
    if crop["enabled"]:
        filters.append(f"crop={crop['w']}:{crop['h']}:{crop['x']}:{crop['y']}")
    profile_is_original = (target_w, target_h) == (info["width"], info["height"])
    if (target_w, target_h) != (crop["w"], crop["h"]) and not (crop["enabled"] and profile_is_original):
        filters.append(f"scale={target_w}:{target_h}:flags=lanczos")

    # HDR -> SDR Tonemapping (BT.709)
    if options.get("remove_hdr") and info.get("is_hdr"):
        filters.append("libplacebo=tonemapping=bt.2390:colorspace=bt709:color_primaries=bt709:color_trc=bt709:format=yuv420p")

    return ",".join(filters) if filters else None


def get_selected_audio_streams(file, info, options):
    all_audio = info.get("audio_streams", [])
    if not all_audio:
        return []

    # Safety: If video only has 1 audio track, NEVER delete it!
    if len(all_audio) <= 1:
        return list(all_audio)

    # Backward compatibility with manual audio_tracks_to_keep (e.g. "1, 2")
    manual_tracks = str(options.get("audio_tracks_to_keep", "")).strip()
    if manual_tracks:
        keep_idxs = set()
        for t in manual_tracks.split(","):
            t = t.strip()
            if t.isdigit():
                keep_idxs.add(int(t) - 1)
        selected = [s for s in all_audio if s["audio_index"] in keep_idxs]
        if selected:
            return selected

    keep_mode = options.get("audio_keep_mode", "all")
    if keep_mode == "all":
        return list(all_audio)

    sel_langs = {norm_lang(l) for l in options.get("audio_languages", [])}
    if keep_mode == "keep_selected":
        selected = [s for s in all_audio if norm_lang(s["language"]) in sel_langs]
    elif keep_mode == "remove_selected":
        selected = [s for s in all_audio if norm_lang(s["language"]) not in sel_langs]
    else:
        selected = list(all_audio)

    # Safety guard: Never leave a video without audio! Fallback to default or first track
    if not selected:
        default_stream = next((s for s in all_audio if s.get("default")), all_audio[0])
        selected = [default_stream]

    return selected


def build_ffmpeg_command(file, options, info, extra_converted_srts=None):
    base = os.path.splitext(file)[0]
    ext = options.get("container_format", ".mkv")
    output = f"{base}_processed{ext}"
    if os.path.abspath(output) == os.path.abspath(file):
        output = f"{base}_processed.mkv"

    extra_srts = extra_converted_srts or []
    cmd = ["ffmpeg", "-hide_banner", "-analyzeduration", "200M", "-probesize", "200M", "-i", file]

    for srt_path, _ in extra_srts:
        cmd += ["-i", srt_path]

    external_srt = base + ".srt" if options.get("subtitle_insert") else None
    if external_srt and os.path.exists(external_srt):
        cmd += ["-i", external_srt]

    audio_only = bool(options.get("audio_only"))

    vf = None if audio_only else build_video_filter(file, info, options)
    crop = {"enabled": False} if audio_only else get_crop_for_file(file, info, options)
    cut = {"enabled": False} if audio_only else get_cut_for_file(file, options)
    target = (info["width"], info["height"]) if audio_only else get_target_resolution(info, options)
    hdr_convert = False if audio_only else (options.get("remove_hdr") and info.get("is_hdr"))
    video_encode = False if audio_only else (options.get("video_convert") or crop["enabled"] or cut["enabled"] or target != (info["width"], info["height"]) or hdr_convert)

    cmd += ["-map", "0:v:0"]
    if video_encode:
        if vf:
            cmd += ["-vf", vf]
        cmd += quality_encoder_args(options)
        cmd += ["-pix_fmt", "yuv420p"]
        if options.get("remove_hdr") and info.get("is_hdr"):
            cmd += ["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]
    else:
        cmd += ["-c:v", "copy"]

    selected_audio = get_selected_audio_streams(file, info, options)
    if selected_audio:
        for out_a_idx, a_stream in enumerate(selected_audio):
            cmd += ["-map", f"0:{a_stream['index']}"]
            if cut["enabled"] and not audio_only:
                cmd += [f"-filter:a:{out_a_idx}", f"atrim=start={cut['start']:.6f}:end={cut['end']:.6f},asetpts=PTS-STARTPTS"]
                cmd += [f"-c:a:{out_a_idx}", "aac", f"-b:a:{out_a_idx}", "192k"]
            elif options.get("audio_convert") and a_stream["codec"].lower() == "eac3" and not audio_only:
                cmd += [f"-c:a:{out_a_idx}", "aac", f"-b:a:{out_a_idx}", "160k"]
            else:
                cmd += [f"-c:a:{out_a_idx}", "copy"]
    else:
        cmd += ["-map", "0:a?"]
        if options.get("audio_convert") and info.get("audio_codec", "").lower() == "eac3" and not audio_only:
            cmd += ["-c:a", "aac", "-b:a", "160k"]
        else:
            cmd += ["-c:a", "copy"]

    if audio_only:
        cmd += ["-map", "0:s?", "-c:s", "copy"]
    else:
        keep_subs = options.get("subtitle_keep", "all")
        subtitle_list = subtitle_streams(file)
        converted_indices = {s_info["index"] for _, s_info in extra_srts}

        if keep_subs == "all":
            selected_subs = [s for s in subtitle_list if s["index"] not in converted_indices and s["codec"] != "none"]
        elif keep_subs == "selected":
            selected_languages = {norm_lang(l) for l in options.get("subtitle_languages", [])}
            selected_subs = [s for s in subtitle_list if norm_lang(s["language"]) in selected_languages and s["index"] not in converted_indices and s["codec"] != "none"]
        else:
            selected_subs = []

        out_sub_idx = 0
        for s in selected_subs:
            cmd += ["-map", f"0:{s['index']}"]
            if ext.lower() in (".mkv", ".webm"):
                cmd += [f"-c:s:{out_sub_idx}", "copy"]
            else:
                cmd += [f"-c:s:{out_sub_idx}", "mov_text"]
            out_sub_idx += 1

        curr_input = 1
        for srt_path, s_info in extra_srts:
            cmd += ["-map", f"{curr_input}:0"]
            if ext.lower() in (".mkv", ".webm"):
                cmd += [f"-c:s:{out_sub_idx}", "subrip"]
            else:
                cmd += [f"-c:s:{out_sub_idx}", "mov_text"]
            cmd += [f"-metadata:s:s:{out_sub_idx}", f"language={norm_lang(s_info.get('language', 'und'))}"]
            if s_info.get("title"):
                cmd += [f"-metadata:s:s:{out_sub_idx}", f"title={s_info.get('title')}"]
            out_sub_idx += 1
            curr_input += 1

        if external_srt and os.path.exists(external_srt):
            cmd += ["-map", f"{curr_input}:0"]
            if ext.lower() in (".mkv", ".webm"):
                cmd += [f"-c:s:{out_sub_idx}", "subrip"]
            else:
                cmd += [f"-c:s:{out_sub_idx}", "mov_text"]
            out_sub_idx += 1
            curr_input += 1

    if ext.lower() in (".mkv", ".webm"):
        cmd += ["-map", "0:t?", "-c:t", "copy"]

    cmd += ["-map_metadata", "0", "-y", output]
    return cmd


def extract_frame_png(file, seconds, width=900):
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{max(0, seconds):.3f}",
           "-i", file, "-frames:v", "1", "-vf", f"scale={width}:-2", "-f", "image2pipe", "-vcodec", "png", "pipe:1"]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode or not r.stdout:
        raise RuntimeError(r.stderr.decode("utf-8", errors="replace").strip() or "Preview failed.")
    return base64.b64encode(r.stdout).decode("ascii")
