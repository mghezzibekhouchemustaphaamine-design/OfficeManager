"""
النافذة الرئيسية للبرنامج (OfficeApp) — الإطار العام (حجم النافذة، تتبّع
التركيز، تأكيد الإغلاق) + شريط علوي ثابت لكل البرنامج (يبقى ظاهر بكل
الشاشات، فوق أي شاشة خدمة مفتوحة — راجع _build_global_topbar) + الشاشة
الرئيسية (قائمة الخدمات: Dossier، CD) اللي تفتح بيها البرنامج أول شي،
والتنقّل بينها وبين باقي الشاشات.

النسخ الاحتياطي تحديداً مو "خدمة" زي Dossier/CD (مو مرتبط بمعاملة/عميل
معيّن، مصلحة البرنامج كله) — لهذا بالشريط العلوي الثابت، مو ضمن قائمة
الخدمات بالرئيسية زي باقي الأزرار.

منفصلة عن main.py (نقطة التشغيل الفعلية، تبقى بجذر المشروع) — main.py
يستدعي OfficeApp من هنا بس، بلا أي تفاصيل بناء واجهة بداخله."""
import tkinter as tk
from tkinter import ttk

from ui.dossier_tab import DossierTab
from ui.cd.tab import CDTab
from ui.common.alerts import confirm as _confirm
from ui.backup_tab import BackupTab


class OfficeApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("نظام إدارة الأعمال المكتبية")
        # 900px كانت كافية سابقاً، لكن شريط أدوات CD كبر تدريجياً (تراجع/
        # إعادة، تنقّل الجلسة، PDF، الاختصارات، الشريط الجانبي...) لحد ما
        # صار يحتاج ~1056px بالعرض على الأقل — أقل من هذا كانت الأزرار
        # اليمينية تتراكب/تختفي بصمت (بلا أي خطأ ظاهر) عند فتح البرنامج
        # لأول مرة. 1180 يعطي هامش أمان مريح فوق هذا الحد.
        #
        # الارتفاع 700 كان كافياً لحد ما أضفنا الشريط العلوي الثابت
        # (_build_global_topbar) — الحيز الرأسي الإضافي اللي أخذه قلّص
        # مساحة ورقة CD القابلة للعرض بما يكفي لدفع آخر حقل بالنموذج
        # (Net a créditer) تحت حافة العرض المرئي الأول (بلا أي خطأ ظاهر،
        # بس ما تشوفه إلا بعد ما تمرّر الشاشة يدوياً). 740 يعيد كل الحقول
        # للظهور الكامل مع هامش أمان بسيط فوق الحد الأدنى المقاس (720).
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

        # لما نافذة البرنامج تفقد التركيز على مستوى النظام (Alt+Tab
        # لبرنامج آخر)، نلتقط الخانة اللي فيها التركيز فعلياً وقتها —
        # تُستخدم بواجهات الحقول (ui/common/widgets.py:
        # is_window_reactivation_focus) للتفريق بين رجوع النافذة نفسها
        # للواجهة (ما نلمس فيه شي) وبين تنقّل حقيقي بين الخانات (يحدّد
        # كل المكتوب زي المطلوب). بدون هالتفريق، أي رجوع من برنامج آخر
        # كان يحدّد كل الكتابة الجارية ويجبر إعادتها من جديد بدل إكمالها
        # من مكانها.
        #
        # نتتبّع "آخر خانة فيها تركيز" باستمرار عبر bind_all (يشتغل مع
        # أي خانة بكل التطبيق، حتى لو ما عندها أي ربط خاص منا — أزرار،
        # خانات بتبويب ثاني...) بدل الاعتماد على focus_get() لحظة حدث
        # Deactivate نفسه (توقيته غير مضمون، ممكن يرجع فاضي وقتها).
        self.bind_all("<FocusIn>", self._on_any_focus_in, add="+")
        self.bind("<Deactivate>", self._on_window_deactivate)

        # إغلاق النافذة (زر X) وفيه بيانات CD مكتوبة ما اتحفظت بمستند —
        # نأكد قبل ما نضيّعها، بدل إغلاق صامت (المسودة المحفوظة تلقائياً
        # تحمي من هذا أصلاً، بس التأكيد الصريح خط دفاع إضافي مباشر).
        self.protocol("WM_DELETE_WINDOW", self._on_close_request)

        self.show_home()

    # ---------- شريط علوي ثابت لكل البرنامج (فوق self.body، يبقى ظاهر
    # بكل الشاشات — الرئيسية وأي خدمة مفتوحة) ----------
    def _build_global_topbar(self):
        # padding رأسي أقل ما يمكن (بدل الافتراضي الأكبر) — كل بكسل رأسي
        # هنا يقتطع من مساحة الورقة بشاشة CD (canvas قابل للتمرير، بس
        # كل بكسل إضافي يدفع الحقول السفلية أبعد عن حدود العرض الأول).
        bar = ttk.Frame(self, padding=(10, 2))
        bar.pack(fill="x", side="top")
        ttk.Button(bar, text="🗄️ النسخ الاحتياطي", command=self.open_backup).pack(side="right")
        ttk.Separator(self, orient="horizontal").pack(fill="x")

    def _on_any_focus_in(self, event):
        self._current_focus_widget = event.widget

    def _on_window_deactivate(self, _event):
        self._deactivated_focus_widget = getattr(self, "_current_focus_widget", None)

    def clear_body(self):
        # نفس خلل _on_close_request بالضبط (راجع شرحه هناك)، بس هذا
        # يغطّي أي تنقّل بعيد عن CD (رجوع، فتح خدمة ثانية...) — كل تنقّل
        # يهدم شاشة CD فوراً، فلو فيه حفظ مسودة مؤجَّل (Debounce 800ms)
        # لسا ما نُفّذ وقت التنقّل، يضيع بصمت. لازم نفرّغه هون قبل الهدم.
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
            # لازم قبل أي شي ثاني — لو فيه حفظ مسودة مؤجَّل (Debounce
            # 800ms) لسا ما نُفّذ، إغلاق النافذة يدمّرها قبل ما يوصل
            # يشتغل، فآخر تعديل يضيع بصمت (راجع الشرح المفصّل بـ
            # flush_draft_save بـui/cd/tab.py).
            cd.flush_draft_save()
        if cd is not None and cd.has_unsaved_changes():
            leave = _confirm(
                "تنبيه",
                "فيه بيانات مكتوبة بشاشة CD ما اتحفظت بمستند بعد.\nتريد تغلق البرنامج بدون إنشاء المستند؟",
            )
            if not leave:
                return
        self.destroy()

    # ---------- الشاشة الرئيسية: قائمة الخدمات ----------
    def show_home(self):
        self.clear_body()
        container = ttk.Frame(self.body)
        container.place(relx=0.5, rely=0.4, anchor="center")

        ttk.Label(container, text="الخدمات", font=("Segoe UI", 18, "bold")).pack(pady=(0, 20))

        buttons_row = ttk.Frame(container)
        buttons_row.pack()

        ttk.Button(buttons_row, text="📁 Dossier", command=self.open_dossier).pack(
            side="left", padx=10, ipadx=20, ipady=8
        )
        ttk.Button(buttons_row, text="CD", command=self.open_cd).pack(
            side="left", padx=10, ipadx=20, ipady=8
        )

    def open_dossier(self):
        self.clear_body()
        DossierTab(self.body, self).pack(fill="both", expand=True)

    def open_cd(self):
        self.clear_body()
        CDTab(self.body, self).pack(fill="both", expand=True)

    def open_backup(self):
        self.clear_body()
        BackupTab(self.body, self).pack(fill="both", expand=True)
