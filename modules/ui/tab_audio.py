import os
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from modules.config import norm_lang
from modules.ffmpeg_builder import get_selected_audio_streams


def build_audio_tab(app):
    tab = ttk.Frame(app.notebook, padding=10)
    app.notebook.add(tab, text="Audio")

    top_info = ttk.Frame(tab)
    top_info.pack(fill="x", pady=(0, 6))
    ttk.Label(top_info, text="Audio Track Retention & Removal", font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
    ttk.Label(top_info, text="Manage which audio tracks to keep or remove from multi-audio videos by language.\nSingle-track videos are automatically protected and hidden from deletion to prevent losing audio.", foreground="#555").pack(anchor="w", pady=(2, 6))

    # Filtering Mode
    mode_box = ttk.LabelFrame(tab, text="Audio Filtering Mode", padding=8)
    mode_box.pack(fill="x", pady=4)
    ttk.Radiobutton(mode_box, text="All (default — keep all audio tracks)", variable=app.vars["audio_keep_mode"], value="all", command=lambda: update_selected_file_audio_info(app)).pack(anchor="w", pady=2)
    ttk.Radiobutton(mode_box, text="Keep selected languages (Remove all other languages from multi-audio videos)", variable=app.vars["audio_keep_mode"], value="keep_selected", command=lambda: update_selected_file_audio_info(app)).pack(anchor="w", pady=2)
    ttk.Radiobutton(mode_box, text="Remove selected languages (Keep all other languages from multi-audio videos)", variable=app.vars["audio_keep_mode"], value="remove_selected", command=lambda: update_selected_file_audio_info(app)).pack(anchor="w", pady=2)

    # Standalone Fast Action button
    action_row = ttk.Frame(tab)
    action_row.pack(fill="x", pady=6)
    app.fast_audio_btn = ttk.Button(action_row, text="⚡ Run Audio Filtering Only (Fast Stream-Copy)", command=lambda: run_audio_filtering_only(app))
    app.fast_audio_btn.pack(side="left")
    ttk.Label(action_row, text="Applies audio filtering immediately without re-encoding video (takes just seconds).", foreground="#555").pack(side="left", padx=8)

    # Main horizontal split
    content = ttk.PanedWindow(tab, orient="horizontal")
    content.pack(fill="both", expand=True, pady=6)

    left_pane = ttk.Frame(content, padding=4)
    right_pane = ttk.Frame(content, padding=4)
    content.add(left_pane, weight=3)
    content.add(right_pane, weight=4)

    # Left: Batch languages frame
    app.audio_lang_group = ttk.LabelFrame(left_pane, text="Batch Languages (Multi-audio videos only)", padding=8)
    app.audio_lang_group.pack(fill="both", expand=True)
    app.audio_lang_frame = ttk.Frame(app.audio_lang_group)
    app.audio_lang_frame.pack(fill="both", expand=True)

    btn_row = ttk.Frame(app.audio_lang_group)
    btn_row.pack(fill="x", pady=(6, 0))
    ttk.Button(btn_row, text="Select all", command=lambda: set_all_audio_languages(app, True)).pack(side="left", padx=(0, 4))
    ttk.Button(btn_row, text="Deselect all", command=lambda: set_all_audio_languages(app, False)).pack(side="left", padx=4)
    ttk.Button(btn_row, text="Refresh", command=lambda: update_audio_list(app)).pack(side="right")

    # Right: Selected video inspector
    app.audio_detail_group = ttk.LabelFrame(right_pane, text="Selected Video Audio Inspector", padding=8)
    app.audio_detail_group.pack(fill="both", expand=True)
    app.audio_detail_frame = ttk.Frame(app.audio_detail_group)
    app.audio_detail_frame.pack(fill="both", expand=True)

    update_audio_list(app)
    update_selected_file_audio_info(app)


def collect_all_audio_languages(app):
    langs = set()
    for f in app.files:
        info = app.info.get(f)
        if not info:
            continue
        streams = info.get("audio_streams", [])
        # Rule: only videos with MORE THAN 1 track! If single track, nothing is shown
        if len(streams) > 1:
            for s in streams:
                langs.add(s["language"])
    return sorted(langs)


def update_audio_list(app):
    if not hasattr(app, "audio_lang_frame"):
        return
    for c in app.audio_lang_frame.winfo_children():
        c.destroy()
    langs = collect_all_audio_languages(app)
    if not langs:
        ttk.Label(app.audio_lang_frame, text="No videos with multiple audio tracks found.\nSingle-track videos are protected so their audio cannot be deleted.", foreground="#666", wraplength=320).pack(anchor="w", pady=10)
        return

    ttk.Label(app.audio_lang_frame, text="Languages found in multi-audio videos:", foreground="#555").pack(anchor="w", pady=(0, 6))
    for lang in langs:
        if lang not in app.audio_language_vars:
            app.audio_language_vars[lang] = tk.BooleanVar(value=False)
        var = app.audio_language_vars[lang]
        var.trace_add("write", lambda *a: update_selected_file_audio_info(app))
        count = sum(1 for f in app.files if len(app.info.get(f, {}).get("audio_streams", [])) > 1 for a in app.info.get(f, {}).get("audio_streams", []) if a["language"] == lang)
        ttk.Checkbutton(app.audio_lang_frame, text=f"{lang}  ({count} tracks in batch)", variable=var).pack(anchor="w", pady=2)


def set_all_audio_languages(app, value):
    for var in getattr(app, "audio_language_vars", {}).values():
        var.set(value)
    update_selected_file_audio_info(app)


def get_selected_audio_languages(app):
    return {norm_lang(lang) for lang, var in getattr(app, "audio_language_vars", {}).items() if var.get()}


def update_selected_file_audio_info(app):
    if not hasattr(app, "audio_detail_frame"):
        return
    for c in app.audio_detail_frame.winfo_children():
        c.destroy()

    f = app.selected_file()
    if not f:
        ttk.Label(app.audio_detail_frame, text="No video selected.", foreground="#666").pack(anchor="w", pady=8)
        return

    info = app.info.get(f, {})
    all_audio = info.get("audio_streams", [])
    ttk.Label(app.audio_detail_frame, text=f"File: {os.path.basename(f)}", font=("TkDefaultFont", 9, "bold")).pack(anchor="w", pady=(0, 4))

    if not all_audio:
        ttk.Label(app.audio_detail_frame, text="⚠️ No audio streams detected in this video.", foreground="#888").pack(anchor="w", pady=4)
        return

    # If only 1 audio track: show protected message and DO NOT show deletion options
    if len(all_audio) == 1:
        s = all_audio[0]
        title_part = f" — '{s['title']}'" if s.get("title") else ""
        ttk.Label(app.audio_detail_frame, text="🛡️ Protected: Single audio track detected", font=("TkDefaultFont", 9, "bold"), foreground="#2e7d32").pack(anchor="w", pady=4)
        ttk.Label(app.audio_detail_frame, text=f"Track 1: {s['language']} [{s['codec'].upper()}, {s['channels']}ch]{title_part}", foreground="#333").pack(anchor="w", padx=10, pady=2)
        ttk.Label(app.audio_detail_frame, text="This track will NEVER be deleted so the video is never left without audio.", foreground="#666", wraplength=380).pack(anchor="w", pady=(4, 0))
        return

    # Multi-audio file: preview which tracks remain under current settings
    opts = {
        "audio_keep_mode": app.vars["audio_keep_mode"].get(),
        "audio_languages": sorted(get_selected_audio_languages(app)),
        "audio_tracks_to_keep": app.vars["audio_tracks_to_keep"].get(),
    }
    selected = get_selected_audio_streams(f, info, opts)
    selected_indices = {s["audio_index"] for s in selected}

    ttk.Label(app.audio_detail_frame, text=f"Found {len(all_audio)} audio tracks ({len(selected)} will remain):", font=("TkDefaultFont", 9, "bold")).pack(anchor="w", pady=(0, 6))

    for a in all_audio:
        row = ttk.Frame(app.audio_detail_frame)
        row.pack(fill="x", pady=2)
        is_kept = a["audio_index"] in selected_indices
        default_tag = " [Default]" if a.get("default") else ""
        title_part = f" ({a['title']})" if a.get("title") else ""

        if is_kept:
            badge = "✔ KEEP"
            color = "#2e7d32"
        else:
            badge = "✖ REMOVE"
            color = "#c62828"

        ttk.Label(row, text=badge, foreground=color, font=("TkDefaultFont", 9, "bold"), width=10).pack(side="left")
        track_desc = f"Track {a['audio_index']+1}: {a['language']} [{a['codec'].upper()}, {a['channels']}ch]{title_part}{default_tag}"
        ttk.Label(row, text=track_desc).pack(side="left", padx=4)


def run_audio_filtering_only(app):
    if not app.files:
        messagebox.showwarning("Audio Filtering", "No videos selected.")
        return

    mode = app.vars["audio_keep_mode"].get()
    manual = app.vars["audio_tracks_to_keep"].get().strip()
    selected_langs = get_selected_audio_languages(app)

    if mode == "all" and not manual:
        messagebox.showinfo("Audio Filtering", "Please select either 'Keep selected languages' or 'Remove selected languages' (and check the desired languages) or specify manual track numbers.")
        return

    if mode in ("keep_selected", "remove_selected") and not selected_langs and not manual:
        messagebox.showwarning("Audio Filtering", "No audio languages checked. Please select at least one language.")
        return

    try:
        opts = app.collect_options()
    except Exception as e:
        messagebox.showerror("Settings", str(e))
        return

    # Force video and other operations off so FFmpeg runs in pure stream-copy mode
    opts["audio_only"] = True
    opts["video_convert"] = False
    opts["audio_convert"] = False
    opts["remove_hdr"] = False
    opts["crop_enabled"] = False
    opts["cut_enabled"] = False
    opts["crop_overrides"] = {}
    opts["cut_overrides"] = {}
    opts["resolution_profiles"] = {}
    opts["extract_subs"] = False
    opts["export_audio"] = False
    opts["subtitle_keep"] = "all"
    opts["subtitle_insert"] = False

    multi_audio_files = [f for f in app.files if len(app.info.get(f, {}).get("audio_streams", [])) > 1]
    if not multi_audio_files:
        messagebox.showinfo("Audio Filtering", "None of the loaded videos have multiple audio tracks.\nAll single-track videos are protected and won't be altered.")
        return

    if not messagebox.askyesno("Run Fast Audio Filtering", f"This will remove unwanted audio tracks from {len(multi_audio_files)} video(s) with multiple audio tracks using fast stream copy (no video re-encoding).\n\nSingle-track videos will remain completely untouched.\n\nProceed?"):
        return

    app.run_btn.configure(state="disabled")
    if hasattr(app, "fast_audio_btn"):
        app.fast_audio_btn.configure(state="disabled")

    def done_callback():
        app.run_btn.configure(state="normal")
        if hasattr(app, "fast_audio_btn"):
            app.fast_audio_btn.configure(state="normal")

    threading.Thread(target=app.process_worker, args=(opts, done_callback), daemon=True).start()
