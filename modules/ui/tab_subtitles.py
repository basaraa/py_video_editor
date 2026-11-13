import tkinter as tk
from tkinter import ttk

from modules.config import norm_lang
from modules.media_probe import subtitle_languages, subtitle_streams


def build_subtitle_tab(app):
    tab = ttk.Frame(app.notebook, padding=10)
    app.notebook.add(tab, text="Subtitles")
    ttk.Label(tab, text="Subtitle retention", font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
    ttk.Radiobutton(tab, text="All (default)", variable=app.vars["subtitle_keep_mode"], value="all").pack(anchor="w", pady=3)
    ttk.Radiobutton(tab, text="None", variable=app.vars["subtitle_keep_mode"], value="none").pack(anchor="w", pady=3)
    ttk.Radiobutton(tab, text="Selected languages (globally for all videos)", variable=app.vars["subtitle_keep_mode"], value="selected").pack(anchor="w", pady=3)
    ttk.Label(tab, text="Selection matches normalized language (e.g. cze/cs, slo/sk). WebVTT is converted without track mismatch.", foreground="#555", wraplength=850).pack(anchor="w", pady=5)
    app.subtitle_frame = ttk.Frame(tab)
    app.subtitle_frame.pack(fill="both", expand=True, pady=8)
    ttk.Button(tab, text="Refresh subtitle list", command=lambda: update_subtitle_list(app)).pack(anchor="w")


def collect_all_subtitle_languages(app):
    langs = set()
    for f in app.files:
        try:
            langs.update(subtitle_languages(f))
        except Exception:
            pass
    return sorted(langs)


def update_subtitle_list(app):
    if not hasattr(app, "subtitle_frame"):
        return
    for c in app.subtitle_frame.winfo_children():
        c.destroy()
    langs = collect_all_subtitle_languages(app)
    if not langs:
        ttk.Label(app.subtitle_frame, text="No supported subtitle tracks found in the available videos.").pack(anchor="w")
        return

    ttk.Label(app.subtitle_frame, text="Selection is global based on normalized language (e.g. cze/cs, slo/sk).", foreground="#555").pack(anchor="w", pady=(0, 8))
    for lang in langs:
        if lang not in app.subtitle_language_vars:
            app.subtitle_language_vars[lang] = tk.BooleanVar(value=False)
        var = app.subtitle_language_vars[lang]
        count = sum(1 for f in app.files for s in subtitle_streams(f) if s["language"] == lang)
        ttk.Checkbutton(app.subtitle_frame, text=f"{lang}  ({count} streams in batch)", variable=var).pack(anchor="w", pady=2)
    ttk.Button(app.subtitle_frame, text="Select all languages", command=lambda: set_all_subtitle_languages(app, True)).pack(anchor="w", pady=(10, 2))
    ttk.Button(app.subtitle_frame, text="Deselect all languages", command=lambda: set_all_subtitle_languages(app, False)).pack(anchor="w")


def set_all_subtitle_languages(app, value):
    for var in getattr(app, "subtitle_language_vars", {}).values():
        var.set(value)


def get_selected_subtitle_languages(app):
    return {norm_lang(lang) for lang, var in getattr(app, "subtitle_language_vars", {}).items() if var.get()}
