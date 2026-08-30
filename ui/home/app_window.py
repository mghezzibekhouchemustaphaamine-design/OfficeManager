"""
النافذة الرئيسية للبرنامج (OfficeApp) — الإطار العام + شريط النسخ الاحتياطي
+ الشاشة الرئيسية لخدمة CD.

OfficeManager حالياً يركّز على النواة الأساسية للبرنامج وخدمة CD.
الخدمات الأخرى ستُضاف لاحقاً واحدة واحدة.
"""
import tkinter as tk
from tkinter import ttk

from ui.cd.tab import CDTab
from ui.common.alerts import confirm as _confirm
from ui.backup_tab import BackupTab


class OfficeApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("نظام إدارة الأعمال المكتبية")
        self.geometry("1180x740")
        self.minsize(700, 500)

        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("TButton", padding=6, font=("Segoe UI", 10))
        style.configure("TLabel", font=("Segoe UI", 10))

        self._build_global_topbar()

        self.body = ttk.Frame(self, padding=20)
        self.body.pack(fill="both", expand=True)

        self.bind_all("<FocusIn>", self._on_any_focus_in, add="+")
        self.bind("<Deactivate>", self._on_window_deactivate)
        self.protocol("WM_DELETE_WINDOW", self._on_close_request)

        self.show_home()

    def _build_global_topbar(self):
        bar = ttk.Frame(self, padding=(10, 2))
        bar.pack(fill="x", side="top")
        ttk.Button(bar, text="🗄️ النسخ الاحتياطي", command=self.open_backup).pack(side="right")
        ttk.Separator(self, orient="horizontal").pack(fill="x")

    def _on_any_focus_in(self, event):
        self._current_focus_widget = event.widget

    def _on_window_deactivate(self, _event):
        self._deactivated_focus_widget = getattr(self, "_current_focus_widget", None)

    def clear_body(self):
        cd = self._current_cd_tab()
        if cd is not None:
            cd.flush_draft_save()
        for widget in self.body.winfo_children():
            widget.destroy()

    def _current_cd_tab(self):
        for widget in self.body.winfo_children():
            if isinstance(widget, CDTab):
                return widget
        return None

    def _on_close_request(self):
        cd = self._current_cd_tab()
        if cd is not None:
            cd.flush_draft_save()
        if cd is not None and cd.has_unsaved_changes():
            leave = _confirm(
                "تنبيه",
                "فيه بيانات مكتوبة بشاشة CD ما اتحفظت بمستند بعد.\nتريد تغلق البرنامج بدون إنشاء المستند؟",
            )
            if not leave:
                return
        self.destroy()

    def show_home(self):
        self.clear_body()
        container = ttk.Frame(self.body)
        container.place(relx=0.5, rely=0.4, anchor="center")

        ttk.Label(container, text="الخدمات", font=("Segoe UI", 18, "bold")).pack(pady=(0, 20))

        buttons_row = ttk.Frame(container)
        buttons_row.pack()

        ttk.Button(buttons_row, text="CD", command=self.open_cd).pack(
            side="left", padx=10, ipadx=20, ipady=8
        )

    def open_cd(self):
        self.clear_body()
        CDTab(self.body, self).pack(fill="both", expand=True)

    def open_backup(self):
        self.clear_body()
        BackupTab(self.body, self).pack(fill="both", expand=True)
