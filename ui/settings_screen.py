"""شاشة الإعدادات — 3 أقسام مستقلة:
1) الحساب: تغيير اسم المستخدم و/أو كلمة المرور (بتأكيد كلمة المرور
   الحالية أولاً — راجع programme.auth.update_account).
2) الأمان: مدة القفل التلقائي بالدقايق — تخزين بس بهذي المرحلة (راجع
   programme.settings)، بلا أي تفعيل فعلي (مرحلة قادمة).
3) النسخ الاحتياطي: زر وحيد يفتح BackupTab الموجودة نفسها — بلا أي
   تعديل عليها.

نفس نمط ui/backup_tab.py بالضبط (ttk.Frame، __init__(self, parent, app)،
زر "← رجوع" أعلى يودي لـapp.show_home)."""
import tkinter as tk
from tkinter import ttk

import programme.auth as auth
import programme.settings as settings
from ui.common import alerts


class SettingsScreen(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=10)
        self.app = app

        top_bar = ttk.Frame(self)
        top_bar.pack(fill="x", pady=(0, 12))
        ttk.Label(top_bar, text="⚙️ الإعدادات", font=("Segoe UI", 14, "bold")).pack(side="left")
        ttk.Button(top_bar, text="← رجوع", command=self.app.show_home).pack(side="right")

        self._build_account_section()
        self._build_security_section()
        self._build_backup_section()

    # ---------- 1) الحساب ----------
    def _build_account_section(self):
        section = ttk.LabelFrame(self, text="👤 الحساب", padding=12)
        section.pack(fill="x", pady=(0, 12))

        self.username_label = ttk.Label(section, text=self._username_label_text())
        self.username_label.pack(anchor="e", pady=(0, 10))

        self.new_username_var = tk.StringVar()
        self.new_password_var = tk.StringVar()
        self.confirm_password_var = tk.StringVar()
        self.current_password_var = tk.StringVar()

        grid = ttk.Frame(section)
        grid.pack(fill="x")
        grid.columnconfigure(0, weight=1)

        rows = (
            ("اسم مستخدم جديد (اختياري):", self.new_username_var, None),
            ("كلمة مرور جديدة (اختياري):", self.new_password_var, "•"),
            ("تأكيد كلمة المرور الجديدة:", self.confirm_password_var, "•"),
            ("كلمة المرور الحالية (إجباري):", self.current_password_var, "•"),
        )
        for i, (label_text, var, show) in enumerate(rows):
            ttk.Label(grid, text=label_text).grid(row=i, column=1, sticky="e", pady=4, padx=(8, 0))
            entry = ttk.Entry(grid, textvariable=var, width=30)
            if show:
                entry.configure(show=show)
            entry.grid(row=i, column=0, sticky="ew", pady=4)

        ttk.Button(section, text="💾 حفظ تغييرات الحساب", command=self._save_account).pack(
            anchor="w", pady=(10, 0)
        )

    def _username_label_text(self):
        return f"اسم المستخدم الحالي: {auth.get_current_username() or '—'}"

    def _save_account(self):
        current_password = self.current_password_var.get()
        if not current_password:
            alerts.error(
                "بيانات ناقصة", "لازم تكتب كلمة المرور الحالية لأي حفظ.", parent=self
            )
            return

        new_username = self.new_username_var.get().strip() or None
        new_password = self.new_password_var.get()
        confirm_password = self.confirm_password_var.get()

        if new_password or confirm_password:
            if new_password != confirm_password:
                alerts.error(
                    "عدم تطابق", "كلمة المرور الجديدة والتأكيد غير متطابقين.", parent=self
                )
                return
        new_password = new_password or None

        if not new_username and not new_password:
            alerts.info(
                "ما فيه تغيير", "ما كتبت اسم مستخدم جديد ولا كلمة مرور جديدة.", parent=self
            )
            return

        if not auth.update_account(
            current_password, new_username=new_username, new_password=new_password
        ):
            alerts.error(
                "كلمة المرور الحالية غير صحيحة", "ما تم أي تغيير.", parent=self
            )
            return

        alerts.info("تم الحفظ", "تحدّث الحساب بنجاح.", parent=self)
        self.current_password_var.set("")
        self.new_password_var.set("")
        self.confirm_password_var.set("")
        self.new_username_var.set("")
        self.username_label.configure(text=self._username_label_text())

    # ---------- 2) الأمان ----------
    def _build_security_section(self):
        section = ttk.LabelFrame(self, text="🔒 الأمان", padding=12)
        section.pack(fill="x", pady=(0, 12))

        ttk.Label(section, text="مدة القفل التلقائي بعد عدم النشاط (بالدقايق):").pack(
            anchor="e"
        )

        row = ttk.Frame(section)
        row.pack(fill="x", pady=(8, 0))
        self.auto_lock_var = tk.StringVar(value=str(settings.get_auto_lock_minutes()))
        ttk.Button(row, text="💾 حفظ", command=self._save_auto_lock).pack(side="right")
        ttk.Entry(row, textvariable=self.auto_lock_var, width=10, justify="center").pack(
            side="right", padx=(0, 8)
        )

        ttk.Label(
            section,
            text="ملاحظة: تخزين المدة بس بهذي المرحلة — التفعيل الفعلي للقفل التلقائي مرحلة قادمة.",
            foreground="#888", wraplength=600, justify="right",
        ).pack(anchor="e", pady=(8, 0))

    def _save_auto_lock(self):
        raw = self.auto_lock_var.get().strip()
        try:
            minutes = int(raw)
        except ValueError:
            alerts.error("قيمة غير صحيحة", "اكتب رقم صحيح بالدقايق.", parent=self)
            return
        if minutes < 5:
            alerts.error("قيمة صغيرة", "الحد الأدنى 5 دقايق.", parent=self)
            return
        settings.set_auto_lock_minutes(minutes)
        self.auto_lock_var.set(str(minutes))
        alerts.info("تم الحفظ", f"مدة القفل التلقائي: {minutes} دقيقة.", parent=self)

    # ---------- 3) النسخ الاحتياطي ----------
    def _build_backup_section(self):
        section = ttk.LabelFrame(self, text="🗄️ النسخ الاحتياطي", padding=12)
        section.pack(fill="x")
        ttk.Button(
            section, text="🗄️ فتح إعدادات النسخ الاحتياطي", command=self.app.open_backup
        ).pack(anchor="w")
