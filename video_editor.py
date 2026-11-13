import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, ttk

try:
    from PIL import Image, ImageTk
except ImportError:
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pillow"])
        from PIL import Image, ImageTk
    except Exception:
        Image = ImageTk = None

from modules.config import tool_exists
from modules.ui.app import VideoBatchProcessor


def run_gui():
    if not tool_exists("ffmpeg") or not tool_exists("ffprobe"):
        r = tk.Tk()
        r.withdraw()
        messagebox.showerror("FFmpeg missing", "ffmpeg and ffprobe are required in PATH.")
        r.destroy()
        return
    root = tk.Tk()
    try:
        ttk.Style().theme_use("clam")
    except Exception:
        pass
    VideoBatchProcessor(root)
    root.mainloop()


if __name__ == "__main__":
    run_gui()
