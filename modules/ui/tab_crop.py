import tkinter as tk
from tkinter import messagebox, ttk

from modules.config import format_time
from modules.ffmpeg_builder import clamp_crop


def build_crop_tab(app):
    tab = ttk.Frame(app.notebook, padding=8)
    app.notebook.add(tab, text="CROP")
    top = ttk.Frame(tab)
    top.pack(fill="x")
    ttk.Label(top, text="Crop margins:").pack(side="left")
    ttk.OptionMenu(top, app.vars["crop_mode"], "pixels", "pixels", "percent").pack(side="left", padx=6)
    ttk.Label(top, text="(0 = none)").pack(side="left")
    fields = ttk.Frame(tab)
    fields.pack(fill="x", pady=7)
    for label, key in [("Left", "crop_left"), ("Right", "crop_right"), ("Top", "crop_top"), ("Bottom", "crop_bottom")]:
        ttk.Label(fields, text=label).pack(side="left", padx=(4, 2))
        ttk.Entry(fields, textvariable=app.vars[key], width=8).pack(side="left", padx=(0, 10))
    ttk.Button(fields, text="Apply globally to all", command=lambda: apply_global_crop(app)).pack(side="left", padx=5)
    ttk.Button(fields, text="Save for this video only", command=lambda: save_crop_override(app)).pack(side="left", padx=5)
    ttk.Button(fields, text="Clear crop for video", command=lambda: clear_crop_override(app)).pack(side="left", padx=5)
    app.crop_result_var = tk.StringVar()
    ttk.Label(tab, textvariable=app.crop_result_var, font=("TkDefaultFont", 10, "bold")).pack(anchor="w", pady=3)
    ttk.Label(tab, text="Move the slider to any frame. The rectangle shows the cropped area.", foreground="#555").pack(anchor="w")
    app.crop_scale = ttk.Scale(tab, from_=0, to=1, orient="horizontal", command=lambda v: on_crop_slider(app, v))
    app.crop_scale.pack(fill="x", pady=5)
    app.crop_scale.bind("<Button-1>", lambda e: on_crop_scale_click(app, e))
    app.crop_time_label = ttk.Label(tab, text="00:00:00.000")
    app.crop_time_label.pack(anchor="w")
    app.crop_canvas = tk.Canvas(tab, background="black", highlightthickness=1)
    app.crop_canvas.pack(fill="both", expand=True, pady=5)
    ttk.Button(tab, text="Refresh preview", command=lambda: app.load_preview(app.preview_seconds)).pack(anchor="w")
    for v in (app.vars["crop_left"], app.vars["crop_right"], app.vars["crop_top"], app.vars["crop_bottom"], app.vars["crop_mode"]):
        v.trace_add("write", lambda *a: update_crop_result(app))


def set_crop_fields(app, v):
    app.vars["crop_mode"].set(v.get("mode", "pixels"))
    app.vars["crop_left"].set(str(v.get("left", 0)))
    app.vars["crop_right"].set(str(v.get("right", 0)))
    app.vars["crop_top"].set(str(v.get("top", 0)))
    app.vars["crop_bottom"].set(str(v.get("bottom", 0)))


def read_crop_fields(app, validate=True):
    v = {
        "mode": app.vars["crop_mode"].get(),
        "left": float(app.vars["crop_left"].get()),
        "right": float(app.vars["crop_right"].get()),
        "top": float(app.vars["crop_top"].get()),
        "bottom": float(app.vars["crop_bottom"].get()),
    }
    if validate and any(x < 0 for x in (v["left"], v["right"], v["top"], v["bottom"])):
        raise ValueError("Crop values cannot be negative.")
    return v


def apply_global_crop(app):
    try:
        read_crop_fields(app)
        app.vars["crop_enabled"].set(True)
        update_crop_result(app)
        app.refresh_list()
        messagebox.showinfo("Crop", "This crop is set globally for all videos.")
    except Exception as e:
        messagebox.showerror("Crop", str(e))


def save_crop_override(app):
    f = app.selected_file()
    if not f:
        return
    try:
        v = read_crop_fields(app)
        app.crop_overrides[f] = v
        app.refresh_list()
        update_crop_result(app)
    except Exception as e:
        messagebox.showerror("Crop", str(e))


def clear_crop_override(app):
    f = app.selected_file()
    if f:
        app.crop_overrides.pop(f, None)
        app.refresh_list()
        app.on_file_selected()


def update_crop_result(app):
    f = app.selected_file()
    if not f or f not in app.info:
        return
    try:
        v = read_crop_fields(app, False)
        x, y, w, h = clamp_crop(app.info[f], v)
        orig = app.info[f]
        app.crop_result_var.set(f"Original: {orig['width']}×{orig['height']}   →   cropped: {w}×{h}   |   cropped: left {x}px, right {orig['width']-x-w}px, top {y}px, bottom {orig['height']-y-h}px")
        draw_crop_overlay(app)
    except Exception:
        app.crop_result_var.set("Invalid crop values")


def on_crop_scale_click(app, event):
    f = app.selected_file()
    if not f or f not in app.info:
        return
    t = app._slider_click_time(app.crop_scale, event, app.info[f]["duration"])
    if t is None:
        return
    app.slider_programmatic = False
    app.crop_scale.set(t)
    on_crop_slider(app, t)
    return "break"


def on_crop_slider(app, v):
    t = float(v)
    app.preview_seconds = t
    app.crop_time_label.configure(text=format_time(t))
    if not app.slider_programmatic and not app.playing:
        app.schedule_preview(t)


def draw_crop_overlay(app):
    if not hasattr(app, "crop_canvas") or not app.preview_photo:
        return
    app.draw_preview(app.preview_photo)
    f = app.selected_file()
    info = app.info.get(f) if f else None
    if not info:
        return
    try:
        x, y, w, h = clamp_crop(info, read_crop_fields(app, False))
    except Exception:
        return
    l, t, r, b = app.preview_box
    sx = (r - l) / info["width"]
    sy = (b - t) / info["height"]
    cx = l + x * sx
    cy = t + y * sy
    cr = cx + w * sx
    cb = cy + h * sy
    app.crop_canvas.create_rectangle(cx, cy, cr, cb, outline="red", width=3)
    app.crop_canvas.create_text(cx + 6, cy + 6, text=f"{w}×{h}", anchor="nw", fill="yellow", font=("TkDefaultFont", 10, "bold"))
