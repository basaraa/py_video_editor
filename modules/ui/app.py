import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from modules.config import format_time, get_video_files, parse_time
from modules.ffmpeg_builder import extract_frame_png
from modules.media_probe import get_media_info, supports_nvenc
from modules.processor import process_batch
from modules.ui.tab_audio import (
    build_audio_tab,
    get_selected_audio_languages,
    update_audio_list,
    update_selected_file_audio_info,
)
from modules.ui.tab_crop import (
    build_crop_tab,
    draw_crop_overlay,
    read_crop_fields,
    set_crop_fields,
    update_crop_result,
)
from modules.ui.tab_cut import build_cut_tab, stop_playback, update_cut_labels
from modules.ui.tab_operations import build_operations_tab
from modules.ui.tab_resolution import (
    build_resolution_profiles,
    build_resolution_tab,
    get_resolution_profiles,
)
from modules.ui.tab_subtitles import (
    build_subtitle_tab,
    get_selected_subtitle_languages,
    update_subtitle_list,
)


class VideoBatchProcessor:
    def __init__(self, root):
        self.root = root
        self.root.title("Video Batch Processor — Crop / Cut / Resolution / HDR")
        self.root.geometry("1350x900")
        self.root.minsize(1100, 760)
        self.files, self.info = [], {}
        self.crop_overrides, self.cut_overrides = {}, {}
        self.subtitle_language_vars = {}
        self.audio_language_vars = {}
        self.preview_photo = None
        self.preview_seconds = 0.0
        self.preview_file = None
        self.preview_job = None
        self.preview_request_id = 0
        self.crop_drag_start_pos = None
        self.playing = False
        self.play_stop = threading.Event()
        self.play_thread = None
        self.play_fps = 25.0
        self.cut_slider_dragging = False
        self.crop_slider_dragging = False
        self.slider_programmatic = False
        self.resolution_vars = {}

        self.vars = {
            "audio_convert": tk.BooleanVar(value=False),
            "video_convert": tk.BooleanVar(value=False),
            "remove_hdr": tk.BooleanVar(value=False),
            "subtitle_insert": tk.BooleanVar(value=False),
            "subtitle_mode": tk.StringVar(value="add"),
            "audio_tracks_to_keep": tk.StringVar(value=""),
            "audio_keep_mode": tk.StringVar(value="all"),
            "audio_filter_enabled": tk.BooleanVar(value=False),
            "recursive_scan": tk.BooleanVar(value=False),
            "export_audio": tk.BooleanVar(value=False),
            "container_format": tk.StringVar(value=".mkv"),
            "extract_subs": tk.BooleanVar(value=False),
            "crop_enabled": tk.BooleanVar(value=False),
            "cut_enabled": tk.BooleanVar(value=False),
            "crop_mode": tk.StringVar(value="pixels"),
            "crop_left": tk.StringVar(value="0"),
            "crop_right": tk.StringVar(value="0"),
            "crop_top": tk.StringVar(value="0"),
            "crop_bottom": tk.StringVar(value="0"),
            "cut_start": tk.StringVar(value="00:00:00"),
            "cut_end": tk.StringVar(value="00:00:00"),
            "quality": tk.IntVar(value=27),
            "encoder": tk.StringVar(value="auto"),
            "nvenc_preset": tk.StringVar(value="p5"),
            "subtitle_keep_mode": tk.StringVar(value="all"),
        }
        self.build_ui()
        self.refresh_files()

    def selected_file(self):
        sel = self.file_list.curselection()
        if not sel:
            return None
        idx = sel[0] // 2
        return self.files[idx] if idx < len(self.files) else None

    def selected_info(self):
        f = self.selected_file()
        return self.info.get(f) if f else None

    def refresh_files(self):
        self.files = get_video_files(recursive=self.vars["recursive_scan"].get())
        self.info = {}
        for f in self.files:
            try:
                self.info[f] = get_media_info(f)
            except Exception:
                pass
        self.refresh_list()
        build_resolution_profiles(self)
        update_subtitle_list(self)
        update_audio_list(self)
        if self.files:
            self.file_list.selection_set(0)
            self.on_file_selected()
        else:
            update_selected_file_audio_info(self)
        self.update_status()

    def refresh_list(self):
        self.file_list.delete(0, "end")
        for f in self.files:
            i = self.info.get(f, {})
            self.file_list.insert("end", f"▶ {os.path.basename(f)}")

            if i:
                flags = []
                if f in self.crop_overrides:
                    flags.append("crop")
                if f in self.cut_overrides:
                    flags.append("cut")
                suffix = f"  [{', '.join(flags)}]" if flags else ""
                hdr_tag = i.get("hdr_type", "SDR")
                a_count = i.get("audio_count", 0)
                a_str = f" | {a_count} audio" if a_count > 1 else ""
                self.file_list.insert("end", f"   └ {i['width']}×{i['height']} | {format_time(i['duration'], False)} | {hdr_tag}{a_str}{suffix}")
            else:
                self.file_list.insert("end", "   └ loading info...")

    def current_options_preview(self):
        return {
            "crop_overrides": self.crop_overrides,
            "cut_overrides": self.cut_overrides,
            "crop_enabled": self.vars["crop_enabled"].get(),
            "cut_enabled": self.vars["cut_enabled"].get(),
            "crop_global": read_crop_fields(self, False),
            "cut_global": {"enabled": self.vars["cut_enabled"].get(), "start": 0, "end": 0},
        }

    def add_files(self):
        paths = filedialog.askopenfilenames(filetypes=[("Video", "*.mkv *.mp4 *.avi *.mov *.m4v *.ts *.m2ts *.webm"), ("All", "*.*")])
        if not paths:
            return
        self.files = list(paths)
        self.info = {}
        for f in self.files:
            try:
                self.info[f] = get_media_info(f)
            except Exception as e:
                messagebox.showerror("FFprobe", f"{f}\n\n{e}")
        self.refresh_list()
        build_resolution_profiles(self)
        update_subtitle_list(self)
        update_audio_list(self)
        if self.files:
            self.file_list.selection_set(0)
            self.on_file_selected()
        else:
            update_selected_file_audio_info(self)

    def on_file_selected(self, event=None):
        if self.playing:
            stop_playback(self)
        f = self.selected_file()
        if not f or f not in self.info:
            update_selected_file_audio_info(self)
            return
        self.preview_file = f
        info = self.info[f]
        if f in self.crop_overrides:
            set_crop_fields(self, self.crop_overrides[f])
        else:
            set_crop_fields(self, {"mode": self.vars["crop_mode"].get(), "left": 0, "right": 0, "top": 0, "bottom": 0})
        if f in self.cut_overrides:
            c = self.cut_overrides[f]
            self.vars["cut_start"].set(format_time(c["start"], False))
            self.vars["cut_end"].set(format_time(c["end"], False))
        else:
            self.vars["cut_start"].set("00:00:00")
            self.vars["cut_end"].set(format_time(info["duration"], False))
        self.cut_scale.configure(to=max(0.01, info["duration"]))
        self.crop_scale.configure(to=max(0.01, info["duration"]))
        self.cut_scale.set(0)
        self.crop_scale.set(0)
        self.preview_seconds = 0
        self.load_preview(0)
        update_cut_labels(self)
        update_crop_result(self)
        update_selected_file_audio_info(self)

    # ---------------- UI ----------------
    def build_ui(self):
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill="x")
        ttk.Button(top, text="Refresh videos", command=self.refresh_files).pack(side="left")
        ttk.Checkbutton(top, text="Recursive scan", variable=self.vars["recursive_scan"], command=self.refresh_files).pack(side="left", padx=6)
        ttk.Button(top, text="Add videos...", command=self.add_files).pack(side="left", padx=6)
        self.status_var = tk.StringVar()
        ttk.Label(top, textvariable=self.status_var).pack(side="right")
        paned = ttk.PanedWindow(self.root, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        left = ttk.Frame(paned, padding=5)
        right = ttk.Frame(paned, padding=5)
        paned.add(left, weight=2)
        paned.add(right, weight=5)
        ttk.Label(left, text="Videos", font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
        lf = ttk.Frame(left)
        lf.pack(fill="both", expand=True)
        self.file_list = tk.Listbox(lf, exportselection=False)
        sb = ttk.Scrollbar(lf, command=self.file_list.yview)
        self.file_list.configure(yscrollcommand=sb.set)
        self.file_list.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.file_list.bind("<<ListboxSelect>>", self.on_file_selected)
        self.notebook = ttk.Notebook(right)
        self.notebook.pack(fill="both", expand=True)

        build_operations_tab(self)
        build_audio_tab(self)
        build_subtitle_tab(self)
        build_crop_tab(self)
        build_cut_tab(self)
        build_resolution_tab(self)

        bottom = ttk.Frame(self.root, padding=8)
        bottom.pack(fill="x")
        self.run_btn = ttk.Button(bottom, text="START PROCESSING", command=self.start_processing)
        self.run_btn.pack(side="right", ipadx=20, ipady=6)
        ttk.Label(bottom, text="Operations are optional and can be combined.").pack(side="left")

    # ---------------- preview & helpers ----------------
    def _slider_click_time(self, widget, event, duration):
        try:
            width = max(1, widget.winfo_width())
            ratio = max(0.0, min(1.0, event.x / float(width)))
            return ratio * max(0.0, duration)
        except Exception:
            return None

    def schedule_preview(self, t):
        if self.preview_job:
            try:
                self.root.after_cancel(self.preview_job)
            except Exception:
                pass
        self.preview_request_id += 1
        request_id = self.preview_request_id
        self.preview_job = self.root.after(140, self.load_preview, t, request_id)

    def load_preview(self, seconds=0, request_id=None):
        f = self.selected_file()
        if not f:
            return
        dur = self.info[f]["duration"]
        seconds = max(0, min(float(seconds), max(0, dur - 0.001)))
        self.preview_seconds = seconds
        self.preview_file = f
        if request_id is None:
            self.preview_request_id += 1
            request_id = self.preview_request_id

        def worker():
            try:
                enc = extract_frame_png(f, seconds, 900)
                self.root.after(0, self.show_preview, enc, seconds, f, request_id)
            except Exception as e:
                self.root.after(0, lambda: self.preview_error(str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def show_preview(self, enc, seconds, f, request_id=None):
        if f != self.selected_file():
            return
        if request_id is not None and request_id != self.preview_request_id:
            return
        try:
            self.preview_photo = tk.PhotoImage(data=enc)
        except Exception as e:
            self.preview_error(str(e))
            return
        self.preview_seconds = seconds
        self.preview_file = f
        self.draw_preview(self.preview_photo)
        self.cut_time_label.configure(text=format_time(seconds))
        self.crop_time_label.configure(text=format_time(seconds))
        self.cut_scale.set(seconds)
        self.crop_scale.set(seconds)
        draw_crop_overlay(self)

    def draw_preview(self, photo):
        for canvas in (self.cut_canvas, self.crop_canvas):
            canvas.delete("all")
            canvas.update_idletasks()
            cw = max(100, canvas.winfo_width())
            ch = max(100, canvas.winfo_height())
            pw, ph = photo.width(), photo.height()
            x = max(0, (cw - pw) // 2)
            y = max(0, (ch - ph) // 2)
            canvas.create_image(x, y, anchor="nw", image=photo)
            canvas.image_ref = photo
        self.preview_box = self.get_preview_box(self.crop_canvas, photo)

    def get_preview_box(self, canvas, photo):
        cw = max(100, canvas.winfo_width())
        ch = max(100, canvas.winfo_height())
        return (
            max(0, (cw - photo.width()) // 2),
            max(0, (ch - photo.height()) // 2),
            max(0, (cw - photo.width()) // 2) + photo.width(),
            max(0, (ch - photo.height()) // 2) + photo.height(),
        )

    def draw_crop_overlay(self):
        draw_crop_overlay(self)

    def preview_error(self, text):
        self.cut_time_label.configure(text=f"Preview: {text}")

    # ---------------- processing ----------------
    def collect_options(self):
        profiles = get_resolution_profiles(self)
        opts = {k: v.get() for k, v in self.vars.items() if isinstance(v, tk.Variable)}
        opts["resolution_profiles"] = profiles
        opts["crop_overrides"] = dict(self.crop_overrides)
        opts["cut_overrides"] = dict(self.cut_overrides)
        opts["subtitle_languages"] = sorted(get_selected_subtitle_languages(self))
        opts["subtitle_keep"] = opts.pop("subtitle_keep_mode")
        opts["audio_keep_mode"] = self.vars["audio_keep_mode"].get()
        opts["audio_filter_enabled"] = self.vars["audio_filter_enabled"].get()
        opts["audio_languages"] = sorted(get_selected_audio_languages(self))
        opts["crop_global"] = read_crop_fields(self, True) if opts["crop_enabled"] else {"mode": "pixels", "left": 0, "right": 0, "top": 0, "bottom": 0}
        if opts["cut_enabled"]:
            s = parse_time(opts["cut_start"])
            e = parse_time(opts["cut_end"])
            if e <= s:
                raise ValueError("Global Cut: End must be greater than Start.")
            opts["cut_global"] = {"enabled": True, "start": s, "end": e}
        else:
            opts["cut_global"] = {"enabled": False, "start": 0, "end": 0}
        return opts

    def start_processing(self):
        if not self.files:
            messagebox.showwarning("Videos", "No videos selected.")
            return
        try:
            opts = self.collect_options()
        except Exception as e:
            messagebox.showerror("Settings", str(e))
            return
        self.run_btn.configure(state="disabled")
        threading.Thread(target=self.process_worker, args=(opts,), daemon=True).start()

    def process_worker(self, opts, done_cb=None):
        def on_progress(n, total, f):
            self.root.after(0, lambda n=n, total=total, f=f: self.status_var.set(f"Processing {n}/{total}: {os.path.basename(f)}"))

        done, errors = process_batch(self.files, self.info, opts, on_progress=on_progress)

        def finish():
            self.run_btn.configure(state="normal")
            if hasattr(self, "fast_audio_btn"):
                self.fast_audio_btn.configure(state="normal")
            if done_cb:
                try:
                    done_cb()
                except Exception:
                    pass
            self.update_status()
            if errors:
                messagebox.showerror("Completed with errors", f"Processed: {done}\nErrors: {len(errors)}\n\n" + "\n".join(errors))
            else:
                messagebox.showinfo("Done", f"Processing completed.\nProcessed videos: {done}")

        self.root.after(0, finish)

    def update_status(self):
        self.status_var.set(f"{len(self.files)} videos | NVENC: {'yes' if supports_nvenc() else 'no'}")
