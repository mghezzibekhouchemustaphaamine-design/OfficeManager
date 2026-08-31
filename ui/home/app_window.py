"""النافذة الرئيسية لـ OfficeManager.

هذه الطبقة مسؤولة عن إطار التطبيق والتنقل فقط. تفاصيل الخدمات تبقى داخل
وحداتها، والخدمات المعروضة تُعرّف في ui.home.services حتى نتمكن من إضافة
خدمات مستقبلية بدون إعادة بناء النافذة الرئيسية.
"""
import tkinter as tk
from tkinter import ttk

import programme.auth as auth
from ui.backup_tab import BackupTab
from ui.cd.tab import CDTab
from ui.common.alerts import confirm as _confirm
from ui.home.services import build_services


class OfficeApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("OfficeManager")
        self.geometry("1180x740")
        self.minsize(800, 560)

        self._current_service = None
        self._current_focus_widget = None
        self._deactivated_focus_widget = None

        self._configure_style()
        self._build_shell()

        self.bind_all("<FocusIn>", self._on_any_focus_in, add="+")
        self.bind("<Deactivate>", self._on_window_deactivate)
        self.protocol("WM_DELETE_WINDOW", self._on_close_request)

        self.show_home()

    def _configure_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("TButton", padding=7, font=("Segoe UI", 10))
        style.configure("TLabel", font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"))
        style.configure("Subtitle.TLabel", font=("Segoe UI", 10))
        style.configure("CardTitle.TLabel", font=("Segoe UI", 13, "bold"))
        style.configure("Status.TLabel", font=("Segoe UI", 9))

    def _build_shell(self):
        self.header = ttk.Frame(self, padding=(18, 12))
        self.header.pack(fill="x", side="top")

        self.brand = ttk.Label(self.header, text="OfficeManager", style="Title.TLabel")
        self.brand.pack(side="left")

        self.header_actions = ttk.Frame(self.header)
        self.header_actions.pack(side="right")

        self.home_button = ttk.Button(
            self.header_actions, text="⌂ الرئيسية", command=self.show_home
        )
        self.home_button.pack(side="left", padx=(0, 8))

        self.backup_button = ttk.Button(
            self.header_actions, text="🗄️ النسخ الاحتياطي", command=self.open_backup
        )
        self.backup_button.pack(side="left")

        ttk.Separator(self, orient="horizontal").pack(fill="x")

        self.body = ttk.Frame(self, padding=24)
        self.body.pack(fill="both", expand=True)

        ttk.Separator(self, orient="horizontal").pack(fill="x", side="bottom")
        self.status_var = tk.StringVar(value="جاهز")
        self.status = ttk.Label(
            self, textvariable=self.status_var, style="Status.TLabel", padding=(18, 6)
        )
        self.status.pack(fill="x", side="bottom")

    def _on_any_focus_in(self, event):
        self._current_focus_widget = event.widget

    def _on_window_deactivate(self, _event):
        self._deactivated_focus_widget = getattr(self, "_current_focus_widget", None)

    def _set_status(self, text):
        self.status_var.set(text)

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
        auth.record_logout_current()
        self.destroy()

    def show_home(self):
        self.clear_body()
        self._current_service = None
        self._set_status("الرئيسية — اختر الخدمة التي تريد العمل عليها")

        container = ttk.Frame(self.body)
        container.pack(fill="both", expand=True)

        ttk.Label(container, text="الخدمات", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            container,
            text="اختر خدمة لبدء العمل. يمكن إضافة خدمات جديدة لاحقًا دون تغيير نواة البرنامج.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(4, 22))

        cards = ttk.Frame(container)
        cards.pack(anchor="nw", fill="x")

        for service in build_services(self):
            if not service.enabled:
                continue
            card = ttk.LabelFrame(cards, text="", padding=18)
            card.pack(side="left", fill="both", expand=False, padx=(0, 14), ipadx=10, ipady=8)

            title = f"{service.icon}  {service.title}" if service.icon else service.title
            ttk.Label(card, text=title, style="CardTitle.TLabel").pack(anchor="w")
            ttk.Label(card, text=service.description, wraplength=250).pack(
                anchor="w", pady=(8, 16)
            )
            ttk.Button(card, text="فتح", command=lambda s=service: s.open_handler(self)).pack(
                anchor="w"
            )

    def open_cd(self):
        self.clear_body()
        self._current_service = "cd"
        self._set_status("CD — العمل على مستندات Change Devise")
        CDTab(self.body, self).pack(fill="both", expand=True)

    def open_backup(self):
        self.clear_body()
        self._current_service = "backup"
        self._set_status("النسخ الاحتياطي — حماية بيانات OfficeManager")
        BackupTab(self.body, self).pack(fill="both", expand=True)
