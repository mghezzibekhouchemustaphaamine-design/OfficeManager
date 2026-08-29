"""
خدمة Dossier: إصدار الشهادات (Attestation de travail / Fiche de paie /
Titre de congé).

كل التنقل يصير داخل نفس النافذة (بدون نوافذ منبثقة) عن طريق تبديل محتوى
إطار واحد (self.body) بين "الشاشات".

الخطوة الحالية: واجهة اختيار فقط. منطق تعبئة البيانات والتوليد الفعلي
يُبنى في خطوة لاحقة.
"""
import tkinter as tk
from tkinter import ttk

from ui.common import alerts

SERVICE_TYPES = [
    "Attestation de travail",
    "Fiche de paie",
    "Titre de congé",
]


class DossierTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=20)
        self.app = app
        self.check_vars = {}

        self.body = ttk.Frame(self)
        self.body.pack(fill="both", expand=True)

        self.show_service_selection()

    def clear_body(self):
        for widget in self.body.winfo_children():
            widget.destroy()

    # ---------- الشاشة 1: اختيار نوع/أنواع الشهادة ----------
    def show_service_selection(self):
        self.clear_body()
        self.check_vars = {}

        ttk.Label(
            self.body, text="اختر نوع أو أنواع الشهادة المطلوب إصدارها:",
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w", pady=(10, 15))

        for service in SERVICE_TYPES:
            var = tk.BooleanVar(value=False)
            self.check_vars[service] = var
            ttk.Checkbutton(self.body, text=service, variable=var).pack(anchor="w", padx=15, pady=6)

        btns = ttk.Frame(self.body)
        btns.pack(fill="x", pady=(25, 0))
        ttk.Button(btns, text="← رجوع", command=self.app.show_home).pack(side="left")
        ttk.Button(btns, text="التالي  ←", command=self.go_next).pack(side="right")

    def go_next(self):
        selected = [name for name, var in self.check_vars.items() if var.get()]
        if not selected:
            alerts.warning("تنبيه", "اختر نوعاً واحداً على الأقل قبل المتابعة")
            return
        self.show_confirmation(selected)

    # ---------- الشاشة 2: تأكيد مؤقت (سيُستبدل بنموذج تعبئة البيانات) ----------
    def show_confirmation(self, selected):
        self.clear_body()

        ttk.Label(self.body, text="تم اختيار:", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(10, 10))
        for name in selected:
            ttk.Label(self.body, text=f"• {name}").pack(anchor="w", padx=15)

        ttk.Label(
            self.body,
            text="\nالخطوة الجاية: تعبئة بيانات الشركة والموظف لكل نوع مختار.",
            font=("Segoe UI", 10),
            foreground="#555",
        ).pack(anchor="w", pady=(15, 0))

        ttk.Button(self.body, text="← رجوع", command=self.show_service_selection).pack(anchor="w", pady=(25, 0))

    def refresh(self):
        pass
