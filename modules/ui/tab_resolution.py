import tkinter as tk
from tkinter import ttk


def build_resolution_tab(app):
    tab = ttk.Frame(app.notebook, padding=12)
    app.notebook.add(tab, text="Resolution")
    ttk.Label(tab, text="Output resolution is always applied. Default = original resolution. Configured in batch by source size.", wraplength=900).pack(anchor="w")
    app.resolution_frame = ttk.Frame(tab)
    app.resolution_frame.pack(fill="both", expand=True, pady=8)
    build_resolution_profiles(app)


def build_resolution_profiles(app):
    old = app.resolution_vars
    app.resolution_vars = {}
    for w, h in sorted({(app.info[f]["width"], app.info[f]["height"]) for f in app.files if f in app.info}):
        key = f"{w}x{h}"
        app.resolution_vars[key] = old.get(key, (tk.StringVar(value=str(w)), tk.StringVar(value=str(h))))
    if hasattr(app, "resolution_frame"):
        rebuild_resolution_widgets(app)


def rebuild_resolution_widgets(app):
    for c in app.resolution_frame.winfo_children():
        c.destroy()
    h = ttk.Frame(app.resolution_frame)
    h.pack(fill="x")
    ttk.Label(h, text="Original", width=18).pack(side="left")
    ttk.Label(h, text="Output W", width=15).pack(side="left")
    ttk.Label(h, text="Output H", width=15).pack(side="left")
    for key in sorted(app.resolution_vars, key=lambda k: tuple(map(int, k.split("x")))):
        wv, hv = app.resolution_vars[key]
        r = ttk.Frame(app.resolution_frame)
        r.pack(fill="x", pady=3)
        ttk.Label(r, text=key, width=18).pack(side="left")
        ttk.Entry(r, textvariable=wv, width=12).pack(side="left", padx=5)
        ttk.Entry(r, textvariable=hv, width=12).pack(side="left", padx=5)
    ttk.Label(app.resolution_frame, text="E.g. 1920×1080 → 1920×1079 and 1280×720 → 1280×719 are two separate batch profiles.", foreground="#555").pack(anchor="w", pady=12)


def get_resolution_profiles(app):
    out = {}
    for key, (wv, hv) in app.resolution_vars.items():
        w, h = int(wv.get()), int(hv.get())
        if w < 2 or h < 2:
            raise ValueError(f"Invalid resolution: {key} → {w}x{h}")
        out[key] = (w, h)
    return out
