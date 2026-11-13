import os
import shutil
import subprocess
import tempfile

from modules.config import norm_lang
from modules.ffmpeg_builder import (
    build_ffmpeg_command,
    get_crop_for_file,
    get_cut_for_file,
    get_selected_audio_streams,
    get_target_resolution,
)
from modules.media_probe import subtitle_streams
from modules.subtitles import detect_unknown_subtitle_codecs, extract_webvtt_as_srt


def process_batch(files, info_map, opts, on_progress=None):
    errors = []
    done = 0
    audio_only = bool(opts.get("audio_only"))

    for n, f in enumerate(files, 1):
        temp_files_to_cleanup = []
        try:
            if on_progress:
                on_progress(n, len(files), f)
            info = info_map[f]

            converted_srts = []
            # Only run WebVTT parsing if NOT audio-only AND subtitle extraction/insertion is requested
            need_sub_conversion = not audio_only and (opts.get("extract_subs") or opts.get("subtitle_insert"))
            if need_sub_conversion:
                unknown_decoders = detect_unknown_subtitle_codecs(f)
                all_subs = subtitle_streams(f)
                sub_track_idx = 0
                for s in all_subs:
                    is_vtt = (s["codec"] == "webvtt") or (s["codec"] == "none") or (unknown_decoders.get(s["index"]) == "webvtt")
                    if is_vtt and f.lower().endswith(".mkv"):
                        srt_text = extract_webvtt_as_srt(f, s["index"], s["language"], sub_track_index=sub_track_idx)
                        if srt_text:
                            tfd, tpath = tempfile.mkstemp(suffix=f"_{s['language']}.srt")
                            os.close(tfd)
                            with open(tpath, "w", encoding="utf-8") as srt_file:
                                srt_file.write(srt_text)
                            temp_files_to_cleanup.append(tpath)
                            converted_srts.append((tpath, s))
                    sub_track_idx += 1

                # 1. Subtitle extraction to separate files
                if opts.get("extract_subs") and f.lower().endswith(".mkv"):
                    for s in all_subs:
                        out_ext = {"subrip": "srt", "ass": "ass", "ssa": "ssa", "hdmv_pgs_subtitle": "sup"}.get(s["codec"], "srt")
                        out = f"{os.path.splitext(f)[0]}.{s['language']}.{out_ext}"
                        matching_conv = next((tpath for tpath, s_info in converted_srts if s_info["index"] == s["index"]), None)
                        if matching_conv:
                            shutil.copyfile(matching_conv, f"{os.path.splitext(f)[0]}.{s['language']}.srt")
                        elif s["codec"] != "none":
                            cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", f, "-map", f"0:{s['index']}", "-c:s", "copy", out]
                            subprocess.run(cmd, check=True)

            # 2. Audio export
            if opts.get("export_audio") and not audio_only:
                export_a = get_selected_audio_streams(f, info, opts)
                a_map = f"0:{export_a[0]['index']}" if export_a else "0:a:0?"
                subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", f, "-vn", "-map", a_map, "-c:a", "copy", "-y", os.path.splitext(f)[0] + "_audio.m4a"], check=True)

            # 3. Video processing
            if audio_only:
                all_audio = info.get("audio_streams", [])
                sel_audio = get_selected_audio_streams(f, info, opts)
                # Process only if multi-track video and tracks are actually filtered
                if len(all_audio) > 1 and len(sel_audio) != len(all_audio):
                    cmd = build_ffmpeg_command(f, opts, info)
                    subprocess.run(cmd, check=True)
                    done += 1
            else:
                crop = get_crop_for_file(f, info, opts)
                cut = get_cut_for_file(f, opts)
                target = get_target_resolution(info, opts)
                subtitle_change = (opts["subtitle_keep"] == "none") or (opts["subtitle_keep"] == "selected")
                has_vtt_subs = len(converted_srts) > 0 if opts["subtitle_keep"] != "none" else False
                hdr_convert = opts.get("remove_hdr") and info.get("is_hdr")

                # Audio filtering check
                all_audio = info.get("audio_streams", [])
                audio_filter_active = False
                if len(all_audio) > 1:
                    if opts.get("audio_filter_enabled") or opts.get("audio_keep_mode") in ("keep_selected", "remove_selected") or opts.get("audio_tracks_to_keep"):
                        sel_audio = get_selected_audio_streams(f, info, opts)
                        if len(sel_audio) != len(all_audio):
                            audio_filter_active = True

                has = (opts["video_convert"] or opts["audio_convert"] or opts["subtitle_insert"] or
                       opts["audio_tracks_to_keep"] or crop["enabled"] or cut["enabled"] or
                       target != (info["width"], info["height"]) or subtitle_change or has_vtt_subs or hdr_convert or audio_filter_active)

                if has:
                    srts_for_video = []
                    if opts["subtitle_keep"] == "all":
                        srts_for_video = converted_srts
                    elif opts["subtitle_keep"] == "selected":
                        sel_langs = {norm_lang(l) for l in opts.get("subtitle_languages", [])}
                        srts_for_video = [(p, s_inf) for p, s_inf in converted_srts if norm_lang(s_inf["language"]) in sel_langs]

                    cmd = build_ffmpeg_command(f, opts, info, extra_converted_srts=srts_for_video)
                    subprocess.run(cmd, check=True)
                    done += 1
        except Exception as e:
            errors.append(f"{os.path.basename(f)}: {e}")
        finally:
            for tmp in temp_files_to_cleanup:
                try:
                    if os.path.exists(tmp):
                        os.remove(tmp)
                except Exception:
                    pass

    return done, errors
