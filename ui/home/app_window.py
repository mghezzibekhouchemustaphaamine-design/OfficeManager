"""النافذة الرئيسية لـ OfficeManager.

هذه الطبقة مسؤولة عن إطار التطبيق والتنقل فقط. تفاصيل الخدمات تبقى داخل
وحداتها، والخدمات المعروضة تُعرّف في ui.home.services حتى نتمكن من إضافة
خدمات مستقبلية بدون إعادة بناء النافذة الرئيسية.

مفهومان منفصلان بمنطقة العرض (self.view_area):
- "شاشات بسيطة" (الرئيسية/الإعدادات/النسخ الاحتياطي): تُبنى وتُدمَّر بكل
  زيارة (راجع _show_transient_view) — بلا أي حالة تبقى بينها.
- "تبويبات خدمة حية" (CD حالياً بس، بـself._service_tabs): تُبنى مرة
  وحدة وتبقى بالذاكرة حتى لو المستخدم انتقل لشاشة ثانية — الرجوع لها
  عبر شريط التبويبات (self.tab_strip) يعرض نفس حالتها بالضبط، بلا أي
  إعادة تحميل. راجع open_cd/_activate_service_tab/_close_service_tab.
"""
import time
import tkinter as tk
from tkinter import ttk

import programme.auth as auth
import programme.settings as settings
from ui.backup_tab import BackupTab
from ui.cd.tab import CDTab
from ui.common.alerts import confirm as _confirm
from ui.home.services import build_services
from ui.lock_overlay import LockOverlay
from ui.settings_screen import SettingsScreen

# نفس نص تنبيه الشغل غير المحفوظ بكل مكان يُستعمل فيه (إغلاق البرنامج
# كامل، أو إغلاق تبويب CD وحده بـ×) — رسالة واحدة بمكان واحد بدل نسختين
# قد تنحرفان عن بعض لاحقاً.
_UNSAVED_CD_TITLE = "تنبيه"
_UNSAVED_CD_MESSAGE = (
    "فيه بيانات مكتوبة بشاشة CD ما اتحفظت بمستند بعد.\n"
    "تريد تغلق البرنامج بدون إنشاء المستند؟"
)

# نص/رمز زر كل تبويب خدمة حي بشريط التبويبات — "cd" هو المفتاح الوحيد
# الممكن حالياً (راجع self._service_tabs).
_SERVICE_TAB_LABELS = {"cd": "💱 CD"}

# نص شريط الحالة السفلي لكل تبويب خدمة حي — تُقرأ من _activate_service_tab
# بس (مصدر وحيد للحقيقة)، بغض النظر هل التفعيل جاء من open_cd() أو من
# ضغطة مباشرة على زر التبويب بالشريط.
_SERVICE_TAB_STATUS = {"cd": "CD — العمل على مستندات Change Devise"}


class OfficeApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("OfficeManager")
        self.geometry("1180x740")
        self.minsize(800, 560)

        self._current_service = None
        self._current_focus_widget = None
        self._deactivated_focus_widget = None
        self._is_locked = False
        self._last_activity_time = time.time()

        # تبويبات خدمة حية (راجع docstring الملف) + الشاشة البسيطة
        # المعروضة حالياً (لو فيه) — كلاهما فاضي قبل show_home() بالأسفل.
        self._service_tabs = {}
        self._transient_view = None
        # وين ترجع لما تسكّر الإعدادات (زر "رجوع" جواها، أو ضغطة ثانية
        # على "⚙️ الإعدادات" بالهيدر) — راجع open_settings/close_settings/
        # return_to_settings تحت. مفتاح تبويب خدمة حي (زي "cd") لو كنت
        # جواه، وإلا None (الرئيسية).
        self._settings_return_to = None

        self._configure_style()
        self._build_shell()

        self.bind_all("<FocusIn>", self._on_any_focus_in, add="+")
        self.bind("<Deactivate>", self._on_window_deactivate)
        # أي نشاط حقيقي (فأرة/كيبورد) يؤجّل القفل التلقائي — راجع
        # _check_idle. add="+" حتى ما نلغي أي ربط ثاني موجود على نفس
        # الحدث (زي <FocusIn> فوق).
        self.bind_all("<Motion>", self._on_activity, add="+")
        self.bind_all("<KeyPress>", self._on_activity, add="+")
        self.bind_all("<Button>", self._on_activity, add="+")
        self.protocol("WM_DELETE_WINDOW", self._on_close_request)

        self.show_home()
        # فحص دوري كل 5 ثواني — يعيد جدولة نفسه دايماً (راجع _check_idle).
        self.after(5000, self._check_idle)

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

        self.settings_button = ttk.Button(
            self.header_actions, text="⚙️ الإعدادات", command=self.open_settings
        )
        self.settings_button.pack(side="left", padx=(0, 8))

        self.lock_button = ttk.Button(
            self.header_actions, text="🔒 قفل", command=self._trigger_lock
        )
        self.lock_button.pack(side="left")

        ttk.Separator(self, orient="horizontal").pack(fill="x")

        self.body = ttk.Frame(self, padding=24)
        self.body.pack(fill="both", expand=True)

        # شريط تبويبات الخدمات الحية (CD الآن بس)، فوق منطقة العمل —
        # بلا pack أول الأمر (غير موجود بالتخطيط إطلاقاً) لحد ما يفتح
        # أول تبويب حي؛ راجع _refresh_tab_strip.
        self.tab_strip = ttk.Frame(self.body)

        # حجز مكان فاضي لشريط أدوات الخدمة المستقبلي — بلا أي محتوى
        # فعلي الآن، بس مكان محجوز بالهيكل تحت شريط التبويبات مباشرة.
        self.toolbar_seam = ttk.Frame(self.body)
        self.toolbar_seam.pack(fill="x", side="top")

        # منطقة العرض المشتركة: كل شاشة (بسيطة أو تبويب خدمة حي) توضع
        # هون بـgrid(row=0, column=0) وتُبان عبر tkraise() — الكل يشغل
        # نفس المساحة تماماً، فوق بعضه، والظاهر بس اللي بالأعلى.
        self.view_area = ttk.Frame(self.body)
        self.view_area.pack(fill="both", expand=True, side="top")
        self.view_area.rowconfigure(0, weight=1)
        self.view_area.columnconfigure(0, weight=1)

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

    def _on_activity(self, _event):
        self._last_activity_time = time.time()

    def _check_idle(self):
        if not self._is_locked:
            elapsed = time.time() - self._last_activity_time
            if elapsed >= settings.get_auto_lock_minutes() * 60:
                self._trigger_lock()
        # تعيد جدولة نفسها دايماً — سواء قفلت الآن أو لسا بانتظار الخمول.
        self.after(5000, self._check_idle)

    def _trigger_lock(self):
        if self._is_locked:
            return
        self._is_locked = True
        # قبل ما نفتح شاشة القفل: نحفظ مسودة كل تبويبات الخدمة الحية
        # ونعطّل اختصاراتها (نفس اللوپ بالضبط اللي بـ_show_transient_view)
        # — بدون هذا، اختصارات CD (bind_all على مستوى التطبيق كامل) تضل
        # تشتغل حتى وشاشة القفل ظاهرة فوقها (Ctrl+P يطبع، Ctrl+N يفتح
        # مستند جديد...)، لأن bindtag "all" موجود بكل الودجات بما فيها
        # ودجات LockOverlay نفسها.
        for tab in self._service_tabs.values():
            if hasattr(tab, "flush_draft_save"):
                tab.flush_draft_save()
            if hasattr(tab, "deactivate_shortcuts"):
                tab.deactivate_shortcuts()
        overlay = LockOverlay(self)
        self.wait_window(overlay)  # يعلّق هنا لحد ما LockOverlay تتدمر (فتح ناجح)
        self._is_locked = False
        self._last_activity_time = time.time()
        # نعيد التفعيل لتبويب الخدمة *النشط حالياً* بس (نفس فحص
        # _activate_service_tab) — ما نفعّل خدمات ثانية مو ظاهرة فعلياً.
        active_tab = self._service_tabs.get(self._current_service)
        if active_tab is not None and hasattr(active_tab, "activate_shortcuts"):
            active_tab.activate_shortcuts()

    def _set_status(self, text):
        self.status_var.set(text)

    # ---------- منطقة العرض: شاشات بسيطة مقابل تبويبات خدمة حية ----------
    def _destroy_transient_view(self):
        view = self._transient_view
        if view is not None and view.winfo_exists():
            view.destroy()
        self._transient_view = None

    def _show_transient_view(self, widget):
        """تعرض شاشة بسيطة (رئيسية/إعدادات/نسخ احتياطي) — تدمّر أي شاشة
        بسيطة سابقة (بلا أي تأثير على self._service_tabs، تبقى حية
        بالخلفية بكامل حالتها) وتحط الجديدة بـview_area."""
        self._destroy_transient_view()
        for tab in self._service_tabs.values():
            if hasattr(tab, "deactivate_shortcuts"):
                tab.deactivate_shortcuts()
        self._transient_view = widget
        widget.grid(row=0, column=0, sticky="nsew")
        widget.tkraise()

    def _activate_service_tab(self, key):
        tab = self._service_tabs.get(key)
        if tab is None:
            return
        self._destroy_transient_view()
        for other_key, other_tab in self._service_tabs.items():
            if other_key != key and hasattr(other_tab, "deactivate_shortcuts"):
                other_tab.deactivate_shortcuts()
        if hasattr(tab, "activate_shortcuts"):
            tab.activate_shortcuts()
        tab.tkraise()
        self._current_service = key
        self._set_status(_SERVICE_TAB_STATUS.get(key, key))

    def _refresh_tab_strip(self):
        for widget in self.tab_strip.winfo_children():
            widget.destroy()
        if not self._service_tabs:
            self.tab_strip.pack_forget()
            return
        for key in self._service_tabs:
            entry = ttk.Frame(self.tab_strip)
            entry.pack(side="left", padx=(0, 4), pady=4)
            ttk.Button(
                entry, text=_SERVICE_TAB_LABELS.get(key, key),
                command=lambda k=key: self._activate_service_tab(k),
            ).pack(side="left")
            ttk.Button(
                entry, text="×", width=2, command=lambda k=key: self._close_service_tab(k),
            ).pack(side="left")
        self.tab_strip.pack(fill="x", side="top", before=self.toolbar_seam)

    def _close_service_tab(self, key):
        tab = self._service_tabs.get(key)
        if tab is None:
            return
        if hasattr(tab, "flush_draft_save"):
            tab.flush_draft_save()
        if hasattr(tab, "has_unsaved_changes") and tab.has_unsaved_changes():
            if not _confirm(_UNSAVED_CD_TITLE, _UNSAVED_CD_MESSAGE):
                return
        was_current = self._current_service == key
        tab.destroy()
        del self._service_tabs[key]
        self._refresh_tab_strip()
        if was_current:
            self.show_home()

    def _on_close_request(self):
        for tab in self._service_tabs.values():
            if hasattr(tab, "flush_draft_save"):
                tab.flush_draft_save()
        for tab in self._service_tabs.values():
            if hasattr(tab, "has_unsaved_changes") and tab.has_unsaved_changes():
                if not _confirm(_UNSAVED_CD_TITLE, _UNSAVED_CD_MESSAGE):
                    return
        auth.record_logout_current()
        self.destroy()

    def show_home(self):
        self._current_service = None
        self._set_status("الرئيسية — اختر الخدمة التي تريد العمل عليها")

        container = ttk.Frame(self.view_area)

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
            # لو الخدمة مفتوحة أصلاً كتبويب حي (راجع self._service_tabs)،
            # النص يوضّح إنك راجع لشغل جاري، لا فاتح شي من الصفر.
            btn_text = "↩️ متابعة الشغل" if service.key in self._service_tabs else "فتح"
            ttk.Button(card, text=btn_text, command=lambda s=service: s.open_handler(self)).pack(
                anchor="w"
            )

        self._show_transient_view(container)

    def open_cd(self):
        if "cd" not in self._service_tabs:
            cd_tab = CDTab(self.view_area, self)
            cd_tab.grid(row=0, column=0, sticky="nsew")
            self._service_tabs["cd"] = cd_tab
            self._refresh_tab_strip()
        self._activate_service_tab("cd")

    def open_backup(self):
        self._current_service = "backup"
        self._set_status("النسخ الاحتياطي — حماية بيانات OfficeManager")
        self._show_transient_view(BackupTab(self.view_area, self))

    def _display_settings(self):
        self._current_service = "settings"
        self._set_status("الإعدادات — الحساب، الأمان، والنسخ الاحتياطي")
        self._show_transient_view(SettingsScreen(self.view_area, self))

    def open_settings(self):
        """زر "⚙️ الإعدادات" بالهيدر — تبديل (toggle): لو الإعدادات
        ظاهرة أصلاً، تسكّرها (ترجع لمكانك الأصلي عبر close_settings()).
        غير كذا، تحفظ وجهتك الحالية (تبويب خدمة حي لو كنت جواه، وإلا
        None = الرئيسية) قبل ما تعرضها."""
        if self._current_service == "settings":
            self.close_settings()
            return
        self._settings_return_to = (
            self._current_service if self._current_service in self._service_tabs else None
        )
        self._display_settings()

    def close_settings(self):
        """زر "رجوع" جوا شاشة الإعدادات — يرجعك لمكانك الأصلي المحفوظ
        بـopen_settings() (تبويب خدمة حي لو فيه، وإلا الرئيسية)."""
        target = self._settings_return_to
        self._settings_return_to = None
        if target is not None and target in self._service_tabs:
            self._activate_service_tab(target)
        else:
            self.show_home()

    def return_to_settings(self):
        """زر "رجوع" جوا شاشة النسخ الاحتياطي (تُفتح بس من جوا
        الإعدادات — راجع ui/backup_tab.py) — تعرض الإعدادات من جديد بلا
        أي لمس على self._settings_return_to، حتى الوجهة الأصلية تبقى
        محفوظة رغم المرور بالنسخ الاحتياطي بالنص."""
        self._display_settings()
