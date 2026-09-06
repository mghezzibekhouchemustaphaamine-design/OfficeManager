"""الأرضية المشتركة لكل شاشات خدمات الموارد البشرية / الأجور.

HRDocScreen: نموذج إدخال (يسار، قابل للتمرير) + معاينة ورقة A4 حيّة
(يمين) + شريط أدوات. الوثائق الأربع ترثها وتغيّر فقط:
  SCREEN_KEY / SCREEN_TITLE / DOC_LABEL / OUTPUT_DIRNAME
  و build_doc_body() لحقول الوثيقة الخاصة (تُضاف مع الموديل).

محرّك الإخراج الحقيقي (قالب Word/Excel أو صورة نموذج) يُربط لاحقاً عبر
self._renderer — حتى ذلك الحين زرّا التوليد يشرحان أنّ الأرضية جاهزة
وبانتظار الموديل.
"""
import tkinter as tk
from tkinter import ttk, messagebox

from ui.common import alerts
from ui.common.client_picker import ClientPickerEntry
from ui.hr.a4_canvas import A4Preview
from ui.hr.blocks import EmployerBlock, EmployeeBlock
from ui.hr.render import TemplateNotReady
from ui.hr.constants import EMPLOYEE_NAME_KEYS


class HRDocScreen(ttk.Frame):
    # تُدهَس في كل شاشة
    SCREEN_KEY = "hr_base"
    SCREEN_TITLE = "وثيقة"
    DOC_LABEL = "Document"
    OUTPUT_DIRNAME = "RH"

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._renderer = None  # يُضبط لاحقاً (render.DocxTemplateRenderer / ImageOverlayRenderer)

        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        # --- العنوان الكبير (يعرض اسم الأجير الحقيقي، لا عنواناً عاماً) ---
        self._header_var = tk.StringVar(value=self.SCREEN_TITLE)
        header = ttk.Frame(self, padding=(14, 10, 14, 6))
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, textvariable=self._header_var, style="Title.TLabel").pack(side="left")
        ttk.Label(header, text=f"  ·  {self.DOC_LABEL}", style="Subtitle.TLabel").pack(side="left")

        # --- الجسم: نموذج (يسار) | معاينة (يمين) ---
        pane = ttk.Panedwindow(self, orient="horizontal")
        pane.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 8))

        form_wrap = self._scrollable(pane)
        form = form_wrap.inner
        pane.add(form_wrap, weight=1)

        self.preview = A4Preview(pane)
        pane.add(self.preview, weight=1)
        self.preview.set_painter(self._paint_preview)

        # --- وضع الزبون: مسجّل مقابل عابر ---
        mode_box = ttk.LabelFrame(form, text="الزبون", padding=10)
        mode_box.pack(fill="x", pady=(0, 8))
        self._mode_var = tk.StringVar(value="walkin")
        ttk.Radiobutton(
            mode_box, text="زبون مسجّل", value="registered",
            variable=self._mode_var, command=self._on_mode_change,
        ).grid(row=0, column=0, sticky="w", padx=(0, 12))
        ttk.Radiobutton(
            mode_box, text="زبون عابر", value="walkin",
            variable=self._mode_var, command=self._on_mode_change,
        ).grid(row=0, column=1, sticky="w")
        self._picker = ClientPickerEntry(mode_box, on_change=self._refresh_header)
        self._picker.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self._picker.grid_remove()  # يظهر فقط في وضع "زبون مسجّل"

        # --- كتل الإدخال المشتركة ---
        self.employer = EmployerBlock(form, on_change=self._refresh_header)
        self.employer.pack(fill="x", pady=(0, 8))
        self.employee = EmployeeBlock(form, on_change=self._refresh_header)
        self.employee.pack(fill="x", pady=(0, 8))

        # --- حقول الوثيقة الخاصة (تُضاف مع الموديل) ---
        self.doc_body = self.build_doc_body(form)
        if self.doc_body is not None:
            self.doc_body.pack(fill="x", pady=(0, 8))

        # --- شريط الأدوات ---
        bar = ttk.Frame(self, padding=(14, 0, 14, 10))
        bar.grid(row=2, column=0, sticky="ew")
        ttk.Button(bar, text="توليد Word", command=lambda: self._on_generate("docx")).pack(side="left")
        ttk.Button(bar, text="توليد PDF", command=lambda: self._on_generate("pdf")).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="السجلّ", command=self._on_history).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="مسح", command=self._on_clear).pack(side="left", padx=(6, 0))
        ttk.Label(
            bar, text="الأرضية جاهزة — توليد المستند يُفعَّل بعد ربط موديل هذه الوثيقة.",
            style="Subtitle.TLabel",
        ).pack(side="left", padx=(12, 0))

    # ---------- خطاطيف تدهسها الشاشات ----------
    def build_doc_body(self, parent):
        """حقول الوثيقة الخاصة. الأرضية: لوحة توضيحية فقط — تُستبدل
        بالحقول الفعلية عند وصول الموديل."""
        grp = ttk.LabelFrame(parent, text="بيانات الوثيقة", padding=10)
        ttk.Label(
            grp,
            text="الحقول الخاصة بهذه الوثيقة تُضاف مع موديلها.",
            style="Subtitle.TLabel", wraplength=340, justify="right",
        ).pack(anchor="w")
        return grp

    # ---------- المعاينة ----------
    def _paint_preview(self, canvas, page_box, scale):
        x0, y0, x1, _y1 = page_box
        cx = (x0 + x1) / 2
        canvas.create_text(
            cx, y0 + 30 * scale, text=self.DOC_LABEL, anchor="n",
            font=("Helvetica", max(int(6 * scale), 9), "bold"), fill="#202124",
        )
        canvas.create_text(
            cx, y0 + 120 * scale, text="الأرضية جاهزة\nبانتظار الموديل", anchor="center",
            font=("Helvetica", max(int(4 * scale), 8)), fill="#9aa0a6", justify="center",
        )

    # ---------- الأدوات ----------
    def collect_data(self):
        return {
            "screen_key": self.SCREEN_KEY,
            "doc_label": self.DOC_LABEL,
            "mode": self._mode_var.get(),
            "client_id": self._picker.get_client_id() if self._mode_var.get() == "registered" else None,
            "employer": self.employer.get_data(),
            "employee": self.employee.get_data(),
        }

    def _employee_name(self):
        emp = self.employee.get_data()
        parts = [emp.get(k, "").strip() for k in EMPLOYEE_NAME_KEYS]
        return " ".join(p for p in parts if p).strip()

    def _refresh_header(self, *_args):
        name = self._employee_name()
        self._header_var.set(name or self.SCREEN_TITLE)

    def _on_mode_change(self):
        if self._mode_var.get() == "registered":
            self._picker.grid()
        else:
            self._picker.grid_remove()
            self._picker.clear()
        self._refresh_header()

    def _on_generate(self, kind):
        if self._renderer is None:
            messagebox.showinfo(
                self.SCREEN_TITLE,
                "الأرضية جاهزة.\nتوليد المستند ("
                + ("Word" if kind == "docx" else "PDF")
                + ") يُفعَّل بعد ربط موديل هذه الوثيقة بالشاشة.",
                parent=self,
            )
            return
        try:
            # نقطة الدمج المستقبلية: بناء المسار، render، ثم log_hr_document
            raise TemplateNotReady("محرّك الإخراج غير مكتمل بعد.")
        except TemplateNotReady as exc:
            messagebox.showinfo(self.SCREEN_TITLE, str(exc), parent=self)

    def _on_history(self):
        messagebox.showinfo(
            self.SCREEN_TITLE,
            "سجلّ هذه الوثيقة يظهر هنا بعد إنشاء أول مستند.",
            parent=self,
        )

    def _on_clear(self):
        if not alerts.confirm("تأكيد", "مسح كل الحقول في هذه الشاشة؟"):
            return
        self.employer.clear()
        self.employee.clear()
        self._picker.clear()
        self._refresh_header()

    # ---------- توافق مع منطق النافذة الرئيسية (كلها اختيارية هناك) ----------
    def activate_shortcuts(self):
        pass

    def deactivate_shortcuts(self):
        pass

    def flush_draft_save(self):
        pass

    def has_unsaved_changes(self):
        return not (self.employer.is_empty() and self.employee.is_empty())

    # ---------- أداة داخلية: إطار قابل للتمرير ----------
    @staticmethod
    def _scrollable(parent):
        outer = ttk.Frame(parent)
        canvas = tk.Canvas(outer, highlightthickness=0)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        # عمداً بلا bind_all لعجلة الفأرة — حتى لا نصطدم بسكرول شاشات أخرى.
        outer.inner = inner
        return outer
