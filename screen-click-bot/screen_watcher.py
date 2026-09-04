#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
桌面 OCR / 圖像自動點擊工具
============================
功能：
1. 讓使用者用滑鼠拖曳選取「監控區域」
2. 週期性截圖該區域
3. 模式 A：用 OCR 辨識文字，若出現指定文字 -> 點擊該文字位置
   模式 B：用模板圖片比對，若畫面中出現該圖片 -> 點擊該位置
4. 找到後在該座標自動點擊滑鼠左鍵（可設定點擊後暫停一段時間避免重複點擊）

依賴：
    pip install pyautogui pytesseract opencv-python pillow mss numpy

系統需求：
    需安裝 Tesseract OCR 執行檔，並設定路徑（見下方 TESSERACT_CMD）
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import time
import queue
import os
import sys
import json

import numpy as np
from PIL import Image, ImageTk
import mss
import cv2

try:
    import pytesseract
except ImportError:
    pytesseract = None

import pyautogui

# ---------------------------------------------------------------------------
# 設定檔位置：跟程式放在一起（打包成 exe 後也會在執行檔旁邊）
# ---------------------------------------------------------------------------
def _base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_PATH = os.path.join(_base_dir(), "config.json")

DEFAULT_CONFIG = {
    "tesseract_cmd": "",   # 留空 = 使用系統 PATH 中的 tesseract
    "mode": "text",
    "target_text": "",
    "ocr_lang": "chi_tra+eng",
    "exact_match": False,
    "template_path": "",
    "threshold": 0.85,
    "interval": 1.0,
    "cooldown": 3.0,
    "click_once": False,
}


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# 若使用者在 config.json 或環境變數指定了 tesseract 路徑，套用之
_cfg = load_config()
_tess_cmd = os.environ.get("TESSERACT_CMD") or _cfg.get("tesseract_cmd")
if _tess_cmd and pytesseract:
    pytesseract.pytesseract.tesseract_cmd = _tess_cmd

pyautogui.FAILSAFE = True  # 滑鼠移到螢幕左上角可緊急中止 pyautogui 動作


class RegionSelector(tk.Toplevel):
    """全螢幕半透明遮罩，讓使用者拖曳選取一個矩形區域"""

    def __init__(self, master, on_selected):
        super().__init__(master)
        self.on_selected = on_selected
        self.attributes("-fullscreen", True)
        self.attributes("-alpha", 0.3)
        self.configure(bg="black")
        self.attributes("-topmost", True)

        self.canvas = tk.Canvas(self, cursor="cross", bg="gray")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.start_x = self.start_y = 0
        self.rect = None

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.bind("<Escape>", lambda e: self.destroy())

        label = tk.Label(
            self, text="拖曳滑鼠選取監控區域（Esc 取消）",
            fg="white", bg="black", font=("Arial", 16)
        )
        label.place(relx=0.5, rely=0.05, anchor="n")

    def on_press(self, event):
        self.start_x, self.start_y = event.x, event.y
        if self.rect:
            self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y,
            outline="red", width=2
        )

    def on_drag(self, event):
        self.canvas.coords(self.rect, self.start_x, self.start_y, event.x, event.y)

    def on_release(self, event):
        x1, y1 = self.start_x, self.start_y
        x2, y2 = event.x, event.y
        left, top = min(x1, x2), min(y1, y2)
        width, height = abs(x2 - x1), abs(y2 - y1)
        self.destroy()
        if width > 5 and height > 5:
            self.on_selected((left, top, width, height))


class WatcherApp:
    def __init__(self, root):
        self.root = root
        self.root.title("桌面 OCR / 圖像自動點擊工具")
        self.root.geometry("480x560")

        self.region = None  # (left, top, width, height)
        self.template_path = None
        self.running = False
        self.watch_thread = None
        self.log_queue = queue.Queue()
        self.cfg = load_config()

        self._build_ui()
        self._apply_config_to_ui()
        self._poll_log_queue()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # UI 建構
    # ------------------------------------------------------------------
    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}

        # 區域選取
        frame_region = ttk.LabelFrame(self.root, text="1. 監控區域")
        frame_region.pack(fill="x", **pad)

        self.region_label = ttk.Label(frame_region, text="尚未選取區域")
        self.region_label.pack(side="left", padx=8, pady=8)

        ttk.Button(frame_region, text="選取螢幕區域", command=self.select_region).pack(
            side="right", padx=8, pady=8
        )

        # 模式選擇
        frame_mode = ttk.LabelFrame(self.root, text="2. 偵測模式")
        frame_mode.pack(fill="x", **pad)

        self.mode_var = tk.StringVar(value="text")
        ttk.Radiobutton(
            frame_mode, text="文字 (OCR)", variable=self.mode_var,
            value="text", command=self._toggle_mode
        ).pack(side="left", padx=10, pady=6)
        ttk.Radiobutton(
            frame_mode, text="圖像比對 (模板匹配)", variable=self.mode_var,
            value="image", command=self._toggle_mode
        ).pack(side="left", padx=10, pady=6)

        # 文字設定 / 圖像設定（共用同一個容器位置，依模式切換顯示）
        self.frame_mode_container = ttk.Frame(self.root)
        self.frame_mode_container.pack(fill="x", **pad)

        self.frame_text = ttk.LabelFrame(self.frame_mode_container, text="文字設定")

        ttk.Label(self.frame_text, text="要偵測的文字：").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        self.target_text_var = tk.StringVar()
        ttk.Entry(self.frame_text, textvariable=self.target_text_var, width=30).grid(
            row=0, column=1, padx=8, pady=6, sticky="ew"
        )

        ttk.Label(self.frame_text, text="OCR 語言 (例: eng / chi_tra / chi_sim+eng)：").grid(
            row=1, column=0, sticky="w", padx=8, pady=6
        )
        self.ocr_lang_var = tk.StringVar(value="chi_tra+eng")
        ttk.Entry(self.frame_text, textvariable=self.ocr_lang_var, width=30).grid(
            row=1, column=1, padx=8, pady=6, sticky="ew"
        )

        self.exact_match_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            self.frame_text, text="需完全符合整個字串（否則只要「包含」即符合）",
            variable=self.exact_match_var
        ).grid(row=2, column=0, columnspan=2, sticky="w", padx=8, pady=4)

        ttk.Label(self.frame_text, text="Tesseract 執行檔路徑（留空=用系統 PATH）：").grid(
            row=3, column=0, sticky="w", padx=8, pady=6
        )
        tess_row = ttk.Frame(self.frame_text)
        tess_row.grid(row=3, column=1, sticky="ew", padx=8, pady=6)
        self.tesseract_cmd_var = tk.StringVar()
        ttk.Entry(tess_row, textvariable=self.tesseract_cmd_var, width=22).pack(side="left")
        ttk.Button(tess_row, text="瀏覽", command=self._select_tesseract).pack(side="left", padx=4)

        # 圖像設定
        self.frame_image = ttk.LabelFrame(self.frame_mode_container, text="圖像設定")

        ttk.Label(self.frame_image, text="範本圖片：").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        self.template_label = ttk.Label(self.frame_image, text="尚未選取圖片")
        self.template_label.grid(row=0, column=1, sticky="w", padx=8, pady=6)
        ttk.Button(self.frame_image, text="選取圖片檔", command=self.select_template).grid(
            row=0, column=2, padx=8, pady=6
        )

        ttk.Label(self.frame_image, text="相似度門檻 (0.5~1.0)：").grid(
            row=1, column=0, sticky="w", padx=8, pady=6
        )
        self.threshold_var = tk.DoubleVar(value=0.85)
        ttk.Entry(self.frame_image, textvariable=self.threshold_var, width=10).grid(
            row=1, column=1, sticky="w", padx=8, pady=6
        )

        # 共用設定
        frame_common = ttk.LabelFrame(self.root, text="3. 執行參數")
        frame_common.pack(fill="x", **pad)

        ttk.Label(frame_common, text="掃描間隔（秒）：").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        self.interval_var = tk.DoubleVar(value=1.0)
        ttk.Entry(frame_common, textvariable=self.interval_var, width=10).grid(
            row=0, column=1, sticky="w", padx=8, pady=6
        )

        ttk.Label(frame_common, text="點擊後冷卻時間（秒）：").grid(row=1, column=0, sticky="w", padx=8, pady=6)
        self.cooldown_var = tk.DoubleVar(value=3.0)
        ttk.Entry(frame_common, textvariable=self.cooldown_var, width=10).grid(
            row=1, column=1, sticky="w", padx=8, pady=6
        )

        self.click_once_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            frame_common, text="找到後只點擊一次就停止監控",
            variable=self.click_once_var
        ).grid(row=2, column=0, columnspan=2, sticky="w", padx=8, pady=4)

        # 控制按鈕
        frame_ctrl = ttk.Frame(self.root)
        frame_ctrl.pack(fill="x", **pad)

        self.start_btn = ttk.Button(frame_ctrl, text="開始監控", command=self.start_watching)
        self.start_btn.pack(side="left", padx=8)
        self.stop_btn = ttk.Button(frame_ctrl, text="停止監控", command=self.stop_watching, state="disabled")
        self.stop_btn.pack(side="left", padx=8)

        # 狀態顯示
        frame_log = ttk.LabelFrame(self.root, text="狀態記錄")
        frame_log.pack(fill="both", expand=True, **pad)

        self.log_text = tk.Text(frame_log, height=10, state="disabled")
        self.log_text.pack(fill="both", expand=True, padx=6, pady=6)

        self._toggle_mode()

    def _apply_config_to_ui(self):
        """把上次儲存的設定套用到畫面上（找不到設定檔就用預設值）"""
        cfg = self.cfg
        self.tesseract_cmd_var.set(cfg.get("tesseract_cmd", ""))
        if cfg.get("tesseract_cmd") and pytesseract:
            pytesseract.pytesseract.tesseract_cmd = cfg["tesseract_cmd"]
        self.mode_var.set(cfg.get("mode", "text"))
        self.target_text_var.set(cfg.get("target_text", ""))
        self.ocr_lang_var.set(cfg.get("ocr_lang", "chi_tra+eng"))
        self.exact_match_var.set(cfg.get("exact_match", False))
        self.threshold_var.set(cfg.get("threshold", 0.85))
        self.interval_var.set(cfg.get("interval", 1.0))
        self.cooldown_var.set(cfg.get("cooldown", 3.0))
        self.click_once_var.set(cfg.get("click_once", False))

        tpath = cfg.get("template_path", "")
        if tpath and os.path.exists(tpath):
            self.template_path = tpath
            self.template_label.config(text=os.path.basename(tpath))

        self._toggle_mode()

    def _collect_config(self):
        return {
            "tesseract_cmd": self.tesseract_cmd_var.get(),
            "mode": self.mode_var.get(),
            "target_text": self.target_text_var.get(),
            "ocr_lang": self.ocr_lang_var.get(),
            "exact_match": self.exact_match_var.get(),
            "template_path": self.template_path or "",
            "threshold": self.threshold_var.get(),
            "interval": self.interval_var.get(),
            "cooldown": self.cooldown_var.get(),
            "click_once": self.click_once_var.get(),
        }

    def _on_close(self):
        self.running = False
        save_config(self._collect_config())
        self.root.destroy()

    def _toggle_mode(self):
        if self.mode_var.get() == "text":
            self.frame_image.pack_forget()
            self.frame_text.pack(fill="x")
        else:
            self.frame_text.pack_forget()
            self.frame_image.pack(fill="x")

    # ------------------------------------------------------------------
    # 事件處理
    # ------------------------------------------------------------------
    def select_region(self):
        self.root.iconify()
        time.sleep(0.3)  # 讓視窗有時間縮到最小，避免遮罩把自己截進去

        def on_selected(region):
            self.region = region
            self.root.deiconify()
            self.region_label.config(
                text=f"區域：left={region[0]}, top={region[1]}, w={region[2]}, h={region[3]}"
            )

        selector = RegionSelector(self.root, on_selected)
        selector.wait_window()
        self.root.deiconify()

    def _select_tesseract(self):
        path = filedialog.askopenfilename(title="選取 tesseract 執行檔")
        if path:
            self.tesseract_cmd_var.set(path)
            if pytesseract:
                pytesseract.pytesseract.tesseract_cmd = path
            self.log(f"已設定 Tesseract 路徑：{path}")

    def select_template(self):
        path = filedialog.askopenfilename(
            title="選取範本圖片",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp")]
        )
        if path:
            self.template_path = path
            self.template_label.config(text=os.path.basename(path))

    def log(self, msg):
        self.log_queue.put(f"[{time.strftime('%H:%M:%S')}] {msg}")

    def _poll_log_queue(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self.log_text.config(state="normal")
                self.log_text.insert("end", msg + "\n")
                self.log_text.see("end")
                self.log_text.config(state="disabled")
        except queue.Empty:
            pass
        self.root.after(150, self._poll_log_queue)

    def start_watching(self):
        if not self.region:
            messagebox.showwarning("提醒", "請先選取監控區域")
            return
        if self.mode_var.get() == "text":
            if pytesseract is None:
                messagebox.showerror("錯誤", "未安裝 pytesseract，請先執行 pip install pytesseract")
                return
            if not self.target_text_var.get().strip():
                messagebox.showwarning("提醒", "請輸入要偵測的文字")
                return
            tess_path = self.tesseract_cmd_var.get().strip()
            if tess_path:
                pytesseract.pytesseract.tesseract_cmd = tess_path
            try:
                pytesseract.get_tesseract_version()
            except Exception:
                messagebox.showerror(
                    "錯誤",
                    "找不到 Tesseract 執行檔。\n"
                    "請安裝 Tesseract OCR，或在上方欄位指定執行檔路徑。"
                )
                return
        else:
            if not self.template_path:
                messagebox.showwarning("提醒", "請選取範本圖片")
                return

        save_config(self._collect_config())

        self.running = True
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.log("開始監控...")

        self.watch_thread = threading.Thread(target=self._watch_loop, daemon=True)
        self.watch_thread.start()

    def stop_watching(self):
        self.running = False
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.log("已停止監控")

    # ------------------------------------------------------------------
    # 監控主迴圈（在背景執行緒執行）
    # ------------------------------------------------------------------
    def _watch_loop(self):
        left, top, width, height = self.region
        interval = max(0.1, self.interval_var.get())
        cooldown = max(0.0, self.cooldown_var.get())
        mode = self.mode_var.get()

        with mss.mss() as sct:
            monitor = {"left": left, "top": top, "width": width, "height": height}

            while self.running:
                try:
                    shot = sct.grab(monitor)
                    img = np.array(shot)  # BGRA
                    img_bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

                    found_point = None

                    if mode == "text":
                        found_point = self._find_text(img_bgr)
                    else:
                        found_point = self._find_image(img_bgr)

                    if found_point:
                        click_x = left + found_point[0]
                        click_y = top + found_point[1]
                        self.log(f"命中！點擊座標 ({click_x}, {click_y})")
                        pyautogui.click(click_x, click_y)

                        if self.click_once_var.get():
                            self.log("已設定「只點擊一次」，停止監控")
                            self.running = False
                            self.root.after(0, lambda: (
                                self.start_btn.config(state="normal"),
                                self.stop_btn.config(state="disabled")
                            ))
                            break

                        time.sleep(cooldown)
                    else:
                        time.sleep(interval)

                except Exception as e:
                    self.log(f"發生錯誤：{e}")
                    time.sleep(interval)

    def _find_text(self, img_bgr):
        """回傳相對於監控區域左上角的 (x, y)，找不到回傳 None"""
        target = self.target_text_var.get().strip()
        exact = self.exact_match_var.get()
        lang = self.ocr_lang_var.get().strip() or "eng"

        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        # 適度放大以提升小字辨識率
        scale = 2
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

        try:
            data = pytesseract.image_to_data(
                gray, lang=lang, output_type=pytesseract.Output.DICT
            )
        except Exception as e:
            self.log(f"OCR 失敗：{e}")
            return None

        n = len(data["text"])
        for i in range(n):
            word = data["text"][i].strip()
            if not word:
                continue
            match = (word == target) if exact else (target in word)
            if match:
                x, y, w, h = (
                    data["left"][i], data["top"][i],
                    data["width"][i], data["height"][i]
                )
                cx = (x + w / 2) / scale
                cy = (y + h / 2) / scale
                return (int(cx), int(cy))
        return None

    def _find_image(self, img_bgr):
        template = cv2.imread(self.template_path, cv2.IMREAD_COLOR)
        if template is None:
            self.log("無法讀取範本圖片")
            return None

        th, tw = template.shape[:2]
        result = cv2.matchTemplate(img_bgr, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        threshold = self.threshold_var.get()
        if max_val >= threshold:
            cx = max_loc[0] + tw / 2
            cy = max_loc[1] + th / 2
            return (int(cx), int(cy))
        return None


def main():
    root = tk.Tk()
    app = WatcherApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
