"""
عرض تجريبي مستقل تماماً (Tkinter، نفس تقنية البرنامج الأساسي) لشكل شاشة
خدمة CAPA الجديدة — واجهة بس، بلا أي ربط بـmain.py أو app_window.py أو
قاعدة البيانات أو الشريط الجانبي أو CD. الهدف: نصمم شكل الصفحة ونتفق
عليه، وبعدها ننقلها كتبويب خدمة رسمي بنفس نمط ui/cd (راجع ui/cd/tab.py).

المصدر: من ملف "Model Pour CAPA filigrane vierge repere.pdf" (كشف حساب
بريدي CCP) أخذنا فقط شكل الجدول وأعمدته كما هي — DATE DES OPERATIONS /
DESIGNATION / CREDIT / DEBIT / TAXES / AVOIR DU COMPTE. تعمّدنا استبعاد
كل شي ثاني من ذاك الملف (ترويسة "ALGERIE POSTE"، العلامة المائية
"ORIGINAL"، كلمة "RECONSTRUCT") — هاي شاشة عمل داخلية تخصّنا، مالها أي
علاقة بمؤسسة البريد.

التشغيل:
    python capa_screen_demo.py
"""
import tkinter as tk
from tkinter import ttk

EMPTY_BG_COLOR = "#fff3cd"  # نفس لون خانة فاضية بـCD — يلفت الانتباه للحقل الناقص
FILLED_BG_COLOR = "white"   # يندمج مع خلفية الورقة بعد التعبئة
HOVER_ON_COLOR = "#4a90d9"
BORDER_COLOR = "#9aa5b1"
HEADER_BG = "#e9edf2"

PAGE_BG = "#dfe3e8"   # خلفية النافذة حوالين الورقة
SHEET_BG = "white"    # لون الورقة A4 نفسها
SHEET_W = 800         # عرض الورقة بالبكسل (تقريب مريح على الشاشة)
SHEET_H = 1131        # نسبة A4 (210 × 297) على نفس العرض

# كل عمود: (العنوان، عرضه التقريبي بالبكسل)
COLUMNS = [
    ("DATE", 90),
    ("DESIGNATION", 260),
    ("CREDIT", 110),
    ("DEBIT", 110),
    ("TAXES", 90),
    ("AVOIR DU COMPTE", 140),
]

INITIAL_ROWS = 14


class CapaDemo(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CAPA — عرض تجريبي (مستقل)")
        self.configure(bg=PAGE_BG)
        self.geometry("900x760")

        self._entries = []  # كل عنصر: list[Entry] بترتيب COLUMNS لهذا السطر

        self._build_top_bar()
        self._build_scrollable_sheet()
        self._build_bottom_bar()

        self.after(50, self._focus_first_empty)

    # ---------------------------------------------------------------- UI

    def _build_top_bar(self):
        bar = tk.Frame(self, bg="#1d4ed8", height=48)
        bar.pack(side="top", fill="x")
        bar.pack_propagate(False)
        tk.Label(
            bar, text="CAPA", font=("Segoe UI", 14, "bold"),
            bg="#1d4ed8", fg="white",
        ).pack(side="left", padx=16)
        tk.Label(
            bar, text="(عرض تجريبي مستقل — شكل الجدول فقط)",
            font=("Segoe UI", 9), bg="#1d4ed8", fg="#dbeafe",
        ).pack(side="left")

    def _build_bottom_bar(self):
        bar = tk.Frame(self, bg=PAGE_BG, height=44)
        bar.pack(side="bottom", fill="x")
        ttk.Button(bar, text="+ إضافة سطر", command=self._add_row).pack(side="left", padx=8, pady=6)
        ttk.Button(bar, text="🗑 حذف آخر سطر", command=self._remove_last_row).pack(side="left", padx=0, pady=6)
        ttk.Button(bar, text="💾 حفظ (تجريبي — بلا وظيفة فعلية بعد)", state="disabled").pack(side="right", padx=8, pady=6)

    def _build_scrollable_sheet(self):
        outer = tk.Frame(self, bg=PAGE_BG)
        outer.pack(side="top", fill="both", expand=True)

        self._canvas = tk.Canvas(outer, bg=PAGE_BG, highlightthickness=0)
        vbar = ttk.Scrollbar(outer, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=vbar.set)
        vbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        # الورقة البيضاء (A4) نفسها، متمركزة داخل الـCanvas.
        self._sheet = tk.Frame(self._canvas, bg=SHEET_BG, width=SHEET_W, height=SHEET_H,
                                highlightbackground=BORDER_COLOR, highlightthickness=1)
        self._sheet_window = self._canvas.create_window(0, 0, window=self._sheet, anchor="n")
        self._sheet.pack_propagate(False)

        self._table = tk.Frame(self._sheet, bg=SHEET_BG)
        self._table.pack(side="top", fill="x", padx=24, pady=32)

        self._build_header_row()
        for _ in range(INITIAL_ROWS):
            self._add_row()

        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._sheet.bind("<Configure>", self._on_sheet_configure)
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _build_header_row(self):
        for col_idx, (title, width_px) in enumerate(COLUMNS):
            cell = tk.Label(
                self._table, text=title, font=("Segoe UI", 9, "bold"),
                bg=HEADER_BG, fg="#1e293b", anchor="center",
                width=1, height=2, wraplength=width_px - 10,
                highlightbackground=BORDER_COLOR, highlightthickness=1,
            )
            cell.grid(row=0, column=col_idx, sticky="nsew")
            self._table.grid_columnconfigure(col_idx, minsize=width_px)

    # ------------------------------------------------------------- rows

    def _add_row(self):
        row_idx = len(self._entries) + 1  # +1 لأن الصف 0 هو الترويسة
        row_entries = []
        for col_idx, (_title, width_px) in enumerate(COLUMNS):
            var = tk.StringVar()
            entry = tk.Entry(
                self._table, textvariable=var, font=("Segoe UI", 10),
                bg=EMPTY_BG_COLOR, relief="flat",
                highlightbackground=BORDER_COLOR, highlightthickness=1,
                justify="center" if col_idx != 1 else "right",
            )
            entry.grid(row=row_idx, column=col_idx, sticky="nsew", ipady=4)
            var.trace_add("write", lambda *_, e=entry, v=var: self._on_cell_changed(e, v))
            entry.bind("<FocusIn>", lambda ev, e=entry: e.configure(highlightbackground=HOVER_ON_COLOR))
            entry.bind("<FocusOut>", lambda ev, e=entry: e.configure(highlightbackground=BORDER_COLOR))
            row_entries.append(entry)
        self._entries.append(row_entries)
        self._table.after_idle(self._sync_scrollregion)

    def _remove_last_row(self):
        if not self._entries:
            return
        row_entries = self._entries.pop()
        for entry in row_entries:
            entry.destroy()
        self._table.after_idle(self._sync_scrollregion)

    def _on_cell_changed(self, entry, var):
        entry.configure(bg=FILLED_BG_COLOR if var.get().strip() else EMPTY_BG_COLOR)

    def _focus_first_empty(self):
        if self._entries and self._entries[0]:
            self._entries[0][0].focus_set()

    # --------------------------------------------------------- scrolling

    def _on_canvas_configure(self, event):
        x = max(0, (event.width - SHEET_W) // 2)
        self._canvas.coords(self._sheet_window, x, 16)
        self._sync_scrollregion()

    def _on_sheet_configure(self, _event):
        self._sync_scrollregion()

    def _sync_scrollregion(self):
        self._sheet.update_idletasks()
        h = self._sheet.winfo_reqheight()
        self._sheet.configure(height=max(SHEET_H, h))
        self._canvas.configure(scrollregion=(0, 0, self._canvas.winfo_width(), h + 32))

    def _on_mousewheel(self, event):
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


if __name__ == "__main__":
    CapaDemo().mainloop()
