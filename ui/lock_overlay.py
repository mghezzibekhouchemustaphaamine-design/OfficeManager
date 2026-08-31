"""شاشة القفل — Toplevel يغطي كامل نافذة OfficeApp (نفس الحجم والموقع
تماماً، عبر app.winfo_geometry()) بلا أي جزء من المحتوى القديم يبان
حواليه. تظهر تلقائياً بعد فترة خمول (راجع OfficeApp._check_idle) أو
يدوياً بزر "🔒 قفل" بالهيدر (راجع OfficeApp._trigger_lock).

الفتح بالباسوورد بس — إعادة استخدام كامل لـauth.verify_login() (بلا أي
تعديل على programme/auth.py)؛ ماكو زر "تخطي" ولا أي طريقة ثانية للخروج
غير الباسوورد الصحيح أو إغلاق البرنامج بالكامل (X ينادي نفس
app._on_close_request العادية)."""
import tkinter as tk
from tkinter import ttk

import programme.auth as auth
from ui.common import alerts


class LockOverlay(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app

        self.title("🔒 مقفل")
        self.geometry(app.winfo_geometry())
        self.resizable(False, False)
        self.transient(app)
        # X بالعنوان ينادي نفس دالة إغلاق البرنامج العادية — الإغلاق
        # الكامل هو المخرج الوحيد غير الباسوورد الصحيح.
        self.protocol("WM_DELETE_WINDOW", app._on_close_request)

        container = ttk.Frame(self)
        container.pack(fill="both", expand=True)

        center = ttk.Frame(container)
        center.place(relx=0.5, rely=0.45, anchor="center")

        ttk.Label(center, text="🔒 البرنامج مقفل", font=("Segoe UI", 20, "bold")).pack(
            pady=(0, 24)
        )

        self.password_var = tk.StringVar()
        entry = ttk.Entry(
            center, textvariable=self.password_var, show="•", width=32,
            justify="center", font=("Segoe UI", 12),
        )
        entry.pack(pady=(0, 14))

        ttk.Button(center, text="🔓 فتح", command=self._try_unlock).pack()

        entry.focus_set()
        self.bind("<Return>", lambda _e: self._try_unlock())
        self.grab_set()

    def _try_unlock(self):
        password = self.password_var.get()
        if auth.verify_login(auth.get_current_username(), password):
            self.destroy()
        else:
            alerts.error("كلمة مرور غير صحيحة", "حاول مرة ثانية.", parent=self)
            self.password_var.set("")
