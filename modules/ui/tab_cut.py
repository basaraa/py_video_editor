import subprocess
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from modules.config import even, format_time, parse_time

try:
    from PIL import Image, ImageTk
except Exception:
    Image = None
    ImageTk = None


def build_cut_tab(app):
    tab = ttk.Frame(app.notebook, padding=8)
    app.notebook.add(tab, text="CUT")
    row = ttk.Frame(tab)
    row.pack(fill="x")
    ttk.Label(row, text="Start:").pack(side="left")
    ttk.Entry(row, textvariable=app.vars["cut_start"], width=13).pack(side="left", padx=5)
    ttk.Label(row, text="End:").pack(side="left", padx=(12, 0))
    ttk.Entry(row, textvariable=app.vars["cut_end"], width=13).pack(side="left", padx=5)
    ttk.Button(row, text="Set globally", command=lambda: apply_global_cut(app)).pack(side="left", padx=8)
    ttk.Button(row, text="Save for video", command=lambda: save_cut_override(app)).pack(side="left")
    ttk.Label(tab, text="Time format is always HH:MM:SS. During playback, you can set Start/End directly at the current frame.", foreground="#555").pack(anchor="w", pady=5)
    app.cut_range_var = tk.StringVar()
    ttk.Label(tab, textvariable=app.cut_range_var, font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
    app.cut_scale = ttk.Scale(tab, from_=0, to=1, orient="horizontal", command=lambda v: on_cut_slider(app, v))
    app.cut_scale.pack(fill="x", pady=5)
    app.cut_scale.bind("<Button-1>", lambda e: on_cut_scale_click(app, e))
    marker_row = ttk.Frame(tab)
    marker_row.pack(fill="x")
    app.cut_start_marker = ttk.Label(marker_row, text="Start: 00:00:00")
    app.cut_start_marker.pack(side="left")
    app.cut_current_marker = ttk.Label(marker_row, text="Current: 00:00:00")
    app.cut_current_marker.pack(side="left", expand=True)
    app.cut_end_marker = ttk.Label(marker_row, text="End: 00:00:00")
    app.cut_end_marker.pack(side="right")
    app.cut_time_label = ttk.Label(tab, text="00:00:00.000")
    app.cut_time_label.pack(anchor="w")
    app.cut_canvas = tk.Canvas(tab, background="black", highlightthickness=1)
    app.cut_canvas.pack(fill="both", expand=True, pady=5)
    buttons = ttk.Frame(tab)
    buttons.pack(fill="x", pady=5)
    app.play_btn = ttk.Button(buttons, text="▶ Play in window", command=lambda: toggle_play(app))
    app.play_btn.pack(side="left")
    ttk.Button(buttons, text="⏮ Frame to Start", command=lambda: preview_cut_start(app)).pack(side="left", padx=5)
    ttk.Button(buttons, text="Frame to End ⏭", command=lambda: preview_cut_end(app)).pack(side="left", padx=5)
    ttk.Button(buttons, text="Set START = current", command=lambda: set_cut_start_current(app)).pack(side="left", padx=12)
    ttk.Button(buttons, text="Set END = current", command=lambda: set_cut_end_current(app)).pack(side="left", padx=5)
    ttk.Button(buttons, text="Clear cut for video", command=lambda: clear_cut_override(app)).pack(side="right")
    app.vars["cut_start"].trace_add("write", lambda *a: update_cut_labels(app))
    app.vars["cut_end"].trace_add("write", lambda *a: update_cut_labels(app))


def validate_cut(app):
    f = app.selected_file()
    dur = app.info[f]["duration"] if f else 0
    s, e = parse_time(app.vars["cut_start"].get()), parse_time(app.vars["cut_end"].get())
    if s < 0 or e <= s or e > dur + 0.05:
        raise ValueError(f"Cut must be 0 ≤ Start < End ≤ {format_time(dur)}")
    return s, e


def update_cut_labels(app):
    try:
        s = parse_time(app.vars["cut_start"].get())
        e = parse_time(app.vars["cut_end"].get())
        app.cut_range_var.set(f"CUT: {format_time(s, False)}  →  {format_time(e, False)}   |   length: {format_time(max(0, e - s), False)}")
        if hasattr(app, "cut_start_marker"):
            app.cut_start_marker.configure(text=f"Start: {format_time(s, False)}")
            app.cut_end_marker.configure(text=f"End: {format_time(e, False)}")
            app.cut_current_marker.configure(text=f"Current: {format_time(app.preview_seconds, False)}")
    except Exception:
        app.cut_range_var.set("CUT: invalid time")


def apply_global_cut(app):
    try:
        s, e = validate_cut(app)
        app.vars["cut_enabled"].set(True)
        app.cut_range_var.set(f"GLOBAL CUT: {format_time(s, False)} → {format_time(e, False)} | length {format_time(e - s, False)}")
    except Exception as ex:
        messagebox.showerror("Cut", str(ex))


def save_cut_override(app):
    f = app.selected_file()
    if not f:
        return
    try:
        s, e = validate_cut(app)
        app.cut_overrides[f] = {"enabled": True, "start": s, "end": e}
        app.refresh_list()
        update_cut_labels(app)
    except Exception as ex:
        messagebox.showerror("Cut", str(ex))


def clear_cut_override(app):
    f = app.selected_file()
    if f:
        app.cut_overrides.pop(f, None)
        app.refresh_list()
        app.on_file_selected()


def preview_cut_start(app):
    try:
        t = parse_time(app.vars["cut_start"].get())
        app.cut_scale.set(t)
        app.load_preview(t)
    except Exception as e:
        messagebox.showerror("Cut", str(e))


def preview_cut_end(app):
    try:
        t = parse_time(app.vars["cut_end"].get())
        app.cut_scale.set(t)
        app.load_preview(t)
    except Exception as e:
        messagebox.showerror("Cut", str(e))


def on_cut_scale_click(app, event):
    f = app.selected_file()
    if not f or f not in app.info:
        return
    t = app._slider_click_time(app.cut_scale, event, app.info[f]["duration"])
    if t is None:
        return
    app.slider_programmatic = False
    app.cut_scale.set(t)
    on_cut_slider(app, t)
    return "break"


def on_cut_slider(app, v):
    t = float(v)
    app.preview_seconds = t
    app.cut_time_label.configure(text=format_time(t))
    update_cut_range_visual(app)
    if hasattr(app, "cut_current_marker"):
        app.cut_current_marker.configure(text=f"Current: {format_time(t, False)}")
    if not app.slider_programmatic and not app.playing:
        app.schedule_preview(t)


def set_cut_start_current(app):
    app.vars["cut_start"].set(format_time(app.preview_seconds, False))
    update_cut_labels(app)


def set_cut_end_current(app):
    app.vars["cut_end"].set(format_time(app.preview_seconds, False))
    update_cut_labels(app)


def update_cut_range_visual(app):
    update_cut_labels(app)


def toggle_play(app):
    if app.playing:
        stop_playback(app)
        return
    f = app.selected_file()
    if not f:
        return
    try:
        s = parse_time(app.vars["cut_start"].get())
        e = parse_time(app.vars["cut_end"].get())
        if e <= s:
            raise ValueError("End must be greater than Start.")
        current = float(app.preview_seconds)
        if current < s or current >= e - 0.02:
            play_from = s
        else:
            play_from = current
    except Exception as ex:
        messagebox.showerror("Playback", str(ex))
        return
    app.playing = True
    app.play_btn.configure(text="■ Stop")
    app.play_stop.clear()
    app.play_thread = threading.Thread(target=playback_worker, args=(app, f, play_from, e), daemon=True)
    app.play_thread.start()


def stop_playback(app):
    app.play_stop.set()
    app.playing = False
    app.play_btn.configure(text="▶ Play in window")


def playback_worker(app, file, start, end):
    info = app.info[file]
    fps = max(8, min(info.get("fps") or 25, 60))
    out_w = 900
    out_h = max(2, even(round(info["height"] * out_w / info["width"])))
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{start:.3f}", "-i", file, "-t", f"{end - start:.3f}", "-vf", f"scale={out_w}:{out_h}", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"]
    try:
        size = out_w * out_h * 3
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=size)
        frame_time = 1.0 / fps
        t = start
        next_tick = time.monotonic()
        while not app.play_stop.is_set():
            data = p.stdout.read(size)
            if len(data) < size:
                break
            current = t
            t += frame_time
            app.root.after(0, show_playback_frame, app, data, out_w, out_h, current)
            next_tick += frame_time
            delay = next_tick - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            elif delay < -0.25:
                next_tick = time.monotonic()
        try:
            p.terminate()
            p.wait(timeout=0.5)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
    finally:
        app.root.after(0, stop_playback, app)


def show_playback_frame(app, data, w, h, t):
    try:
        if Image is None or ImageTk is None:
            raise RuntimeError("Playback requires Pillow: pip install pillow")
        image = Image.frombytes("RGB", (w, h), data)
        app.preview_photo = ImageTk.PhotoImage(image=image)
        app.preview_seconds = t
        app.slider_programmatic = True
        try:
            app.cut_scale.set(t)
            app.crop_scale.set(t)
        finally:
            app.slider_programmatic = False
        app.cut_time_label.configure(text=format_time(t))
        app.crop_time_label.configure(text=format_time(t))
        update_cut_range_visual(app)
        app.draw_preview(app.preview_photo)
        app.draw_crop_overlay()
    except Exception as e:
        app.preview_error(str(e))
