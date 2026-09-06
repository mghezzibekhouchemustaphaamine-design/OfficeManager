"""معاينة ورقة A4 حيّة — لوحة بيضاء بنسبة 210×297 تتوسّط منطقة العرض،
مع تكبير/تصغير وسكرول عمودي/أفقي.

الأرضية فقط: ترسم الورقة وهامش الطباعة ثم تسلّم الرسم لدالة "رسّام"
تحقنها الشاشة (set_painter). لمّا تصل موديلات الوثائق تصير هذي الدالة
ترسم نص المستند الحقيقي بمكانه؛ حالياً ترسم ختم "بانتظار الموديل".
"""
import tkinter as tk
from tkinter import ttk

from ui.hr.constants import (
    A4_RATIO, PREVIEW_BASE_W, PREVIEW_MARGIN, PAGE_MARGIN_MM, A4_W_MM,
    ZOOM_MIN, ZOOM_MAX, ZOOM_STEP, ZOOM_DEFAULT,
)


class A4Preview(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self._zoom = ZOOM_DEFAULT
        self._painter = None  # دالة(canvas, page_box, scale) — تحقنها الشاشة

        bar = ttk.Frame(self)
        bar.pack(fill="x", side="top")
        ttk.Label(bar, text="معاينة A4", style="Subtitle.TLabel").pack(side="left", padx=(2, 8))
        ttk.Button(bar, text="－", width=3, command=lambda: self._bump_zoom(-ZOOM_STEP)).pack(side="left")
        self._zoom_lbl = ttk.Label(bar, text="100%", width=6, anchor="center")
        self._zoom_lbl.pack(side="left")
        ttk.Button(bar, text="＋", width=3, command=lambda: self._bump_zoom(ZOOM_STEP)).pack(side="left")
        ttk.Button(bar, text="ملاءمة", command=self.fit_to_window).pack(side="left", padx=(8, 0))

        wrap = ttk.Frame(self)
        wrap.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(wrap, background="#9aa0a6", highlightthickness=0)
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.canvas.yview)
        hsb = ttk.Scrollbar(wrap, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)

        self.canvas.bind("<Configure>", lambda _e: self.redraw())
        # Ctrl + عجلة الفأرة = تكبير/تصغير (ويندوز/ماك: <MouseWheel>)
        self.canvas.bind("<Control-MouseWheel>", self._on_ctrl_wheel)
        # عجلة عادية = سكرول عمودي
        self.canvas.bind("<MouseWheel>", lambda e: self.canvas.yview_scroll(-1 if e.delta > 0 else 1, "units"))

    # ---------- واجهة عامة ----------
    def set_painter(self, fn):
        """fn(canvas, page_box, scale): page_box = (x0, y0, x1, y1) بإحداثيات
        اللوحة، scale = بكسل لكل مليمتر عند التكبير الحالي."""
        self._painter = fn
        self.redraw()

    def refresh(self):
        self.redraw()

    def fit_to_window(self):
        avail_h = max(self.canvas.winfo_height() - 2 * PREVIEW_MARGIN, 100)
        avail_w = max(self.canvas.winfo_width() - 2 * PREVIEW_MARGIN, 100)
        # اختر التكبير الذي يجعل الورقة تدخل كاملة في الاتجاهين
        by_w = avail_w / PREVIEW_BASE_W
        by_h = avail_h / (PREVIEW_BASE_W * A4_RATIO)
        self._set_zoom(min(by_w, by_h) * 100)

    # ---------- داخلي ----------
    def _bump_zoom(self, delta):
        self._set_zoom(self._zoom + delta)

    def _on_ctrl_wheel(self, event):
        self._bump_zoom(ZOOM_STEP if event.delta > 0 else -ZOOM_STEP)

    def _set_zoom(self, value):
        self._zoom = max(ZOOM_MIN, min(ZOOM_MAX, int(round(value))))
        self._zoom_lbl.configure(text=f"{self._zoom}%")
        self.redraw()

    def redraw(self):
        c = self.canvas
        c.delete("all")
        if not c.winfo_exists():
            return
        cw = max(c.winfo_width(), 1)
        ch = max(c.winfo_height(), 1)

        sheet_w = PREVIEW_BASE_W * self._zoom / 100.0
        sheet_h = sheet_w * A4_RATIO
        scale = sheet_w / A4_W_MM  # بكسل لكل مليمتر

        # توسيط الورقة؛ لو أكبر من منطقة العرض تبدأ من الهامش ويعمل السكرول
        x0 = max((cw - sheet_w) / 2, PREVIEW_MARGIN)
        y0 = max((ch - sheet_h) / 2, PREVIEW_MARGIN)
        x1, y1 = x0 + sheet_w, y0 + sheet_h

        c.create_rectangle(x0 + 3, y0 + 3, x1 + 3, y1 + 3, fill="#5f6368", outline="")  # ظل
        c.create_rectangle(x0, y0, x1, y1, fill="white", outline="#3c4043")

        m = PAGE_MARGIN_MM * scale
        c.create_rectangle(x0 + m, y0 + m, x1 - m, y1 - m, outline="#d0d0d0", dash=(3, 3))

        if self._painter is not None:
            try:
                self._painter(c, (x0, y0, x1, y1), scale)
            except Exception:
                # الرسّام تحت التطوير — خطؤه ما يوقف الشاشة كلها
                pass

        pad = PREVIEW_MARGIN
        c.configure(scrollregion=(0, 0, max(x1 + pad, cw), max(y1 + pad, ch)))
