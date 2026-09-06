"""كتل إدخال قابلة لإعادة الاستعمال في شاشات hr — "صاحب العمل" و"الأجير".

كل كتلة LabelFrame تبني حقولها من مواصفة (constants.EMPLOYER_FIELDS /
EMPLOYEE_FIELDS) وتوفّر get_data / set_data / set_state موحّدة، حتى تدخل
البيانات مرّة واحدة وتُعاد في الوثائق الأربع (لمّا يصل موديل كل وثيقة).
"""
import tkinter as tk
from tkinter import ttk

from ui.common.widgets import MaskedDateEntry
from ui.hr.constants import EMPLOYER_FIELDS, EMPLOYEE_FIELDS


class _FieldGroup(ttk.LabelFrame):
    """مجموعة حقول عامة مبنية من مواصفة [(key, label, kind, width), …].

    kind: "text" → ttk.Entry ·  "date" → MaskedDateEntry
    on_change (اختياري): تُنادى بلا وسائط عند أي تعديل بأي حقل نصّي —
    تستعملها الشاشة لتحديث العنوان الكبير حياً.
    """

    def __init__(self, parent, title, spec, on_change=None):
        super().__init__(parent, text=title, padding=10)
        self._spec = spec
        self._on_change = on_change
        self._widgets = {}
        self._vars = {}

        self.columnconfigure(1, weight=1)
        for row, (key, label, kind, width) in enumerate(spec):
            ttk.Label(self, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=2)
            if kind == "date":
                w = MaskedDateEntry(self, default_today=False)
                w.grid(row=row, column=1, sticky="w", pady=2)
                self._widgets[key] = w
            else:
                var = tk.StringVar()
                if self._on_change is not None:
                    var.trace_add("write", lambda *_a: self._on_change())
                ent = ttk.Entry(self, textvariable=var, width=width)
                ent.grid(row=row, column=1, sticky="w", pady=2)
                self._widgets[key] = ent
                self._vars[key] = var

    # ---------- واجهة موحّدة ----------
    def get_data(self):
        out = {}
        for key, _label, kind, _w in self._spec:
            if kind == "date":
                w = self._widgets[key]
                try:
                    out[key] = w.get_date().isoformat()
                except (ValueError, AttributeError):
                    out[key] = w.var.get().strip()
            else:
                out[key] = self._vars[key].get().strip()
        return out

    def set_data(self, data):
        data = data or {}
        for key, _label, kind, _w in self._spec:
            if kind == "date":
                raw = (data.get(key) or "").strip()
                w = self._widgets[key]
                try:
                    from datetime import date
                    w.set_date(date.fromisoformat(raw) if raw else None)
                except (ValueError, AttributeError):
                    pass
            else:
                self._vars[key].set(data.get(key, "") or "")

    def clear(self):
        self.set_data({})

    def is_empty(self):
        return not any(v for v in self.get_data().values())

    def set_state(self, state):
        """'normal' / 'readonly' / 'disabled' — لقفل الاستمارة لاحقاً."""
        for key, _label, kind, _w in self._spec:
            w = self._widgets[key]
            try:
                if kind == "date":
                    w.entry.configure(state=state)
                else:
                    w.configure(state=state)
            except tk.TclError:
                pass


class EmployerBlock(_FieldGroup):
    def __init__(self, parent, on_change=None):
        super().__init__(parent, "صاحب العمل / Employeur", EMPLOYER_FIELDS, on_change)


class EmployeeBlock(_FieldGroup):
    def __init__(self, parent, on_change=None):
        super().__init__(parent, "الأجير / Employé", EMPLOYEE_FIELDS, on_change)
