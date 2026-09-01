"""
خدمة CD (Change Devise): شاشة وحدة — تكتب البيانات مباشرة فوق صورة
النموذج الفاضي بمكانها الدقيق (زي الكتابة على الورقة الحقيقية)، وزر
واحد ينشئ المستند النهائي (Word) بنفس البيانات بالضبط.

الورقة تتوسّط دائماً بمنطقة العرض (أي حجم نافذة)، ومزوّدة بتكبير/تصغير
(زوم) وسكرول عمودي/أفقي، وتبويبات (زي كروم) — راجع _build_tab_strip
وما حولها للتفاصيل.

هذا الملف (CDTab نفسه) يركّز على: التبويبات، توليد/طباعة/تصدير المستند،
التراجع/الإعادة، المسودة وإعدادات المكتب. خانات الكتابة المخصّصة
(CDEntryFactoryMixin) وسجل المستندات (CDHistoryWindow) بملفين منفصلين
بنفس الحزمة (ui/cd/entries.py، ui/cd/history.py) — راجعهم لتفاصيلهم."""
import logging
import math
import os
import tkinter as tk
import tkinter.font as tkfont
from datetime import date

from tkinter import ttk, simpledialog, filedialog

from ui.common import alerts

import programme.backup as backup
from programme.database import (
    log_cd_document, update_cd_document, find_cd_document_by_path, deserialize_cd_data, get_client,
)
from programme.paths import get_travail_root, get_client_dir
from programme.case_ops import move_case
from ui.cd.constants import (
    _load_json, _save_json, _safe_float_or_none, _fmt_amount,
    CD_SETTINGS_PATH, CD_DRAFT_PATH, CD_UI_PREFS_PATH,
    OFFICE_FIELD_KEYS, DRAFT_FIELD_KEYS, _TRANSACTIONAL_DRAFT_KEYS,
    TARGET_W, CANVAS_MARGIN, BASE_FONT_SIZE, ENTRY_CHROME_PX,
    ZOOM_MIN, ZOOM_MAX, ZOOM_STEP, ZOOM_DEFAULT,
)
# نوافذ التأكيد صارت مشتركة لكل البرنامج — راجع ui/common/alerts.py.
# alias محلي (_confirm) حتى ما نغيّر كل نداء بالملف (5 استخدامات).
from ui.common.alerts import confirm as _confirm, confirm_always
from ui.cd.entries import CDEntryFactoryMixin
from ui.cd.document import (
    generate_cd_document,
    generate_cd_pdf,
    get_blank_background,
    field_layout_px,
    FIELD_LAYOUT,
    TAUX_MAX_VALUE,
    TAUX_DEC_DIGITS,
    OUTPUT_DIR,
    _named_path,
)
from ui.cd.history import CDHistoryWindow
from ui.common.widgets import MaskedDateEntry, MaskedTimeEntry, SplitDateEntry, _ALLOWED_TIME_WINDOWS
from ui.common.file_explorer import FileExplorerPanel
from ui.common.client_picker import ClientPickerEntry
from programme.utils import open_path
import random


def _norm_path(path):
    """تطبيع مسار للمقارنة — abspath + normcase (حماية فرق حالة
    الأحرف بويندوز عند مقارنة مسار ملف بمسار محفوظ بقاعدة البيانات)."""
    return os.path.normcase(os.path.abspath(path))


def _increment_dossier_no(no_str):
    """+1 لرقم البوردرو، بنفس عدد الخانات بالضبط (يحافظ على الأصفار
    الأولى — "00456" -> "00457") — إلا لو الرقم الجديد طفح عن نفس عدد
    الخانات (زي "99999" -> "100000")، عندها يطلع بدون حشو لأنه ما عاد
    يتّسع أصلاً. لرقم غير رقمي بالكامل (نادر، حالة استثنائية) يرجّعه
    كما هو بلا أي تغيير — أسلم من تخمين شكله."""
    if not no_str.isdigit():
        return no_str
    new_str = str(int(no_str) + 1)
    return new_str.zfill(len(no_str)) if len(new_str) <= len(no_str) else new_str


def _advance_time_for_next_client(time_str):
    """يرجّع وقت = time_str + عدد دقائق عشوائي بين 4 و7 (زبون تالٍ
    بطابور متتالٍ يستغرق وقت معقول) — لو الجمع طلع برّا فترتي الدوام
    المسموحتين (نهاية فترة، أو فترة راحة الغداء)، يقفز مباشرة لبداية
    فترة الدوام التالية بدل ما يطلع وقت مرفوض. لو ما بقيت فترة دوام
    اليوم أصلاً (كنا بآخر دقائق الفترة الثانية)، يرجّع فاضي (تُكتب
    يدوياً) بدل وقت مضلِّل."""
    try:
        hour_s, minute_s = time_str.split(":")
        total = int(hour_s) * 60 + int(minute_s) + random.randint(4, 7)
    except (ValueError, AttributeError):
        return ""
    for lo, hi in _ALLOWED_TIME_WINDOWS:
        if lo <= total <= hi:
            return f"{total // 60:02d}:{total % 60:02d}"
        if total < lo:
            return f"{lo // 60:02d}:{lo % 60:02d}"
    return ""


def _serialize_tab_draft(state):
    """يحوّل حالة تبويب (dict فيه fields/date/time/date_delivrance) لصيغة
    قابلة لـJSON — تواريخ Python لأسطر ISO. جزء من مسودة تدعم عدة
    تبويبات معاً (راجع _save_draft_now/_maybe_restore_draft)."""
    return {
        "fields": state["fields"],
        "date": state["date"].isoformat() if state["date"] else None,
        "time": state["time"],
        "date_delivrance": state["date_delivrance"].isoformat() if state["date_delivrance"] else None,
        "client_id": state.get("client_id"),
    }


def _deserialize_tab_draft(d):
    """عكس _serialize_tab_draft بالضبط — أسطر ISO ترجع تواريخ Python."""
    return {
        "fields": d.get("fields") or {},
        "date": date.fromisoformat(d["date"]) if d.get("date") else None,
        "time": d.get("time") or "",
        "date_delivrance": date.fromisoformat(d["date_delivrance"]) if d.get("date_delivrance") else None,
        "client_id": d.get("client_id"),
    }


class CDTab(ttk.Frame, CDEntryFactoryMixin):
    def __init__(self, parent, app):
        super().__init__(parent, padding=10)
        self.app = app

        # مصدر الحقيقة الوحيد لمستوى الزوم — نسبة مئوية صحيحة مباشرة (مو
        # فهرس بقائمة)، حتى تقدر تاخذ أي قيمة (زي ناتج Fit to Window غير
        # المضاعف لـ25) — راجع set_zoom بالأسفل لشرح كامل النظام.
        self.zoom = self._load_zoom_pref()
        self._bg_ox = self._bg_oy = 0  # آخر إزاحة (توسيط) محسوبة بـ_relayout — يستخدمها زوم حول المؤشر
        # يبقى None لغاية أول _relayout() ناجح (بعد _load_background) —
        # fit_to_window/_zoom_anchor_from_event يفحصونه قبل أي استخدام،
        # حتى ضغطة اختصار زوم مبكرة (قبل تحميل الخلفية) ما تعطّب البرنامج.
        self.current_bg_image = None
        self._bg_photo_cache = {}  # نسبة الزوم -> PhotoImage بدقة أصلية (بدون تكبير/تضبيب)
        self.field_widgets = {}
        self.field_window_ids = {}
        self.field_natural_size = {}
        self.bg_item_id = None

        self._draft_save_after_id = None
        # مسودة مُسترجَعة (بعد موافقة _maybe_restore_draft) بانتظار تطبيقها
        # على تبويبات فعلية — راجع _apply_pending_draft_tabs بـ_load_background.
        self._pending_draft_tabs = None
        # يوقف _save_office_settings وقتياً وسط _load_data_into_form —
        # راجع الشرح المفصّل هناك (فتح مستند قديم ما لازم يبدّل إعدادات
        # المكتب الدائمة).
        self._suppress_office_settings_save = False

        # مستندات الجلسة الحالية (كل مستند وُلّد بنجاح، بترتيب توليده) —
        # تراكم خام بس حالياً (بلا واجهة تستهلكه)، محجوز لشريط سفلي
        # مستقبلي (نتكلم عليه لاحقاً) يعرض تاريخ التوليد بنفس الجلسة.
        self._session_docs = []

        # تبويبات (زي كروم): كل تبويب = مستند CD مستقل تماماً (حقوله
        # الشخصية/المعاملة، تاريخ تراجعه...)، بنفس الودجت الحية المشتركة —
        # نحفظ/نحمّل لقطة كاملة عند كل تبديل بدل تكرار الشاشة كلها لكل
        # تبويب (أخف وأسلم، وما يكسر اختصارات لوحة المفاتيح المشتركة).
        # راجع _new_tab/_activate_tab/_close_tab وشرح _new_tab_state.
        # محدودية معروفة (مقبولة حالياً): مسودة الاسترجاع التلقائي بعد
        # إغلاق غير متوقع (_maybe_restore_draft/_save_draft_now) تحمي
        # التبويب *النشط* بس وقت الإغلاق — تبويبات ثانية مفتوحة بنفس
        # اللحظة ما تُسترجع لو البرنامج انقفل بالغلط.
        self._tabs = []
        self._tab_buttons = {}  # tab_id -> (إطار التبويب، StringVar عنوانه)
        self._active_tab_id = None
        self._next_tab_id = 1

        # وضع "عرض فقط" للتبويب النشط حالياً — راجع set_form_readonly
        # وشرح "readonly" بـ_new_tab_state.
        self._readonly_active = False

        # مزامنة تحديد الشريط الجانبي بعد رجوع تركيز النافذة (Alt+Tab
        # ورجوع) — راجع _on_app_reactivated/_maybe_resync_explorer_on_focus_return.
        self._resync_pending_after_reactivation = False

        # تراجع/إعادة (Ctrl+Z / Ctrl+Y) — راجع الشرح الكامل عند _undo بالأسفل.
        # الحالة هنا دائماً تخص التبويب *النشط حالياً* بس — تُستبدل بالكامل
        # عند أي تبديل تبويب (راجع _activate_tab).
        self._undo_stack = []
        self._redo_stack = []
        self._last_committed_snapshot = None
        self._undo_checkpoint_after_id = None

        self._build_top_bar()
        self._build_readonly_banner()
        self._build_canvas_area()  # ينادي _build_tab_strip() بنفسه (راجع شرحها)
        self.after(50, self._load_background)

        # تبويب CD يبقى حياً بالذاكرة حتى لو المستخدم انتقل لشاشة ثانية
        # (راجع ui/home/app_window.py: self._service_tabs) — اختصارات
        # الكيبورد تحت مربوطة بـbind_all (على مستوى التطبيق كامل، بغض
        # النظر مين الظاهر فعلياً)، فلازم تتعطّل تلقائياً وقت ما CD مو
        # الظاهرة، وإلا تشتغل حتى وشاشة ثانية (إعدادات مثلاً) مفتوحة.
        # self._shortcut() هي نقطة التعطيل الوحيدة — فعّالة True افتراضياً
        # (أول ما يُفتح CD، هو الظاهر مباشرة)، وapp_window.py تبدّلها عبر
        # activate_shortcuts()/deactivate_shortcuts() تحت بس، بلا أي
        # تغيير على سلوك أي اختصار وقت ما يكون فعّال.
        self._shortcuts_active = True

        # اختصارات لوحة مفاتيح: Ctrl+P توليد+طباعة، Ctrl+N مستند جديد
        # (نفس التبويب الحالي)، Ctrl+T تبويب جديد، Ctrl+W إغلاق التبويب
        # الحالي (نفس عادة كروم بالضبط)، Esc رجوع (بنفس حماية البيانات
        # الجارية)، Ctrl+Z تراجع، Ctrl+Y أو Ctrl+Shift+Z إعادة (نفس عادة
        # برامج الكتابة المعروفة — Ctrl+Y الأشيع بويندوز، Ctrl+Shift+Z
        # بديل شائع بمحررات ثانية).
        self.bind_all("<Control-p>", self._shortcut(self._print_flow))
        self.bind_all("<Control-P>", self._shortcut(self._print_flow))
        self.bind_all("<Control-n>", self._shortcut(self.new_document))
        self.bind_all("<Control-N>", self._shortcut(self.new_document))
        # Ctrl+Shift+N: الزبون التالي بطابور متتالٍ — راجع _next_client_tab.
        self.bind_all("<Control-Shift-N>", self._shortcut(self._next_client_tab))
        self.bind_all("<Control-t>", self._shortcut(self._new_tab))
        self.bind_all("<Control-T>", self._shortcut(self._new_tab))
        self.bind_all("<Control-w>", self._shortcut(lambda: self._close_tab(self._active_tab_id)))
        self.bind_all("<Control-W>", self._shortcut(lambda: self._close_tab(self._active_tab_id)))
        # Ctrl+Tab / Ctrl+Shift+Tab: التبويب التالي/السابق (زي كروم).
        # اكتشفنا تجريبياً إن bind_all("<Control-Tab>") لوحده ما يشتغل
        # أبداً من داخل أي خانة كتابة حقيقية (tk.Entry) — Tk نفسه عنده
        # ربط جاهز (<Key-Tab>) على مستوى صنف "Entry" (لا خانة بعينها)
        # يمسك أي ضغطة Tab (حتى لو مصحوبة بـCtrl) *قبل* ما توصل لـ
        # bind_all، بغض النظر هل الخانة عندها ربط خاص فينا إحنا أو لأ.
        # الحل الفعلي: كل خانة كتابة بالاستمارة مربوطة مباشرة (راجع
        # _bind_tab_switch_shortcuts) تطلق حدث افتراضي (<<CDTabNext/
        # Prev>>) نستقبله هون. الربط العام تحت يبقى فقط كخط دفاع ثاني
        # لعناصر مو خانات كتابة (زر، الـcanvas نفسه...).
        self.bind_all("<Control-Tab>", self._shortcut(self._switch_to_next_tab))
        self.bind_all("<Control-Shift-Tab>", self._shortcut(self._switch_to_previous_tab))
        self.bind_all("<<CDTabNext>>", self._shortcut(self._switch_to_next_tab))
        self.bind_all("<<CDTabPrev>>", self._shortcut(self._switch_to_previous_tab))
        self.bind_all("<Escape>", self._shortcut(self._on_back))
        self.bind_all("<Control-z>", self._shortcut(self._undo))
        self.bind_all("<Control-Z>", self._shortcut(self._undo))
        self.bind_all("<Control-y>", self._shortcut(self._redo))
        self.bind_all("<Control-Y>", self._shortcut(self._redo))
        self.bind_all("<Control-Shift-Z>", self._shortcut(self._redo))

        # اختصارات الزوم بالكيبورد (بطلب صريح) — نربط عدة صيغ لكل مفتاح
        # حتى تشتغل بغض النظر عن لوحة المفاتيح/حالة Shift: "+" غالباً
        # يحتاج Shift مع "=" (فـ<Control-plus> وحدها ما تكفي دايماً)،
        # وفيه كيبوردات فيها الرمز المطبوع فوق "=" مباشرة بلا Shift.
        # زر الفأرة الرقمي (Keypad) مربوط بردو لنفس السبب.
        self.bind_all("<Control-plus>", self._shortcut(self.zoom_in))
        self.bind_all("<Control-equal>", self._shortcut(self.zoom_in))
        self.bind_all("<Control-KP_Add>", self._shortcut(self.zoom_in))
        self.bind_all("<Control-minus>", self._shortcut(self.zoom_out))
        self.bind_all("<Control-KP_Subtract>", self._shortcut(self.zoom_out))
        self.bind_all("<Control-0>", self._shortcut(self.zoom_reset))
        self.bind_all("<Control-KP_0>", self._shortcut(self.zoom_reset))

        # مزامنة تحديد الشريط الجانبي بعد رجوع تركيز النافذة (راجع
        # _sync_explorer_to_active_tab وشرح الدالتين تحت بالتفصيل):
        # <Activate> على النافذة الجذرية يعلّم "فيه مزامنة معلَّقة"، وأول
        # تفاعل حقيقي (كليك/كتابة) بمساحة عمل CD نفسها ينفّذها.
        self.winfo_toplevel().bind("<Activate>", self._on_app_reactivated, add="+")
        self.bind_all("<Button-1>", self._maybe_resync_explorer_on_focus_return, add="+")
        self.bind_all("<KeyPress>", self._maybe_resync_explorer_on_focus_return, add="+")

    def _shortcut(self, func):
        """يلف أي استدعاء اختصار كيبورد بفحص self._shortcuts_active —
        وقت ما يكون فعّال (True)، يستدعي func() عادي بلا أي تغيير على
        سلوكه أو وظيفته؛ وقت ما يكون موقوف (False، لأن CD حالياً
        بالخلفية خلف شاشة ثانية — راجع activate_shortcuts/
        deactivate_shortcuts)، يتجاهل الضغطة بصمت."""
        def wrapper(_event=None):
            if self._shortcuts_active:
                return func()
        return wrapper

    def activate_shortcuts(self):
        """تُستدعى من ui/home/app_window.py لما تبويب CD يصير الظاهر
        فعلياً بمنطقة العرض — تفعّل كل اختصارات الكيبورد المربوطة أعلاه."""
        self._shortcuts_active = True

    def deactivate_shortcuts(self):
        """عكس activate_shortcuts — تُستدعى لما ينتقل المستخدم لشاشة
        ثانية (CD تبقى حية بالذاكرة بكامل حالتها بالخلفية، بس اختصاراتها
        موقوفة مؤقتاً حتى ما تشتغل وشاشة ثانية هي الظاهرة)."""
        self._shortcuts_active = False

    def _on_app_reactivated(self, _event):
        """<Activate> على النافذة الجذرية — النافذة رجعت تاخذ تركيز
        النظام (Alt+Tab من برنامج آخر ورجوع). ما نزامن الشريط فوراً هون
        (المستخدم ممكن يكون بشاشة ثانية أصلاً، أو ينوي يحدّد شي ثاني
        بالشريط بنفسه) — بس نعلّم "فيه مزامنة معلَّقة"، تنفَّذ عند أول
        تفاعل حقيقي بمساحة عمل CD (راجع _maybe_resync_explorer_on_focus_return)."""
        self._resync_pending_after_reactivation = True

    def _maybe_resync_explorer_on_focus_return(self, event):
        """أول كليك/كتابة حقيقية بمساحة عمل CD نفسها بعد رجوع تركيز
        النافذة (راجع _on_app_reactivated) — تزامن تحديد الشريط الجانبي
        مع التبويب النشط حالياً، مرة وحدة بس (تصفّر العلم فوراً)، ثم
        تحديد الشجرة يبقى حر تماماً بأي وقت ثاني بلا أي فرض. مربوطة
        bind_all (عالمياً) عمداً — بس نتحقق هون إن مصدر الحدث فعلاً
        داخل CD نفسها (مو شاشة ثانية أو تبويب خدمة حي ثاني) قبل التنفيذ."""
        if not self._resync_pending_after_reactivation:
            return
        widget = getattr(event, "widget", None)
        if widget is None:
            return
        try:
            is_within_cd = str(widget).startswith(str(self))
        except tk.TclError:
            is_within_cd = False
        if not is_within_cd:
            return
        self._resync_pending_after_reactivation = False
        self._sync_explorer_to_active_tab()

    # ---------- الشريط العلوي ----------
    def _build_top_bar(self):
        top_bar = ttk.Frame(self)
        top_bar.pack(fill="x", pady=(0, 4))
        # العنوان الكبير = اسم الموديل الحقيقي لي نشتغل عليه (بدل تسمية عامة
        # زي "لوحة التحكم") — قرار عمل معتمد لكل شاشات البرنامج القادمة:
        # كل تبويب يفتح على موديل معيّن يعرض اسمه الحقيقي هون.
        ttk.Label(top_bar, text="BORDEREAU D'ACHAT DEVISE", font=("Segoe UI", 14, "bold")).pack(side="left")

        # خانة "الزبون" (بيانات المعاملة، لا حقول المكتب Agence/Guichet/
        # Caisse — راجع البند 4-أ بمستند التصميم): تتغيّر مع كل تبويب.
        # ⚠️ قرار تنفيذي: استمارة CD كلها حقول فوق صورة النموذج بلا منطقة
        # استمارة عادية، فالشريط العلوي أقرب مكان طبيعي لخانة الزبون
        # (نفس مكوّن ClientPickerEntry المستخدَم بنافذة السجل بالضبط —
        # ui/common/client_picker.py). اختيارية دائماً (زبون عابر يضلّها
        # فاضية بلا أي منع من الحفظ). لو مُختارة قبل أول حفظ، الملف يروح
        # مباشرة لمجلد الزبون (راجع _do_generate).
        ttk.Separator(top_bar, orient="vertical").pack(side="left", fill="y", padx=10, pady=2)
        ttk.Label(top_bar, text="الزبون:").pack(side="left", padx=(0, 4))
        self.client_picker = ClientPickerEntry(top_bar, on_change=self._on_client_picker_change)
        self.client_picker.pack(side="left")

        # أزرار مرتبطة بتبويب/مستند فعلي مفتوح — تتعطّل تلقائياً لما ما
        # يبقى أي تبويب مفتوح (راجع _set_document_controls_enabled).
        # "🕘 السجل" مستثناة عمداً: تبقى شغالة دايماً (تفتح مستند حتى
        # بصفر تبويبات). زر "رجوع" منفصل انحذف (بطلب صريح — CD صارت
        # تبويب خدمة حي يبقى مفتوح بالخلفية، Escape كافي كاختصار رجوع
        # سريع بلا زر مرئي مكرر — راجع _on_back تحت).
        # الأزرار مجمَّعة منطقياً بفواصل بصرية (بطلب صريح — كانت 7 أزرار
        # متلاصقة بلا أي تمييز): [حفظ/طباعة] فعل التوليد الأساسي | [مستند
        # جديد] بدء معاملة | [السجل/رجوع] تنقّل. "⏭️ الزبون التالي" ونظام
        # التنقّل بين التبويبات انتقلا للشريط السفلي (راجع تحت) — عائلة
        # "تنقّل تسلسلي بالشغل" وحدة (تبويب بعده، زبون بعده)، بطلب صريح.
        self._document_dependent_buttons = []
        # نطاق فرعي من الأعلى: تتعطّل بصرياً كمان (إضافة للشرط الحالي —
        # وجود تبويب مفتوح) وقت readonly (راجع set_form_readonly تحت) —
        # طباعة/السجل/الزوم/◀▶/الزبون التالي بلا أي لمس (بطلب صريح).
        self._readonly_guarded_buttons = []
        save_btn = ttk.Button(top_bar, text="💾 حفظ", command=self.generate_document)
        save_btn.pack(side="right")
        # زر "📄 PDF" المنفصل انحذف (بطلب صريح) — صار كل حفظ حقيقي يولّد
        # PDF دائم تلقائياً بالأصل (راجع _do_generate)، فما عاد له داعٍ.
        # "💾 حفظ في مكان آخر": نفس الحفظ الرسمي بالضبط، بس بمكان تختاره
        # أنت (داخل travail بس — راجع _save_to_other_location) بدل المكان
        # التلقائي — يستبدله، مو نسخة إضافية جنبه (بطلب صريح).
        save_as_btn = ttk.Button(top_bar, text="💾 حفظ في مكان آخر", command=self._save_to_other_location)
        save_as_btn.pack(side="right", padx=(0, 8))
        print_btn = ttk.Button(top_bar, text="🖨️ طباعة", command=self._print_flow)
        print_btn.pack(side="right", padx=(0, 8))
        ttk.Separator(top_bar, orient="vertical").pack(side="right", fill="y", padx=8, pady=2)
        new_doc_btn = ttk.Button(top_bar, text="🆕 مستند جديد", command=self.new_document)
        new_doc_btn.pack(side="right")
        ttk.Separator(top_bar, orient="vertical").pack(side="right", fill="y", padx=8, pady=2)
        ttk.Button(top_bar, text="🕘 السجل", command=self.open_history).pack(side="right")
        self._document_dependent_buttons.extend([save_btn, save_as_btn, print_btn, new_doc_btn])
        self._readonly_guarded_buttons.extend([save_btn, save_as_btn, new_doc_btn])

        # ---------- شريط ثاني (سفلي): تنقّل وعرض — تراجع/إعادة، تنقّل
        # تسلسلي (تبويب سابق/تالٍ + زبون تالٍ)، وزوم أقصى اليمين مع إرجاع
        # سريع لـ100% (بطلب صريح، نفس مكان الزوم بمعظم البرامج). "❓
        # الاختصارات" انتقل لقائمة "⋮" صغيرة (نادر الاستخدام، ما يستاهل
        # زر دائم)، و"📁 فتح مجلد المستندات" انحذف (الشريط الجانبي يسوي
        # نفس الشي وأفضل)، و"🗂️ الشريط الجانبي" انحذف كمان (السهم الجديد
        # الملتصق بالشريط نفسه يسوي وظيفته — راجع _build_canvas_area). ----------
        tools_bar = ttk.Frame(self)
        tools_bar.pack(fill="x", pady=(0, 8))

        undo_bar = ttk.Frame(tools_bar)
        undo_bar.pack(side="left")
        undo_btn = ttk.Button(undo_bar, text="↶ تراجع", command=self._undo)
        undo_btn.pack(side="left")
        redo_btn = ttk.Button(undo_bar, text="↷ إعادة", command=self._redo)
        redo_btn.pack(side="left", padx=(4, 0))
        self._document_dependent_buttons.extend([undo_btn, redo_btn])
        self._readonly_guarded_buttons.extend([undo_btn, redo_btn])

        ttk.Separator(tools_bar, orient="vertical").pack(side="left", fill="y", padx=12, pady=2)

        nav_bar = ttk.Frame(tools_bar)
        nav_bar.pack(side="left")
        ttk.Button(nav_bar, text="◀", width=3, command=self._switch_to_previous_tab).pack(side="left")
        # طابور زبائن متتالي (Ctrl+Shift+N): تبويب جديد مبدوء من التبويب
        # النشط الحالي — رقم البوردرو +1، نفس التاريخ، الوقت +4-7 دقائق
        # عشوائي، ونفس Tx de change/Devise — راجع _next_client_tab لتفاصيل
        # كل قاعدة. عمداً غير مُدرَج بـ_document_dependent_buttons: شرط
        # تفعيله أدق من "فيه تبويب نشط" بس (يحتاج كمان بيانات فعلية —
        # راجع _update_next_button_state)، فتركه بتلك القائمة كان يخليه
        # عرضة لإعادة تفعيله غلط من _set_document_controls_enabled بأي
        # مسار جديد ينادي _update_no_tab_state() بعده. _update_next_button_state
        # نفسها تتكفّل بحالة صفر تبويبات لحالها (تفحص self._active_tab_id مباشرة).
        self._next_client_btn = ttk.Button(nav_bar, text="⏭️ الزبون التالي", command=self._next_client_tab)
        self._next_client_btn.pack(side="left", padx=4)
        ttk.Button(nav_bar, text="▶", width=3, command=self._switch_to_next_tab).pack(side="left")

        zoom_bar = ttk.Frame(tools_bar)
        zoom_bar.pack(side="right")
        ttk.Button(zoom_bar, text="＋", width=3, command=self.zoom_in).pack(side="right")
        self.zoom_label = ttk.Label(zoom_bar, text="100%", width=5, anchor="center", cursor="hand2")
        self.zoom_label.pack(side="right", padx=4)
        self.zoom_label.bind("<Button-1>", lambda _e: self.zoom_reset())
        ttk.Button(zoom_bar, text="－", width=3, command=self.zoom_out).pack(side="right")
        # ⤢ ملاءمة النافذة: تحسب أقل نسبة تخلي الورقة كاملة ظاهرة بمساحة
        # العرض الحالية بلا سكرول (راجع fit_to_window) — فعل لمرة وحدة،
        # مو وضع دائم يتابع تغيّر حجم النافذة. الرجوع لـ100% يبقى بكليك
        # على النسبة نفسها (زر منفصل هون كان تكراراً بلا داعي).
        ttk.Button(zoom_bar, text="⤢", width=3, command=self.fit_to_window).pack(side="right", padx=(4, 0))

        self._more_menu = tk.Menu(tools_bar, tearoff=0)
        self._more_menu.add_command(label="❓ الاختصارات", command=self._show_shortcuts_help)
        self._more_btn = ttk.Menubutton(tools_bar, text="⋮", width=3, menu=self._more_menu)
        self._more_btn.pack(side="right", padx=(0, 8))

    # ---------- شريط تنبيه "عرض فقط" ----------
    def _build_readonly_banner(self):
        """شريط تنبيه واضح (خلفية صفراء فاتحة) يظهر بس والتبويب النشط
        حالياً بوضع "عرض فقط" (راجع set_form_readonly) — لا يُحزَم
        (pack) هنا افتراضياً، يظهر/يختفي ديناميكياً عبر
        _update_readonly_banner. الزر "🔓 فتح للتعديل" يفك القفل مباشرة
        بلا أي تأكيد إضافي (بطلب صريح — التأكيدات محجوزة للأمور
        الحساسة فقط، وفتح قفل للتعديل مو منها)."""
        self._readonly_banner = tk.Frame(self, bg="#fff3cd", padx=10, pady=6)
        tk.Label(
            self._readonly_banner,
            text="🔒 عرض فقط — هذا عمل منتهي، التعديلات لن تُحفظ قبل فتح القفل",
            bg="#fff3cd", font=("Segoe UI", 10, "bold"),
        ).pack(side="right")
        ttk.Button(self._readonly_banner, text="🔓 فتح للتعديل", command=self._unlock_active_tab).pack(side="left")

    def set_form_readonly(self, readonly):
        """يقفل/يفك قفل كل حقول الاستمارة الحية دفعة وحدة — قفل ثنائي
        (الكل أو ولا شي، بلا حالات وسط، بطلب صريح): "readonly" لا
        "disabled" حتى يبقى النص واضحاً بلا تعتيم وقابلاً للتحديد/النسخ
        وهو مقفول. يُستخدم لحماية "عمل منتهي" فُتح من الشريط الجانبي
        بلا نية تعديل صريحة (راجع _open_case_readonly) من تعديل غير
        مقصود. بمجرد ما يُفتح القفل تعود الحقول والاستمارة للحياة
        بالكامل فوراً، بلا أي تأكيد إضافي (بطلب صريح)."""
        for widget in self.field_widgets.values():
            if hasattr(widget, "set_readonly"):
                widget.set_readonly(readonly)
            elif isinstance(widget, tk.Entry):
                try:
                    widget.configure(state="readonly" if readonly else "normal")
                except tk.TclError:
                    pass
        if hasattr(self, "client_picker"):
            self.client_picker.set_state("readonly" if readonly else "normal")
        self._readonly_active = readonly
        if self._active_tab_id is not None:
            tab = self._tab_by_id(self._active_tab_id)
            if tab is not None:
                tab["readonly"] = readonly
        self._update_readonly_banner()
        self._update_readonly_guarded_buttons()

    def _on_client_picker_change(self):
        """تُنادى من ClientPickerEntry عند اختيار/مسح زبون — نخزّنها فوراً
        بحالة التبويب النشط حتى ما تنخسر لو تبدّل التبويب قبل أي حفظ
        (نفس مبدأ باقي حقول التبويب)."""
        if self._active_tab_id is None:
            return
        tab = self._tab_by_id(self._active_tab_id)
        if tab is not None:
            tab["client_id"] = self.client_picker.get_client_id()

    def _update_readonly_banner(self):
        if self._readonly_active:
            self._readonly_banner.pack(fill="x", pady=(0, 6), before=self._paned)
        else:
            self._readonly_banner.pack_forget()

    def _update_readonly_guarded_buttons(self):
        """💾 حفظ/💾 حفظ في مكان آخر/🆕 مستند جديد/↶ تراجع/↷ إعادة —
        تتعطّل بصرياً وقت readonly، بالإضافة لشرطها الأصلي (وجود تبويب
        مفتوح — راجع _document_dependent_buttons/_set_document_controls_enabled).
        الشرطان معاً محسوبان من جديد هنا (AND) بدل تبديل حالة كل واحد
        لحاله، حتى ما يتعارضا (زي إعادة تفعيل الأزرار غلط عند فتح قفل
        وقت ما ما يبقى أي تبويب مفتوح أصلاً)."""
        enabled = self._active_tab_id is not None and not self._readonly_active
        state = "!disabled" if enabled else "disabled"
        for btn in self._readonly_guarded_buttons:
            btn.state([state])

    def _unlock_active_tab(self):
        self.set_form_readonly(False)

    def _open_case_readonly(self, file_path):
        """يُستدعى من الشريط الجانبي (نقرة مزدوجة أو "📂 فتح" — راجع
        on_open_file بـFileExplorerPanel) قبل الفتح الافتراضي بالنظام.
        لو الملف مرتبط بسطر CD كامل البيانات: يفتحه بتبويب جديد
        **للقراءة فقط** مباشرة (حماية من تعديل غير مقصود لعمل منتهي —
        بطلب صريح)، أو يقفز للتبويب القابل للتعديل أصلاً لو نفس الملف
        مفتوح فيه حالياً بدل فتح نسخة قراءة-فقط ثانية زيادة منه. يرجّع
        True لو تكفّلنا بالفتح (فما داعي يفتحه الشريط بالنظام كمان)،
        False لو الملف مو مرتبط بأي سطر (أو مستند قديم بلا بيانات كاملة
        محفوظة) — يُفتح عادي بالنظام بمساره الطبيعي."""
        try:
            abs_path = _norm_path(file_path)
        except (TypeError, ValueError):
            return False
        for tab in self._tabs:
            loaded_from = tab.get("loaded_from")
            if loaded_from and any(
                candidate and _norm_path(candidate) == abs_path
                for candidate in (loaded_from.get("file_path"), loaded_from.get("pdf_path"))
            ):
                self._activate_tab(tab["id"])
                return True
        row = find_cd_document_by_path(file_path)
        if row is None:
            return False
        data = deserialize_cd_data(row.get("full_data_json"))
        if data is None:
            return False  # مستند قديم بلا بيانات كاملة محفوظة — يُفتح عادي بالنظام
        self._open_data_in_new_tab(
            data, source_row_id=row["id"], source_file_path=row.get("file_path"),
            source_pdf_path=row.get("pdf_path"), source_client_id=row.get("client_id"),
        )
        self.set_form_readonly(True)
        return True

    # ---------- شريط التبويبات (زي كروم) ----------
    def _build_tab_strip(self, holder):
        """شريط تبويبات فوق ورقة الاستمارة مباشرة (جوّا holder، صف أول
        فوق الـcanvas — راجع _build_canvas_area) — عرضه يتطابق مع عرض
        الورقة بالضبط، بغض النظر هل الشريط الجانبي ظاهر أو مخفي. كل
        تبويب = مستند CD مستقل مفتوح بنفس الوقت (عنوانه = رقم البوردرو
        المكتوب فيه، يتحدّث حياً وأنت تكتب). زر "+" يفتح تبويب جديد فاضي،
        كل تبويب فيه "✕" لإغلاقه (بتأكيد لو فيه بيانات غير محفوظة).

        لما تكثر التبويبات وما تعود تتّسع بعرض الشاشة، ما نصغّرها (لازم
        تبقى تبين رقم البوردرو كامل بوضوح) ولا نخليها تختفي بصمت (بگ
        حقيقي لاحظناه: Tk يخفي العناصر اللي ما تتّسع، بما فيها زر "+"
        نفسه، بلا أي تنبيه أو طريقة تمرير) — بدلها نحطها بمنطقة قابلة
        للتمرير الأفقي (self._tabs_canvas) بعرض ثابت، مع سهمين (◀/▶)
        يظهرون بس لما فيه تبويبات فعلاً مخفية بتلك الجهة، وقائمة منسدلة
        (▾) للقفز المباشر لأي تبويب برقمه بدل التمرير المتكرر. زر "+"
        وزر ▾ والسهمان كلهم برّا منطقة التمرير (يُحجز مكانهم من الحافة
        اليمنى أولاً بـpack(side="right")) حتى يبقوا ظاهرين وقابلين
        للضغط دايماً بغض النظر عن عدد التبويبات أو موضع التمرير الحالي."""
        self.tab_strip = ttk.Frame(holder)
        self.tab_strip.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))

        # نحجز مساحة الأزرار الثابتة (يمين الشريط) أولاً — قبل منطقة
        # التمرير المرنة — حتى تبقى مضمونة الظهور مهما ضاقت المساحة.
        self._plus_button = ttk.Button(self.tab_strip, text="+", width=3, command=self._new_tab)
        self._plus_button.pack(side="right")

        self._tabs_dropdown_btn = ttk.Button(
            self.tab_strip, text="▾", width=3, command=self._show_tabs_dropdown,
        )
        self._tab_right_arrow = ttk.Button(self.tab_strip, text="▶", width=2, command=self._scroll_tabs_right)
        self._tab_left_arrow = ttk.Button(self.tab_strip, text="◀", width=2, command=self._scroll_tabs_left)
        # الثلاثة أعلاه يُظهَرون/يُخفَون ديناميكياً حسب الحاجة الفعلية —
        # راجع _update_tab_scroll_arrows (ما نـpack أي وحد منهم هنا).

        bg = ttk.Style().lookup("TFrame", "background") or "#f0f0f0"
        self._tabs_canvas = tk.Canvas(self.tab_strip, height=1, highlightthickness=0, bg=bg)
        self._tabs_canvas.pack(side="left", fill="both", expand=True)

        self._tabs_inner = ttk.Frame(self._tabs_canvas)
        self._tabs_window_id = self._tabs_canvas.create_window(0, 0, window=self._tabs_inner, anchor="nw")
        self._tab_scroll_x = 0  # بكسل: كم بعدنا لليمين عن أول تبويب (0 = البداية)
        self._tabs_inner.bind("<Configure>", lambda _e: self._update_tab_scroll_arrows())
        self._tabs_canvas.bind("<Configure>", lambda _e: self._update_tab_scroll_arrows())

    def _tab_scroll_bounds(self):
        inner_w = self._tabs_inner.winfo_reqwidth()
        view_w = self._tabs_canvas.winfo_width()
        return inner_w, view_w, max(inner_w - view_w, 0)

    def _set_tab_scroll(self, x):
        _inner_w, _view_w, max_scroll = self._tab_scroll_bounds()
        self._tab_scroll_x = max(0, min(x, max_scroll))
        self._update_tab_scroll_arrows()

    def _update_tab_scroll_arrows(self):
        """يُنادى بعد أي تغيير يمكن يأثر على مساحة/عدد التبويبات (فتح/
        إغلاق تبويب، تغيّر حجم النافذة...) — يحدّث موضع منطقة التمرير
        فعلياً، وارتفاع الـcanvas ليطابق ارتفاع التبويبات الحقيقي، ويُظهر/
        يُخفي السهمين وزر ▾ حسب الحاجة الفعلية بس (بلا تصغير أي تبويب)."""
        self._tabs_canvas.configure(height=max(self._tabs_inner.winfo_reqheight(), 1))
        inner_w, view_w, max_scroll = self._tab_scroll_bounds()
        if self._tab_scroll_x > max_scroll:
            self._tab_scroll_x = max_scroll
        self._tabs_canvas.coords(self._tabs_window_id, -self._tab_scroll_x, 0)
        self._tabs_canvas.configure(scrollregion=(0, 0, inner_w, self._tabs_canvas.winfo_reqheight()))

        if self._tab_scroll_x > 0:
            if not self._tab_left_arrow.winfo_ismapped():
                self._tab_left_arrow.pack(side="left", before=self._tabs_canvas)
        else:
            self._tab_left_arrow.pack_forget()

        if len(self._tabs) > 1:
            if not self._tabs_dropdown_btn.winfo_ismapped():
                self._tabs_dropdown_btn.pack(side="right", before=self._plus_button)
        else:
            self._tabs_dropdown_btn.pack_forget()

        if self._tab_scroll_x < max_scroll:
            if not self._tab_right_arrow.winfo_ismapped():
                anchor = self._tabs_dropdown_btn if self._tabs_dropdown_btn.winfo_ismapped() else self._plus_button
                self._tab_right_arrow.pack(side="right", before=anchor)
        else:
            self._tab_right_arrow.pack_forget()

    def _scroll_tabs_right(self):
        """▶: يخفي أوتوماتيكياً أول تبويب ظاهر حالياً (حافة اليسار)
        ويبيّن كامل التبويب اللي بعده بمكانه — بالضبط زي ما طُلب."""
        target = self._tab_scroll_x
        for child in self._tabs_inner.winfo_children():
            x1 = child.winfo_x() + child.winfo_width()
            if x1 > self._tab_scroll_x + 1:
                target = x1
                break
        self._set_tab_scroll(target)

    def _scroll_tabs_left(self):
        """◀: يبيّن كامل التبويب المخفي مباشرة قبل أول تبويب ظاهر حالياً."""
        target = 0
        for child in self._tabs_inner.winfo_children():
            x0 = child.winfo_x()
            if x0 >= self._tab_scroll_x - 1:
                break
            target = x0
        self._set_tab_scroll(target)

    def _ensure_tab_visible(self, tab_id):
        """يلف شريط التبويبات تلقائياً حتى يبين التبويب المطلوب كامل —
        لازم يُنادى كل مرة يتغيّر فيها التبويب *النشط* لتبويب ممكن يكون
        مخفي حالياً بمنطقة التمرير (تفعيل بزر/قائمة، إعادة تفعيل تبويب
        بعد إغلاق واحد جنبه، فتح تبويب جديد بزر "+"، أو فتح مستند من
        السجل) — تصحيح إلزامي، مو اختياري: بدونه ممكن ينفتح/يتفعّل
        تبويب المستخدم ما يشوفه أصلاً لو الشريط ممتلئ."""
        frame, _label_var = self._tab_buttons.get(tab_id, (None, None))
        if frame is None:
            return
        # تكرار قصير (مو مرة وحدة): تغيير موضع التمرير ممكن يُظهر/يُخفي
        # سهم ◀/▶ أو زر ▾ (راجع _update_tab_scroll_arrows)، وهذا يغيّر
        # عرض منطقة العرض الفعلي (view_w) نفسها — فحساب أول مرة ممكن
        # يصير غير دقيق بمجرد ما يبان سهم جديد. يتقارب عملياً خلال
        # تكرارين-ثلاثة (العرض المتاح ما يضيق أكثر من مرة وحدة إضافية).
        for _ in range(4):
            self.update_idletasks()  # نضمن winfo_x()/winfo_width() محدّثة فعلياً
            x0 = frame.winfo_x()
            x1 = x0 + frame.winfo_width()
            _inner_w, view_w, _max_scroll = self._tab_scroll_bounds()
            if x0 < self._tab_scroll_x:
                new_scroll = x0
            elif x1 > self._tab_scroll_x + view_w:
                new_scroll = x1 - view_w
            else:
                break
            if new_scroll == self._tab_scroll_x:
                break
            self._set_tab_scroll(new_scroll)

    def _show_tabs_dropdown(self):
        """قائمة منسدلة (▾) بكل التبويبات المفتوحة برقمها — قفزة مباشرة
        لأي وحد بضغطة وحدة، بدل تمرير متكرر بالأسهم لما تكثر التبويبات.
        التبويب النشط حالياً يتميّز بـ"●" أول العنصر."""
        menu = tk.Menu(self, tearoff=0)
        for t in self._tabs:
            tab_id = t["id"]
            label_var = self._tab_buttons[tab_id][1]
            prefix = "● " if tab_id == self._active_tab_id else "   "
            menu.add_command(
                label=f"{prefix}{label_var.get()}", command=lambda tid=tab_id: self._activate_tab(tid),
            )
        x = self._tabs_dropdown_btn.winfo_rootx()
        y = self._tabs_dropdown_btn.winfo_rooty() + self._tabs_dropdown_btn.winfo_height()
        menu.tk_popup(x, y)

    def _switch_to_next_tab(self):
        if len(self._tabs) < 2:
            return
        ids = [t["id"] for t in self._tabs]
        idx = ids.index(self._active_tab_id)
        self._activate_tab(ids[(idx + 1) % len(ids)])

    def _switch_to_previous_tab(self):
        if len(self._tabs) < 2:
            return
        ids = [t["id"] for t in self._tabs]
        idx = ids.index(self._active_tab_id)
        self._activate_tab(ids[(idx - 1) % len(ids)])

    def _new_tab_state(self, tab_id):
        fields = {k: "" for k in _TRANSACTIONAL_DRAFT_KEYS}
        return {
            "id": tab_id,
            "no": "",
            "fields": fields,
            "date": None, "time": "", "date_delivrance": None,
            "undo_stack": [], "redo_stack": [], "last_committed": None,
            # "آخر حالة معروفة كمستند فعلي" (توليد ناجح، أو تحميل مستند سابق
            # من السجل) — أساس مقارنة "فيه تعديل ما تحفّظ بعد" اللي يحدّد هل
            # ✕ يسأل تأكيد أو يسكّر التبويب مباشرة (راجع _tab_is_dirty).
            # فاضية بالبداية دائماً — تبويب جديد فاضٍ "نظيف" بلا أي تعديل.
            "saved_snapshot": self._snapshot_of(fields, None, "", None),
            # هوية "الحالة" اللي هذا التبويب يمثّلها بقاعدة البيانات — None
            # لتبويب فاضٍ جديد (أول حفظ له = سطر جديد). بعد أول حفظ ناجح
            # (من هذا التبويب، أو تحميل حالة موجودة من السجل)، تصير
            # {"row_id", "file_path", "pdf_path"} — أي حفظ تالٍ **بنفس
            # هذا التبويب** يحدّث فوقها (يستبدل الملفين، يحدّث نفس السطر)
            # بدل تكرارها، بغض النظر حتى لو تغيّر رقم البوردرو نفسه —
            # راجع _do_generate وشرح "حفظ" مقابل "حفظ في مكان آخر".
            "loaded_from": None,
            # زبون هذا التبويب (client_id من جدول clients) — None لتبويب
            # فاضٍ أو زبون عابر. يتعبّى من خانة الزبون بالشريط العلوي،
            # ويُحفظ/يُحمّل مع باقي حالة التبويب (راجع _save_active_tab_state/
            # _apply_state_to_widgets). أول حفظ وهو معبّى = الملف يروح
            # مباشرة لمجلد الزبون (راجع _do_generate).
            "client_id": None,
            # وضع "عرض فقط" (راجع set_form_readonly): True لتبويب فُتح
            # من الشريط الجانبي بنقرة/فتح عادي لحالة "عمل منتهي" (بلا
            # نية تعديل صريحة — راجع _open_case_readonly)، بلا حاجة
            # لأي تأكيد لفتح القفل لاحقاً (بطلب صريح). تبويب فاضٍ جديد
            # دائماً False — قابل للتعديل عادي من أول لحظة.
            "readonly": False,
        }

    @staticmethod
    def _snapshot_of(fields, date_val, time_val, delivrance_val):
        return {
            "fields": dict(fields),
            "date": date_val,
            "time": time_val,
            "date_delivrance": delivrance_val,
        }

    def _tab_is_dirty(self, tab_id):
        """True لو فيه أي فرق بين حالة التبويب الحالية وآخر حالة معروفة
        كمستند فعلي (saved_snapshot) — تُستخدم حصراً لتحديد سلوك ✕ (زي
        برامج ويندوز العادية: تسكّر بصمت لو ما تغيّر شي عن آخر حفظ، تسأل
        تأكيد لو فيه أي تعديل ولو بسيط). لا علاقة لها بحماية البيانات
        نفسها (المسودة تُحفظ دائماً بغض النظر — راجع _close_tab)."""
        tab = self._tab_by_id(tab_id)
        if tab is None:
            return False
        if tab_id == self._active_tab_id:
            fields, date_val, time_val, delivrance_val = self._capture_state_from_widgets()
            current = self._snapshot_of(fields, date_val, time_val, delivrance_val)
        else:
            current = self._snapshot_of(tab["fields"], tab["date"], tab["time"], tab["date_delivrance"])
        return current != tab.get("saved_snapshot")

    def _tab_by_id(self, tab_id):
        return next((t for t in self._tabs if t["id"] == tab_id), None)

    @staticmethod
    def _tab_label_text(no_value):
        no_value = (no_value or "").strip()
        return no_value if no_value else "بدون رقم"

    def _make_tab_widget(self, tab_id, label_text):
        # داخل _tabs_inner (منطقة التمرير الأفقي) لا self.tab_strip مباشرة
        # — راجع _build_tab_strip. زر "+" وزر ▾ والأسهم كلهم عناصر ثابتة
        # مستقلة برّا هالمنطقة، ما يحتاجون أي إعادة تعبئة بعد الآن.
        frame = ttk.Frame(self._tabs_inner, relief="raised", borderwidth=1)
        label_var = tk.StringVar(value=label_text)
        lbl = ttk.Label(frame, textvariable=label_var, padding=(8, 4))
        lbl.pack(side="left")
        lbl.bind("<Button-1>", lambda _e, tid=tab_id: self._activate_tab(tid))
        close_btn = ttk.Label(frame, text=" ✕", padding=(2, 4), foreground="#888")
        close_btn.pack(side="left")
        close_btn.bind("<Button-1>", lambda _e, tid=tab_id: self._close_tab(tid))
        close_btn.bind("<Enter>", lambda _e: close_btn.configure(foreground="red"))
        close_btn.bind("<Leave>", lambda _e: close_btn.configure(foreground="#888"))
        frame.pack(side="left", padx=(0, 2))
        return frame, label_var

    def _refresh_tab_styles(self):
        for tab_id, (frame, _label_var) in self._tab_buttons.items():
            frame.configure(relief="sunken" if tab_id == self._active_tab_id else "raised")

    def _set_document_controls_enabled(self, enabled):
        state = "!disabled" if enabled else "disabled"
        for btn in self._document_dependent_buttons:
            btn.state([state])

    def _update_no_tab_state(self):
        """يتحدّث بعد أي تغيير بعدد/نشاط التبويبات — يظهر لوحة "لا يوجد
        تبويب مفتوح" فوق الورقة ويعطّل أزرار المستند (💾/🖨️/🆕/↶/↷) لو
        ما يبقى أي تبويب نشط، ويخفيها/يفعّلها لما يرجع فيه تبويب. "🕘
        السجل" و"← رجوع" و"🗂️ الشريط الجانبي" ما تتأثر إطلاقاً — تشتغل
        دايماً بغض النظر عن عدد التبويبات (راجع _build_top_bar)."""
        has_active = self._active_tab_id is not None
        self._set_document_controls_enabled(has_active)
        self._update_readonly_guarded_buttons()
        if has_active:
            self._no_tab_placeholder.place_forget()
        else:
            # in_=self.canvas: تغطّي مساحة الـcanvas بالذات (مو كل holder،
            # اللي صار فيه شريط التبويبات كمان بعد نقله جوّاه — راجع
            # _build_canvas_area) حتى زر "+" يضل ظاهر وقابل للضغط.
            self._no_tab_placeholder.place(in_=self.canvas, relx=0, rely=0, relwidth=1, relheight=1)

    # ---------- التقاط/تطبيق حالة تبويب على الودجت الحية المشتركة ----------
    def _capture_state_from_widgets(self):
        """يلتقط بيانات *المعاملة* الحالية من الودجت الحية — بدون حقول
        المكتب (Agence/Guichet/Caisse/Guichetier)، هذي عابرة للتبويبات
        (تمثّل الشباك/الموظف الحالي، مو الزبون المفتوح بهذا التبويب) فتبقى
        كما هي بغض النظر عن أي تبويب نشط."""
        fields = {k: self._field_var(k).get() for k in _TRANSACTIONAL_DRAFT_KEYS}
        try:
            date_val = self.date_entry.get_date()
        except ValueError:
            date_val = None
        try:
            time_val = self.time_entry.get_time_str()
        except ValueError:
            time_val = ""
        try:
            delivrance_val = self.delivrance_entry.get_date()
        except ValueError:
            delivrance_val = None
        return fields, date_val, time_val, delivrance_val

    def _apply_state_to_widgets(self, state):
        self._triangle_updating = True
        try:
            for key, value in state["fields"].items():
                self._field_var(key).set(value)
        finally:
            self._triangle_updating = False
        # نفس ملاحظة _currency_entry: var.set() يعطّل validate أوتوماتيكياً
        # — نرجّعه يدوياً لحقول المبالغ الثلاثة.
        for key in ("eur", "dzd", "taux"):
            self.field_widgets[key].configure(validate="key")
        self.date_entry.set_date(state["date"])
        self.time_entry.set_time_str(state["time"])
        self.delivrance_entry.set_date(state["date_delivrance"])
        # خانة الزبون خاصة بكل تبويب — تُعاد تعبئتها كل تبديل تبويب (تعبئة
        # برمجية: بلا إطلاق بحث حي أو on_change).
        self.client_picker.set_client_id(state.get("client_id"))
        # وضع "عرض فقط" خاص بكل تبويب لحاله (راجع set_form_readonly) —
        # لازم يُعاد تطبيقه على الودجت الحية كل تبديل تبويب، وإلا تبويب
        # عادي مفتوح جنب تبويب مقفول يورّث قفله بالغلط (أو العكس).
        self.set_form_readonly(state.get("readonly", False))

    def _tab_state_has_data(self, state):
        """نفس منطق has_unsaved_data() بالضبط، بس لتبويب غير نشط حالياً
        (نفحص لقطته المخزَّنة، مو ودجت حية — ماكو ودجت حية له أصلاً)."""
        for key in _TRANSACTIONAL_DRAFT_KEYS:
            if (state["fields"].get(key) or "").strip():
                return True
        return bool(state["date"] or state["time"] or state["date_delivrance"])

    def _save_active_tab_state(self):
        if self._active_tab_id is None:
            return
        tab = self._tab_by_id(self._active_tab_id)
        if tab is None:
            return
        fields, date_val, time_val, delivrance_val = self._capture_state_from_widgets()
        tab["fields"] = fields
        tab["date"] = date_val
        tab["time"] = time_val
        tab["date_delivrance"] = delivrance_val
        tab["no"] = fields.get("no", "")
        tab["client_id"] = self.client_picker.get_client_id()
        tab["undo_stack"] = list(self._undo_stack)
        tab["redo_stack"] = list(self._redo_stack)
        tab["last_committed"] = self._last_committed_snapshot

    def _activate_tab(self, tab_id):
        if tab_id == self._active_tab_id:
            return
        self._save_active_tab_state()
        tab = self._tab_by_id(tab_id)
        if tab is None:
            return
        self._active_tab_id = tab_id
        self._apply_state_to_widgets(tab)
        self._undo_stack = list(tab["undo_stack"])
        self._redo_stack = list(tab["redo_stack"])
        self._last_committed_snapshot = tab["last_committed"]
        if self._undo_checkpoint_after_id is not None:
            self.after_cancel(self._undo_checkpoint_after_id)
            self._undo_checkpoint_after_id = None
        self._refresh_tab_styles()
        self._ensure_tab_visible(tab_id)
        self._update_next_button_state()
        self._sync_explorer_to_active_tab()

    def _sync_explorer_to_active_tab(self):
        """يحدّد بالشريط الجانبي مسار التبويب النشط حالياً (لو محمَّل من
        ملف فعلي — تبويب جديد فاضٍ ما فيه شي يُحدَّد له) — يُنادى عند
        تبديل التبويب (راجع _activate_tab) وعند أول تفاعل بمساحة الشغل
        بعد رجوع تركيز النافذة (راجع _maybe_resync_explorer_on_focus_return).
        تحديد الشجرة يبقى حر تماماً بأي وقت ثاني (المستخدم يقدر يحدّد
        أي مكان ثاني بالشريط بلا ما نرجّعه لهون قسراً)."""
        tab = self._tab_by_id(self._active_tab_id) if self._active_tab_id is not None else None
        if tab is None:
            return
        loaded_from = tab.get("loaded_from")
        if not loaded_from:
            return
        path = loaded_from.get("pdf_path") or loaded_from.get("file_path")
        if path:
            self.explorer_panel.reveal_path(path)

    def _new_tab(self):
        """يفتح تبويب جديد فاضٍ (زر "+" أو Ctrl+T) — يحفظ حالة التبويب
        الحالي أولاً (ما يلمسها إطلاقاً)، ثم يفضّي الودجت الحية لتبويب
        جديد مستقل تماماً."""
        self._save_active_tab_state()
        tab_id = self._next_tab_id
        self._next_tab_id += 1
        state = self._new_tab_state(tab_id)
        self._tabs.append(state)
        frame, label_var = self._make_tab_widget(tab_id, self._tab_label_text(state["no"]))
        self._tab_buttons[tab_id] = (frame, label_var)
        self._active_tab_id = tab_id
        self._apply_state_to_widgets(state)
        self._reset_undo_history()
        self._refresh_tab_styles()
        self._update_no_tab_state()
        self._update_tab_scroll_arrows()
        self._ensure_tab_visible(tab_id)
        self._update_next_button_state()
        self._focus_no_field()

    def _close_tab(self, tab_id):
        if tab_id is None:
            return
        tab = self._tab_by_id(tab_id)
        if tab is None:
            return
        is_active = tab_id == self._active_tab_id
        # زي برامج ويندوز العادية: يسأل بس لو فيه تعديل حقيقي عن آخر مستند
        # اتولّد فعلياً من هذا التبويب (أو آخر مستند سابق اتحمّل فيه) — لو
        # نفس الشي بالضبط (أو التبويب فاضٍ من الأصل)، يسكّر مباشرة بلا أي
        # سؤال. هذا مستقل عمداً عن _confirm()/CONFIRM_DIALOGS_ENABLED (بقية
        # تأكيدات البرنامج) — نستخدم confirm_always() (راجع ui/common/
        # alerts.py) اللي ما تحترم هذا التعطيل إطلاقاً، بطلب صريح — نطاق
        # هذا السلوك محصور بإغلاق التبويب بس.
        if self._tab_is_dirty(tab_id) and not confirm_always(
            "إغلاق التبويب",
            "فيه تعديلات بهذا التبويب ما تولّد منها مستند بعد.\n"
            "تريد تغلقه على أي حال؟\n"
            "(المعلومات المكتوبة تُحفظ وترجع أوتوماتيكياً لما تفتح البرنامج تاني،"
            " بس تحتاج تعيد توليد المستند منها).",
        ):
            return
        # نحفظ حالة كل التبويبات المفتوحة الآن (بما فيها هذا قبل ما
        # نشيله) كمسودة — يحمي بياناته بنفس مستوى حماية إغلاق البرنامج
        # بالضبط (بطلب صريح)، بدل ما تُمسح نهائياً بلا أي أثر.
        self.flush_draft_save()
        frame, _label_var = self._tab_buttons.pop(tab_id)
        frame.destroy()
        self._tabs = [t for t in self._tabs if t["id"] != tab_id]
        if is_active:
            self._active_tab_id = None  # حتى ما يحاول أي كود يحفظ حالة بتبويب متمسوح
            if self._tabs:
                self._activate_tab(self._tabs[-1]["id"])
            else:
                # بطلب صريح: يجوز تسكّر آخر تبويب متبقٍ فعلاً (بدل فتح بديل
                # فاضٍ أوتوماتيكياً زي قبل) — يبقى بس زر "+". نصفّي تاريخ
                # التراجع/الإعادة المشترك حتى ما يبقى يحمل بيانات التبويب
                # المسكور (Ctrl+Z ما لازم يشتغل بلا أي تبويب نشط أصلاً).
                self._reset_undo_history()
        self._refresh_tab_styles()
        self._update_no_tab_state()
        self._update_tab_scroll_arrows()
        self._update_next_button_state()
        # إغلاق تبويب "محمَّل" من حالة CD يغيّر حالة القفل بالشريط الجانبي
        # (الملف يرجع "شغل منتهي") — بدون هذا الاستدعاء، أيقونة 🔒 تبقى
        # قديمة بصرياً لحد أي refresh() ثاني بسبب فعل مختلف تماماً.
        self.explorer_panel.refresh()

    def _open_data_in_new_tab(
        self, data, source_row_id=None, source_file_path=None, source_pdf_path=None,
        source_client_id=None,
    ):
        """يفتح بيانات مستند (من السجل مثلاً) بتبويب جديد مستقل — ما يلمس
        أي تبويب مفتوح حالياً، نفس مبدأ فتح رابط بتبويب جديد بالمتصفح
        (بلا حاجة لأي تأكيد "بتفقد شغلك الحالي" — ما يفقد شي أصلاً).

        source_row_id/source_file_path/source_pdf_path (اختياري): هوية
        الحالة الأصلية بقاعدة البيانات وملفاتها — لو انعطت، أي حفظ لاحق
        بهذا التبويب بالذات **يحدّث فوقها** (يستبدل الملفين، نفس السطر)
        بدل ما يسجّل حالة جديدة مكرّرة (راجع _do_generate)."""
        self._new_tab()
        self._load_data_into_form(data)
        # زبون الحالة من سطر قاعدة البيانات نفسه (أدقّ من full_data_json —
        # مستند قديم رُبط بزبون لاحقاً عبر السجل تكون client_id بالسطر بس).
        if source_client_id is not None:
            self.client_picker.set_client_id(source_client_id)
        # هذا مستند موجود أصلاً (محمَّل من السجل) — "نظيف" من لحظة تحميله،
        # ✕ يسكّر بصمت طالما ما عدّلت فيه شي بعدها (راجع _tab_is_dirty).
        tab = self._tab_by_id(self._active_tab_id)
        if tab is not None:
            fields, date_val, time_val, delivrance_val = self._capture_state_from_widgets()
            tab["saved_snapshot"] = self._snapshot_of(fields, date_val, time_val, delivrance_val)
            if source_row_id is not None:
                tab["loaded_from"] = {
                    "row_id": source_row_id, "file_path": source_file_path,
                    "pdf_path": source_pdf_path, "client_id": source_client_id,
                }
            tab["client_id"] = source_client_id

    # ---------- طابور زبائن متتالٍ (⏭️ الزبون التالي / Ctrl+Shift+N) ----------
    def _update_next_button_state(self):
        """يفعّل/يعطّل زر ⏭️ الزبون التالي: يبقى معطّلاً على تبويب فاضٍ
        تماماً (ولا حتى حقل مكتب مشترك واحد معبّى) — ما فيه شي يُبنى
        عليه أصلاً بهالحالة (رقم البوردرو/التاريخ/الوقت/Tx de change
        كلها فاضية) — ويتفعّل بمجرد ما تتعبى أي بيانات (حقل مكتب مشترك،
        أو أي بيانات معاملة بالتبويب النشط)، بطلب صريح."""
        if self._active_tab_id is None:
            enabled = False
        else:
            office_filled = any((self._field_var(k).get() or "").strip() for k in OFFICE_FIELD_KEYS)
            enabled = office_filled or self._active_tab_has_data()
        self._next_client_btn.state(["!disabled" if enabled else "disabled"])

    def _next_client_tab(self):
        """⏭️ الزبون التالي (Ctrl+Shift+N): لطابور زبائن متتالٍ — تبويب
        جديد مستقل تماماً (زي "+")، لكن مبدوء ببيانات مبنية على التبويب
        النشط الحالي بدل فراغ تام:

        - رقم البوردرو: +1 (بنفس عدد الخانات، راجع _increment_dossier_no).
        - التاريخ: نفس تاريخ التبويب الحالي بالضبط.
        - الوقت: +4 إلى 7 دقائق عشوائي (راجع _advance_time_for_next_client).
        - Tx de change وDevise: نفس القيمة (خامس الأسطر الخمسة الأولى —
          الأربعة الباقية Agence/Guichet/Caisse/Guichetier أصلاً مشتركة
          تلقائياً بين كل التبويبات، راجع OFFICE_FIELD_KEYS، فما تحتاج
          أي نسخ إضافي هون).
        - الراكب، رقم الجواز، تاريخ الحصول، EUR وDZD: تفضى تماماً —
          زبون مختلف تماماً، بطلب صريح.

        الزر نفسه معطَّل أصلاً على تبويب فاضٍ تماماً (راجع
        _update_next_button_state)، فمافي داعي لأي فحص إضافي هون."""
        prev_no = self.no_var.get().strip()
        try:
            prev_date = self.date_entry.get_date()
        except ValueError:
            prev_date = None
        try:
            prev_time = self.time_entry.get_time_str()
        except ValueError:
            prev_time = ""
        prev_taux = self.taux_var.get().strip()
        prev_devise_code = self.devise_code_var.get().strip()
        prev_devise = self.devise_var.get().strip()

        self._new_tab()

        if prev_no:
            self.no_var.set(_increment_dossier_no(prev_no))
        if prev_date is not None:
            self.date_entry.set_date(prev_date)
        if prev_time:
            self.time_entry.set_time_str(_advance_time_for_next_client(prev_time))
        if prev_taux:
            self.taux_var.set(prev_taux)
        if prev_devise_code:
            self.devise_code_var.set(prev_devise_code)
        if prev_devise:
            self.devise_var.set(prev_devise)

        # المؤشر يبدأ مباشرة بحقل الراكب (الاسم) لا No — رغم إن _new_tab()
        # فوق حطّه بـNo (سلوك التبويب الفاضي العادي)، هون No معبّى أوتوماتيكياً
        # خلاص (+1)، فأول شي فعلاً فاضٍ ومحتاج كتابة هو الاسم. بطلب صريح.
        self.field_widgets["passager"].focus_set()

    # ---------- منطقة الصورة القابلة للتمرير ----------
    def _build_canvas_area(self):
        # PanedWindow أفقي بدل Frame عادي: يعطي خط فاصل قابل للسحب فعلياً
        # (Sash جاهز من Tk نفسه) لتوسيع/تصغير الشريط الجانبي يدوياً حسب
        # الحاجة، بدل عرضه الثابت القديم — بطلب صريح.
        self._paned = ttk.PanedWindow(self, orient="horizontal")
        self._paned.pack(fill="both", expand=True)

        # شريط الملفات الجانبي (يسار الشاشة) — قابل للإخفاء/الإظهار (راجع
        # _toggle_file_explorer)، حالته (ظاهر أو لا) تُتذكَّر بين الجلسات.
        # يُبنى دائماً هنا (بلا تكلفة تُذكر لو مخفياً — ما فيه ملفات كثيرة)
        # حتى ما نعيد بناءه من الصفر كل مرة تنضغط السهم. ملف مستقل تماماً
        # (ui/common/file_explorer.py) — مو خاص بـCD، قابل للتضمين بأي
        # شاشة ثانية لاحقاً بنفس السطرين.
        self.explorer_panel = FileExplorerPanel(
            self._paned, width=220,
            is_path_active=self._is_case_path_active,
            on_open_file=self._open_case_readonly,
            on_toggle_lock=self._toggle_lock_for_path,
        )

        holder_outer = tk.Frame(self._paned)
        # سهم صغير ملتصق بحافة الشريط (بدل زر منفصل بالشريط العلوي — راجع
        # _build_top_bar) — يفتح/يقفل الشريط بضغطة وحدة، ظاهر دائماً بغض
        # النظر عن حالة الشريط، بطلب صريح.
        collapse_bar = tk.Frame(holder_outer)
        collapse_bar.pack(side="left", fill="y")
        self._collapse_arrow_btn = ttk.Button(collapse_bar, width=2, command=self._toggle_file_explorer)
        self._collapse_arrow_btn.pack(side="top", pady=4)

        holder = tk.Frame(holder_outer)
        holder.pack(side="left", fill="both", expand=True)
        self._canvas_holder = holder

        self._paned.add(holder_outer, weight=1)
        if self._load_explorer_visibility():
            self._paned.insert(0, self.explorer_panel, weight=0)
        self._update_collapse_arrow()

        # شريط التبويبات هون بالذات — صف أول جوّا holder، فوق الـcanvas
        # مباشرة — بدل ما يكون شريط مستقل فوق الشاشة كلها (زي قبل). هيك
        # عرضه يتطابق تماماً مع عرض ورقة الاستمارة (يبدأ وينتهي بنفس
        # حدودها)، ظاهر أو مخفي الشريط الجانبي، بدل ما يمتد فوق الشريط
        # الجانبي كمان ويبان غير متناسق بصرياً (بطلب صريح راجعناه ونقلناه).
        self._build_tab_strip(holder)

        self.canvas = tk.Canvas(holder, bg="#c9c9c9", highlightthickness=0)
        vscroll = ttk.Scrollbar(holder, orient="vertical", command=self.canvas.yview)
        hscroll = ttk.Scrollbar(holder, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vscroll.set, xscrollcommand=hscroll.set)
        self.canvas.grid(row=1, column=0, sticky="nsew")
        vscroll.grid(row=1, column=1, sticky="ns")
        hscroll.grid(row=2, column=0, sticky="ew")
        holder.grid_rowconfigure(1, weight=1)
        holder.grid_columnconfigure(0, weight=1)

        self.loading_id = self.canvas.create_text(
            20, 20, anchor="nw", font=("Segoe UI", 12),
            text="⏳ جاري تجهيز الورقة...",
        )

        # تُظهَر بس لما ما يبقى أي تبويب مفتوح (سكّرت آخر واحد بـ✕) — تغطّي
        # الـcanvas بالذات بس (مو شريط التبويبات فوقها — لازم زر "+" يضل
        # قابل للضغط عادي حتى بصفر تبويبات) حتى ما تضل حقول قديمة ظاهرة/
        # قابلة للكتابة بلا أي تبويب يحفظها (راجع _update_no_tab_state).
        self._no_tab_placeholder = tk.Frame(holder, bg="#c9c9c9")
        ttk.Label(
            self._no_tab_placeholder,
            text="لا يوجد تبويب مفتوح\n\nاضغط \"+\" لبدء استمارة جديدة\nأو \"🕘 السجل\" لفتح مستند سابق",
            font=("Segoe UI", 13), justify="center", background="#c9c9c9",
        ).place(relx=0.5, rely=0.5, anchor="center")

    def _load_background(self):
        if self.bg_item_id is not None:
            return  # تحميل مسبق فعلاً، ما نكرره (يمنع صور/حقول مكررة)
        self.canvas.delete(self.loading_id)
        self.bg_item_id = self.canvas.create_image(0, 0, anchor="nw")
        self._build_fields()
        self._init_first_tab()
        self._apply_pending_draft_tabs()
        self.canvas.bind("<Configure>", lambda _e: self._relayout())
        # Ctrl + عجلة الفأرة للزوم (فوق=تكبير، تحت=تصغير)
        self.canvas.bind("<Control-MouseWheel>", self._on_ctrl_wheel)
        self._relayout()
        self._update_no_tab_state()
        self._update_next_button_state()

    # ---------- الزوم ----------
    # self.zoom هو مصدر الحقيقة الوحيد لمستوى التكبير (نسبة مئوية صحيحة
    # مباشرة، لا فهرس بقائمة) — set_zoom() هي نقطة الدخول المركزية
    # الوحيدة لتغييره، وكل طريقة زوم ثانية (الأزرار، عجلة الفأرة،
    # اختصارات الكيبورد، Fit to Window، تحميل التفضيل المحفوظ) تمر
    # منها. كل مستوى يُعاد رسمه من الصورة الأصلية بدقتها الحقيقية من
    # جديد (راجع _bg_image_for_pct أسفل و get_blank_background بـ
    # document.py) — بلا تكبير فوق تكبير وبلا أي تراكم أخطاء تقريب مهما
    # تكرر التكبير/التصغير ذهاباً وإياباً.
    def set_zoom(self, pct, anchor=None):
        """
        anchor (اختياري): tuple (widget_x, widget_y, frac_x, frac_y) من
        _zoom_anchor_from_event — نقطة بمساحة العمل ووقت الطلب، وموقعها
        النسبي (0..1) داخل صورة المستند. لو انعطت، بعد تطبيق الزوم
        الجديد نصحّح موضع التمرير حتى تبقى نفس النقطة قريبة من نفس مكان
        المؤشر (زوم حول المؤشر) بدل ما يقفز العرض فجأة لمكان ثاني.
        تُستخدم فقط من عجلة الفأرة (Ctrl+Wheel) — الأزرار والاختصارات
        تسيب موضع العرض كما هو (بلا معنى لمكان مؤشر بالكيبورد).
        """
        pct = max(ZOOM_MIN, min(ZOOM_MAX, round(pct)))
        if pct == self.zoom and anchor is None:
            return
        self.zoom = pct
        self._save_zoom_pref()
        self._relayout(anchor=anchor)

    def _step_zoom(self, direction, anchor=None):
        """يحسب المستوى المنطقي التالي/السابق بخطوات ثابتة (ZOOM_STEP)
        حتى لو الزوم الحالي مو على مضاعف الخطوة أصلاً (بعد Fit to Window
        مثلاً) — يقرّب للأعلى (تكبير) أو للأسفل (تصغير) لأقرب حد خطوة،
        مو يزيدها/ينقصها بشكل أعمى، حتى يضل تدرّج الزوم منطقياً ومتوقعاً
        دائماً بغض النظر من وين بدأنا."""
        if direction > 0:
            next_pct = ((self.zoom // ZOOM_STEP) + 1) * ZOOM_STEP
        else:
            next_pct = (math.ceil(self.zoom / ZOOM_STEP) - 1) * ZOOM_STEP
        self.set_zoom(next_pct, anchor=anchor)

    def zoom_in(self, anchor=None):
        self._step_zoom(1, anchor=anchor)

    def zoom_out(self, anchor=None):
        self._step_zoom(-1, anchor=anchor)

    def zoom_reset(self):
        """يرجّع الزوم لـ100% بضغطة وحدة (كليك على نسبة الزوم نفسها) —
        بدل الضغط المتكرر على "－"/"＋" للرجوع للحالة الطبيعية، بطلب صريح."""
        self.set_zoom(ZOOM_DEFAULT)

    def fit_to_window(self):
        """يحسب أقل نسبة زوم تخلي الورقة كاملة (عرضاً وطولاً معاً) ظاهرة
        داخل مساحة العمل المرئية حالياً بلا أي سكرول — بالاعتماد على
        أبعاد آخر صورة خلفية مرسومة فعلياً (self.current_bg_image، تحمل
        نفس نسبة عرض/طول المستند دائماً بغض النظر عن دقتها الحالية).
        فعل لمرة وحدة (يضبط self.zoom على القيمة الناتجة) — مو وضع دائم
        يتابع تغيّر حجم النافذة تلقائياً بعدها."""
        if self.current_bg_image is None:
            return
        avail_w = max(self.canvas.winfo_width() - 2 * CANVAS_MARGIN, 1)
        avail_h = max(self.canvas.winfo_height() - 2 * CANVAS_MARGIN, 1)
        aspect = self.current_bg_image.height() / self.current_bg_image.width()
        fit_w = min(avail_w, avail_h / aspect)
        self.set_zoom(fit_w / TARGET_W * 100)

    def _on_ctrl_wheel(self, event):
        anchor = self._zoom_anchor_from_event(event)
        if event.delta > 0:
            self.zoom_in(anchor=anchor)
        else:
            self.zoom_out(anchor=anchor)
        return "break"  # يمنع السكرول العادي وقت الزوم بـ Ctrl (العجلة العادية تبقى للسكرول فقط)

    def _zoom_anchor_from_event(self, event):
        """يحوّل موضع المؤشر وقت عجلة الزوم لنقطة نسبية (0..1) داخل صورة
        المستند الحالية + موضعه بالبكسل داخل self.canvas — يُستخدم بعدين
        (بعد ما يتغيّر الزوم فعلياً بـ_relayout) لتصحيح موضع التمرير حتى
        تضل نفس النقطة قريبة من نفس مكان المؤشر (زوم حول المؤشر)."""
        if self.current_bg_image is None:
            return None
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        img_w = self.current_bg_image.width()
        img_h = self.current_bg_image.height()
        if img_w <= 0 or img_h <= 0:
            return None
        frac_x = (cx - self._bg_ox) / img_w
        frac_y = (cy - self._bg_oy) / img_h
        return (event.x, event.y, frac_x, frac_y)

    def _apply_zoom_anchor(self, anchor, ox, oy, img_w, img_h, scroll_w, scroll_h):
        """يُستدعى من _relayout بعد ما تتحدّث كل الإحداثيات للزوم الجديد
        — يحرّك التمرير (لا أي عنصر) حتى تبقى نفس النقطة النسبية اللي
        كانت تحت المؤشر (راجع _zoom_anchor_from_event) بنفس مكان المؤشر
        تقريباً. أي خطأ حسابي (كنسبة خارج المدى بحافة الورقة) يُتجاهل
        بأمان — أسوأ حالة العرض يرجع للتوسيط الافتراضي، بلا كراش."""
        try:
            widget_x, widget_y, frac_x, frac_y = anchor
            new_cx = ox + frac_x * img_w
            new_cy = oy + frac_y * img_h
            target_left = new_cx - widget_x
            target_top = new_cy - widget_y
            if scroll_w > 0:
                self.canvas.xview_moveto(max(0.0, min(1.0, target_left / scroll_w)))
            if scroll_h > 0:
                self.canvas.yview_moveto(max(0.0, min(1.0, target_top / scroll_h)))
        except (TypeError, ValueError, ZeroDivisionError, tk.TclError):
            pass

    @staticmethod
    def _load_zoom_pref():
        """يرجّع مستوى الزوم المحفوظ من الجلسة السابقة (لو موجود ورقم
        صالح)، وإلا الافتراضي (100%) — تذكّر مستوى الزوم بين الجلسات
        بطلب صريح. القيمة المخزَّنة نسبة مئوية مباشرة (مو فهرس بقائمة)،
        تُقصّ لحدود الزوم الحالية احتياطاً (زوم محفوظ بجلسة قديمة بحدود
        مختلفة، أو ملف تُلوعب فيه يدوياً)."""
        prefs = _load_json(CD_UI_PREFS_PATH)
        pct = prefs.get("zoom_pct")
        if isinstance(pct, (int, float)) and not isinstance(pct, bool):
            return max(ZOOM_MIN, min(ZOOM_MAX, round(pct)))
        return ZOOM_DEFAULT

    def _save_zoom_pref(self):
        # نقرأ ونعدّل ونكتب (بدل استبدال الملف كامل) — حتى ما نمسح تفضيلات
        # ثانية مخزَّنة بنفس الملف (زي إظهار/إخفاء شريط الملفات تحت).
        prefs = _load_json(CD_UI_PREFS_PATH)
        prefs["zoom_pct"] = self.zoom
        _save_json(CD_UI_PREFS_PATH, prefs)

    def _current_zoom_pct(self):
        # يبقى للتوافق مع كود/اختبارات قديمة تناديها — self.zoom نفسه
        # هو المصدر الوحيد للحقيقة الآن (راجع شرح فوق).
        return self.zoom

    # ---------- شريط الملفات الجانبي (إظهار/إخفاء + تذكّره بين الجلسات) ----------
    @staticmethod
    def _load_explorer_visibility():
        # افتراضياً ظاهر (بطلب صريح) — يختفي بس لو المستخدم خبّاه بنفسه
        # يدوياً قبل هيك (عندها تُحفظ False صراحة بـ_save_explorer_visibility
        # وتُحترَم بكل فتح تالي).
        return bool(_load_json(CD_UI_PREFS_PATH).get("file_explorer_visible", True))

    def _save_explorer_visibility(self, visible):
        prefs = _load_json(CD_UI_PREFS_PATH)
        prefs["file_explorer_visible"] = visible
        _save_json(CD_UI_PREFS_PATH, prefs)

    def _is_case_path_active(self, path):
        """"شغل جارٍ" (True) لأي مسار (Word أو PDF) يخص تبويب مفتوح
        فعلاً الآن **وقابل للتعديل** (مو بوضع readonly) — والعكس: ملف
        تبويبه مسكّر، أو تبويبه مفتوح بس لسا بوضع "عرض فقط" (راجع
        set_form_readonly)، أو غير معروف إطلاقاً — يُعتبر "شغل منتهي"
        (False)، فيحصل حماية إضافية بالشريط الجانبي (تأكيد أوضح قبل
        نقل/حذف/إعادة تسمية، وأيقونة 🔒 قابلة للنقر لفتحه/فكّه — راجع
        is_path_active/on_toggle_lock بـui/common/file_explorer.py).
        يُمرَّر كدالة (callback) للشريط الجانبي عند بنائه — الشريط نفسه
        ما يعرف شي عن مفهوم "تبويبات"/"readonly" إطلاقاً، عام تماماً.

        الإصلاح المهم هنا: قبل كانت ترجّع True لمجرد وجود تبويب محمَّل
        من هالمسار، بغض النظر عن حالة القفل — يعني ملف تبويبه مفتوح بس
        لسا مقفول (لم يُفتح للتعديل بعد) كان يُعامَل خطأً كـ"شغل جارٍ"
        بلا أي حماية إضافية بالشريط، رغم إنه فعلياً محمي من التعديل
        بالضبط زي "شغل منتهي" لحد ما يُفتح صراحة."""
        try:
            abs_path = _norm_path(path)
        except (TypeError, ValueError):
            return True
        for tab in self._tabs:
            loaded_from = tab.get("loaded_from")
            if not loaded_from:
                continue
            for candidate in (loaded_from.get("file_path"), loaded_from.get("pdf_path")):
                if candidate and _norm_path(candidate) == abs_path:
                    return not tab.get("readonly", False)
        return False

    def _toggle_lock_for_path(self, path):
        """تُستدعى من الشريط الجانبي عند دبل كليك على أيقونة 🔒 تحديداً
        (راجع on_toggle_lock بـFileExplorerPanel) — تفتح/تفك التبويب
        المرتبط بهذا الملف بضغطة وحدة: لو تبويبه مفتوح أصلاً (بس لسا
        مقفول)، تفكّه مباشرة (نفس زر "🔓 فتح للتعديل" بالضبط، بلا أي
        تأكيد إضافي — بطلب صريح). لو "شغل منتهي" حقيقي (بلا تبويب مفتوح
        أصلاً)، تفتحه أولاً للقراءة فقط (نفس _open_case_readonly) ثم
        تفكّه مباشرة — فتح وفك بضغطة وحدة. refresh() بالنهاية يحدّث
        أيقونة الشريط 🔒↔🔓 فوراً (الودجت نفسه ما يعيد تقييم
        is_path_active إلا عند إعادة بناء الصف)."""
        try:
            abs_path = _norm_path(path)
        except (TypeError, ValueError):
            return
        for tab in self._tabs:
            loaded_from = tab.get("loaded_from")
            if loaded_from and any(
                candidate and _norm_path(candidate) == abs_path
                for candidate in (loaded_from.get("file_path"), loaded_from.get("pdf_path"))
            ):
                self._activate_tab(tab["id"])
                self.set_form_readonly(False)
                self.explorer_panel.refresh()
                return
        if self._open_case_readonly(path):
            self.set_form_readonly(False)
            self.explorer_panel.refresh()

    def _is_explorer_visible(self):
        return str(self.explorer_panel) in self._paned.panes()

    def _update_collapse_arrow(self):
        # "◀" لما الشريط ظاهر (يقفله)، "▶" لما مخفي (يفتحه) — نفس مبدأ
        # أسهم الطي بالبرامج المعروفة (VS Code وغيره).
        self._collapse_arrow_btn.configure(text="◀" if self._is_explorer_visible() else "▶")

    def _toggle_file_explorer(self):
        # PanedWindow (مو pack/pack_forget العادية — راجع _build_canvas_area)
        # حتى يبقى قابل للسحب لما يكون ظاهر، والسهم يحل محل زر "🗂️ الشريط
        # الجانبي" المحذوف (بطلب صريح).
        visible = self._is_explorer_visible()
        if visible:
            self._paned.forget(self.explorer_panel)
        else:
            self._paned.insert(0, self.explorer_panel, weight=0)
        self._save_explorer_visibility(not visible)
        self._update_collapse_arrow()

    def _bg_image_for_pct(self, pct, target_w):
        """
        يرجّع صورة الخلفية بدقة أصلية (مو مكبّرة من صورة أصغر، حتى تبقى
        الكتابة حادة دائماً). ترسم مباشرة ببايثون (فورية، بلا Word)، لكن
        نخزّنها بالذاكرة وعلى القرص بردو حتى ما نعيد رسمها كل مرة بلا داعي.
        """
        if pct in self._bg_photo_cache:
            return self._bg_photo_cache[pct]

        loading_id = self.canvas.create_text(
            20, 20, anchor="nw", font=("Segoe UI", 11),
            text=f"⏳ جاري تجهيز الورقة بدقة {pct}%...",
        )
        self.canvas.update_idletasks()
        try:
            bg_path = get_blank_background(target_w)
        except Exception as exc:  # noqa: BLE001
            self.canvas.delete(loading_id)
            alerts.error("خطأ", f"تعذر تجهيز الورقة بهالمستوى:\n{exc}")
            return None
        self.canvas.delete(loading_id)

        img = tk.PhotoImage(file=bg_path)
        self._bg_photo_cache[pct] = img
        return img

    def _set_widget_font(self, widget, font):
        # ودجت مركّبة بعدة خانات كتابة (زي SplitDateEntry) تعرّف .entries
        # (قائمة)؛ ودجت بخانة وحدة (MaskedDateEntry/MaskedTimeEntry) تعرّف
        # .entry (مفرد)؛ خانة عادية (tk.Entry) نطبّق عليها مباشرة.
        targets = getattr(widget, "entries", None) or [getattr(widget, "entry", widget)]
        for target in targets:
            try:
                target.configure(font=font)
            except tk.TclError:
                pass
        # ودجت زي SplitDateEntry فيها خانة (السنة) تتموضع حياً حسب طول
        # النص جوار جنبها — لازم نعيد حسابها بعد ما يتبدل حجم الخط بالزوم.
        reposition = getattr(widget, "reposition_year", None)
        if reposition is not None:
            reposition()

    # ---------- إعادة التوضّع: توسيط الورقة + تطبيق مستوى الزوم ----------
    def _relayout(self, anchor=None):
        if self.bg_item_id is None:
            return

        pct = self.zoom
        self.zoom_label.config(text=f"{pct}%")

        target_w = round(TARGET_W * pct / 100)
        bg_image = self._bg_image_for_pct(pct, target_w)
        if bg_image is None:
            return
        self.layout = field_layout_px(target_w)
        self.current_bg_image = bg_image  # لازم مرجع حتى ما تُمسح

        canvas_w = max(self.canvas.winfo_width(), 1)
        canvas_h = max(self.canvas.winfo_height(), 1)
        img_w, img_h = bg_image.width(), bg_image.height()
        ox = max((canvas_w - img_w) // 2, CANVAS_MARGIN)
        oy = max((canvas_h - img_h) // 2, CANVAS_MARGIN)
        self._bg_ox, self._bg_oy = ox, oy  # يستخدمها _zoom_anchor_from_event بالمرة الجاية

        self.canvas.itemconfigure(self.bg_item_id, image=bg_image)
        self.canvas.coords(self.bg_item_id, ox, oy)

        font_size = max(6, round(BASE_FONT_SIZE * pct / 100))
        scaled_font = ("Courier New", font_size)
        # لقياس أطول نص ممكن يدخل بخانات الكتابة الحقيقية بنفس الخط
        # المعروض حياً بالضبط — راجع شرح ENTRY_CHROME_PX واستخدامه تحت.
        measure_font = tkfont.Font(family="Courier New", size=font_size)

        for name, item_id in self.field_window_ids.items():
            x, y, w, h = self.layout[name]
            widget = self.field_widgets[name]
            if not self.field_natural_size[name]:
                if isinstance(widget, tk.Entry):
                    # خانات الكتابة الحقيقية (tk.Entry) بس — النصوص الحية
                    # (Label، زي انعكاس اسم الراكب أو Net a créditer) ما
                    # فيها نفس هامش Tk الداخلي، وما بلّغ عنها أي خلل.
                    #
                    # عرض الحقل بصيغة المستند (field_layout_px، أعلاه)
                    # مبني على حجم خط القسم الحقيقي بالمستند (10 أو 11)،
                    # بينما كل خانات الكتابة حياً على الشاشة تُرسم دائماً
                    # بـBASE_FONT_SIZE (10) موحّد — أحياناً يطابق حجم خط
                    # القسم، وأحياناً لأ (زي حقل No، بقسم خط 10 بالمستند
                    # لكن عرضه محسوب بنفس الصيغة أصلاً فتفاديناها بالقياس
                    # المباشر تحت بدل الافتراض). نضمن هنا مباشرة (نقيس، ما
                    # نخمّن) إنه الصندوق يتّسع لأطول نص ممكن يحتويه الحقل
                    # (حده الأقصى المعلن بـFIELD_LAYOUT) بالخط الحقيقي
                    # المرسوم + هامش Tk الثابت (ENTRY_CHROME_PX) — وإلا
                    # آخر حرف مكتوب يُقص بصرياً بالحقول الضيقة.
                    maxlen = FIELD_LAYOUT[name][2]
                    min_w = measure_font.measure("M" * maxlen) + ENTRY_CHROME_PX
                    if min_w > w:
                        # نوسّع من الجهة "الحرة" بس — يسار الحقول اليمينية
                        # (المبالغ، ملاصقة مباشرة لـ"EUR"/"DZD" بلا فاصل)،
                        # يمين باقي الحقول (نص عادي يسار) — حتى ما تنزاح
                        # الحافة الملاصقة لتسمية أو حقل تاني عن مكانها
                        # الحقيقي بالمستند.
                        if widget.cget("justify") == "right":
                            x -= min_w - w
                        w = min_w
                self.canvas.itemconfigure(item_id, width=w, height=h)
            self.canvas.coords(item_id, ox + x, oy + y)
            self._set_widget_font(widget, scaled_font)

        # حقل الوقت يتبع فعلياً حرف "a" (جزء من date_entry نفسه) بفاصل
        # مسافة واحدة، مقاسة بالبكسل الحقيقي من الودجت نفسه — بدل عمود
        # تجريدي ثابت قد يتصادم مع الشهر أثناء الكتابة الجزئية.
        date_x, date_y, _, _ = self.layout["date"]
        time_font = tkfont.Font(font=self.time_entry.entry.cget("font"))
        space_px = time_font.measure(" ")
        time_x = ox + date_x + self.date_entry.a_right_edge_px() + space_px
        time_y = oy + self.layout["time"][1]
        self.canvas.coords(self.field_window_ids["time"], time_x, time_y)

        scroll_w = max(img_w + 2 * ox, canvas_w)
        scroll_h = max(img_h + 2 * oy, canvas_h)
        self.canvas.configure(scrollregion=(0, 0, scroll_w, scroll_h))

        if anchor is not None:
            self._apply_zoom_anchor(anchor, ox, oy, img_w, img_h, scroll_w, scroll_h)

    # ---------- الحقول فوق الصورة ----------
    def _place(self, name, widget, natural_size=False):
        """
        natural_size=True: لا نفرض عرض/طول بالبكسل (نسيب الودجت تاخذ
        حجمها الطبيعي) — ضروري للودجت المركّبة (تاريخ/وقت) حتى ما ننقص
        عرضها ونقص آخر حرف مكتوب. الموضع الفعلي يتحدد بـ _relayout().
        """
        item_id = self.canvas.create_window(0, 0, window=widget, anchor="nw")
        self.field_widgets[name] = widget
        self.field_window_ids[name] = item_id
        self.field_natural_size[name] = natural_size

    def _maybe_year_complete(self):
        """بمجرد ما تكتمل السنة (4 أرقام)، ننتقل أوتوماتيكياً لخانة
        الوقت — نفس مبدأ اليوم/الشهر بالضبط."""
        if len(self.date_entry.year_var.get()) == 4:
            self.after_idle(self.time_entry.entry.focus_set)

    def _on_time_complete(self):
        """اكتمال الوقت أو Enter بحقله (<<TimeComplete>>): ينتقل مباشرة
        لحقل الراكب (الاسم)، متخطياً حقول المكتب — بطلب صريح."""
        self.field_widgets["passager"].focus_set()

    def _focus_no_field(self):
        """يحط المؤشر مباشرة بحقل No — بتبويب جديد فاضٍ (+ / Ctrl+T /
        فتح البرنامج لأول مرة)، وكمان بـ⏭️ الزبون التالي رغم إنو معبّى
        أوتوماتيكياً (للمراجعة السريعة)، بطلب صريح. مباشر (بلا
        after_idle) عمداً: يُستدعى دايماً من نهاية أمر زر/إعداد أولي
        (مو من وسط معالجة ضغطة مفتاح لسا Tk ما خلّص فيها زي اليوم/الشهر/
        السنة)، فما فيه داعي للتأجيل — والتأجيل هون فعلياً كان يسبب
        تعليق تركيز عشوائي التوقيت (لاحظناه بفشل متقطّع بعدة اختبارات
        عملية) لأن الاستدعاء المؤجَّل يقدر يوصل متأخر ويسرق التركيز من
        حقل تاني المستخدم/الاختبار خلاص انتقل له."""
        self.field_widgets["no"].focus_set()

    def _label_display(self, var, anchor="w"):
        """نص حي (Label) بدون كتابة مباشرة — يعكس متغيّر آخر تلقائياً.
        anchor="w" افتراضياً (محاذاة يسار، زي انعكاس اسم الراكب بسطر
        Guichet)؛ anchor="e" للحقول اللي لازم تظهر أقصى اليمين (زي
        Net a créditer، نفس محاذاة الأرقام بباقي حقول المبالغ)."""
        lbl = tk.Label(
            self.canvas, textvariable=var, font=("Courier New", BASE_FONT_SIZE), bg="white", anchor=anchor,
            highlightthickness=0,
        )
        return lbl

    def _build_fields(self):
        self.no_var = tk.StringVar()
        self.agence_no_var = tk.StringVar()
        self.agence_var = tk.StringVar()
        self.devise_code_var = tk.StringVar()
        self.devise_var = tk.StringVar()
        self.guichet_no_var = tk.StringVar()
        self.guichet_var = tk.StringVar()
        self.caisse_no_var = tk.StringVar()
        self.caisse_var = tk.StringVar()
        self.guichetier_var = tk.StringVar()
        self.passager_var = tk.StringVar()
        self.passport_var = tk.StringVar()
        self.taux_var = tk.StringVar()
        self.eur_var = tk.StringVar()
        self.dzd_var = tk.StringVar()
        self.net_crediter_var = tk.StringVar(value="")

        self._place("no", self._numeric_entry(self.no_var, FIELD_LAYOUT["no"][2]))

        self.date_entry = SplitDateEntry(self.canvas, default_today=False)
        self._place("date", self.date_entry, natural_size=True)
        self._add_hover(self.date_entry.day_entry, self.date_entry.day_var)
        self._add_hover(self.date_entry.month_entry, self.date_entry.month_var)
        self._add_hover(self.date_entry.year_entry, self.date_entry.year_var)
        # حرف "a" جزء داخلي من date_entry نفسه (سطر/جملة واحدة متماسكة مع
        # يوم/شهر/سنة) — لا حاجة لعنصر منفصل هنا، راجع SplitDateEntry.

        # حقل الوقت يتبع حياً نهاية حقل التاريخ (بعد حرف "a"): أي تغيير
        # باليوم/الشهر/السنة يعيد حساب مكانهما فوراً (زي ما يتحسبان بالضبط
        # بالمستند الحقيقي).
        for var in (self.date_entry.day_var, self.date_entry.month_var, self.date_entry.year_var):
            var.trace_add("write", lambda *a: self._relayout())
        self.time_entry = MaskedTimeEntry(self.canvas, default_now=False)
        self._place("time", self.time_entry, natural_size=True)
        self._add_hover(self.time_entry.entry, self.time_entry.var)
        # اكتمال الوقت (4 أرقام أثناء الكتابة) أو Enter كلاهما يطلقان
        # <<TimeComplete>> (راجع MaskedTimeEntry — ودجت عام ما يعرف شي
        # عن حقول CD) — الشاشة هنا هي اللي تقرر الوجهة: حقل الراكب
        # (الاسم) مباشرة (بطلب صريح)، متخطياً حقول المكتب لأنها غالباً
        # مُتذكَّرة/مشتركة مسبقاً (راجع _load_office_settings).
        self.time_entry.entry.bind("<<TimeComplete>>", lambda _e: self._on_time_complete())

        # لما تكتمل السنة (4 أرقام) ننتقل أوتوماتيكياً لخانة الوقت — نفس
        # مبدأ اليوم يكمل وينتقل للشهر، والشهر يكمل وينتقل للسنة. مؤجّل
        # بـafter_idle (زي انتقالات اليوم/الشهر بالضبط) حتى ما نغيّر
        # التركيز ونحن لسا وسط معالجة ضغطة الرقم نفسها.
        self.date_entry.year_var.trace_add("write", lambda *a: self._maybe_year_complete())

        # كل حقول النص العادية محدودة بعرضها المعلن بـFIELD_LAYOUT بالضبط
        # (لا أزيد ولا أنقص) — نفس مبدأ Guichet/N° Passport، حتى لو ما
        # كانت متبوعة بكتابة أخرى بنفس السطر (يمنع الكتابة تفيض عن حدود
        # المساحة الحقيقية المتاحة لها بالمستند المطبوع).
        # الأسطر الخمسة الأولى (Agence/Devise/Guichet/Caisse/Guichetier)
        # كلها بنفس النمط الموحّد: حقل أول 5 خانات، فراغ واحد ثابت، ثم
        # حقل ثاني 25 حرف (حروف كبيرة، أرقام، أو مسافة — أسماء وكالات/
        # وكلاء غالباً أكثر من كلمة، زي "TEST PASSAGER" بحقل الراكب) —
        # ما عدا Guichetier اللي حقل واحد بس (رقم 5 خانات، بلا حقل ثاني).
        # راجع الشرح المفصّل بـui/cd/document.py (FIRST_FIELD_WIDTH/
        # SECOND_FIELD_WIDTH وثوابت كل سطر).
        self._place("agence_no", self._numeric_entry(self.agence_no_var, FIELD_LAYOUT["agence_no"][2]))
        self._place(
            "agence", self._alnum_entry(self.agence_var, allow_space=True, maxlen=FIELD_LAYOUT["agence"][2]),
        )
        # Devise استثناء وحيد: حقله الأول حروف كبيرة بس (بلا أرقام) بدل أرقام.
        self._place(
            "devise_code",
            self._alnum_entry(self.devise_code_var, maxlen=FIELD_LAYOUT["devise_code"][2], allow_digits=False),
        )
        self._place(
            "devise", self._alnum_entry(self.devise_var, allow_space=True, maxlen=FIELD_LAYOUT["devise"][2]),
        )
        self._place("guichet_no", self._numeric_entry(self.guichet_no_var, FIELD_LAYOUT["guichet_no"][2]))
        self._place(
            "guichet", self._alnum_entry(self.guichet_var, allow_space=True, maxlen=FIELD_LAYOUT["guichet"][2]),
        )
        self._place("caisse_no", self._numeric_entry(self.caisse_no_var, FIELD_LAYOUT["caisse_no"][2]))
        self._place(
            "caisse", self._alnum_entry(self.caisse_var, allow_space=True, maxlen=FIELD_LAYOUT["caisse"][2]),
        )
        # Guichetier: رقم بس (5 خانات)، بلا حقل ثاني إطلاقاً.
        self._place("guichetier", self._numeric_entry(self.guichetier_var, FIELD_LAYOUT["guichetier"][2]))

        # انعكاس اسم الراكب بآخر سطر Guichet (نص حي، مو خانة كتابة)
        self.guichet_mirror_lbl = self._label_display(self.passager_var)
        self._place("guichet_mirror", self.guichet_mirror_lbl)

        # اسم الراكب: أرقام وحروف كبيرة بس (تُحوَّل تلقائياً)، مع مسافة
        # مسموحة (أسماء بكلمتين وأكثر)، ومحدود بعرضه المعلن بـFIELD_LAYOUT.
        self._place(
            "passager",
            self._alnum_entry(self.passager_var, allow_space=True, maxlen=FIELD_LAYOUT["passager"][2]),
        )
        # نفس مبدأ Guichet بالضبط: N° Passport يتبعه "Obtent." بنفس السطر.
        # نفس قيد الاسم (أرقام وحروف كبيرة بس، بلا مسافة) — أرقام الجواز
        # عادة مزيج أحرف وأرقام.
        self._place("passport_no", self._alnum_entry(self.passport_var, maxlen=FIELD_LAYOUT["passport_no"][2]))

        self.delivrance_entry = MaskedDateEntry(self.canvas, default_today=False)
        self._place("date_delivrance", self.delivrance_entry, natural_size=True)
        self._add_hover(self.delivrance_entry.entry, self.delivrance_entry.var)

        # حقلا المبلغ (EUR وDZD): تنسيق تلقائي بصيغة فرنسية (فاصل آلاف
        # "." + ",00" بالنهاية) عند الخروج منهما، بحد أقصى 999.999 —
        # راجع _currency_entry.
        self._place("eur", self._currency_entry(self.eur_var))
        # taux: نفس مبدأ EUR/DZD (صيغة فرنسية + تنسيق تلقائي عند الخروج)
        # بس 3 أرقام صحيحة كحد أقصى و7 أرقام عشرية بالضبط دائماً (بدل 2).
        self._place("taux", self._currency_entry(self.taux_var, max_value=TAUX_MAX_VALUE, decimals=TAUX_DEC_DIGITS))
        self._place("dzd", self._currency_entry(self.dzd_var))

        # Net a créditer: نص حي يعكس DZD (نفس القيمة دائماً لأن العمولات 0)
        self.net_crediter_lbl = self._label_display(self.net_crediter_var, anchor="e")
        self._place("net_crediter", self.net_crediter_lbl)

        # علاقة Taux/EUR/DZD: taux (Tx de change) ثابت لا يتغيّر إلا
        # بالكتابة اليدوية (راجع _recompute_dzd/_recompute_eur). تعديل
        # Montant en devise (EUR) أو Tx de change نفسه يضرب أوتوماتيكياً
        # في taux ويكتب النتيجة بـSoit (DZD). تعديل Soit يقسم أوتوماتيكياً
        # على taux ويكتب النتيجة بـMontant en devise. كل اتجاه مستقل
        # ومباشر (مو "آخر حقلين اتعدّلا") — بالضبط زي ما طلبت.
        self._triangle_vars = {"taux": self.taux_var, "eur": self.eur_var, "dzd": self.dzd_var}
        self._triangle_updating = False
        self.eur_var.trace_add("write", lambda *a: self._recompute_dzd())
        self.taux_var.trace_add("write", lambda *a: self._recompute_dzd())
        self.dzd_var.trace_add("write", lambda *a: self._recompute_eur())

        self.dzd_var.trace_add("write", lambda *a: self._update_net_crediter())

        # حقول المكتب الثابتة (Agence/Guichet/Caisse/Guichetier) تُتذكَّر
        # بين الجلسات — نفس الموظف/الشباك عادةً كل يوم، ما فيه داعي
        # تُكتب من الصفر كل مرة. تُحمَّل هنا، وتُحفظ تلقائياً كل تغيير.
        self._load_office_settings()
        for key in OFFICE_FIELD_KEYS:
            self._field_var(key).trace_add("write", lambda *a: self._save_office_settings())

        # مسودة العمل الجاري: استرجاع تلقائي لو البرنامج انقفل بالغلط
        # وسط التعبئة (بعد ما يسأل تأكيد)، وحفظ تلقائي بعدها لأي تعديل
        # على حقول المسودة (راجع DRAFT_FIELD_KEYS — التاريخ/الوقت مستثنيان).
        self._maybe_restore_draft()
        for key in DRAFT_FIELD_KEYS:
            self._field_var(key).trace_add("write", lambda *a: self._schedule_draft_save())

        # تراجع/إعادة: نفس نطاق حقول المسودة بالضبط (DRAFT_FIELD_KEYS —
        # التاريخ/الوقت مستثنيان لنفس السبب: تفضّل تكتبهما يدوياً دائماً،
        # واسترجاع حالتهما الداخلية أعقد وأخطر لو انحرف). الحالة البدائية
        # (بعد استرجاع الإعدادات/المسودة لو وُجدت) هي أول نقطة تراجع.
        self._last_committed_snapshot = self._snapshot()
        for key in _TRANSACTIONAL_DRAFT_KEYS:
            self._field_var(key).trace_add("write", lambda *a: self._maybe_checkpoint_undo())

        # عنوان التبويب النشط = رقم البوردرو (no)، يتحدّث حياً وأنت تكتب.
        self.no_var.trace_add("write", lambda *a: self._update_active_tab_label())

        # زر ⏭️ الزبون التالي يتفعّل/يتعطّل حياً حسب DRAFT_FIELD_KEYS (كل
        # حقول المكتب + المعاملة معاً) والتاريخ/الوقت (مستثنيان من
        # DRAFT_FIELD_KEYS لكن _active_tab_has_data تفحصهما أيضاً — راجع
        # _update_next_button_state).
        for key in DRAFT_FIELD_KEYS:
            self._field_var(key).trace_add("write", lambda *a: self._update_next_button_state())
        for var in (self.date_entry.day_var, self.date_entry.month_var, self.date_entry.year_var, self.time_entry.var):
            var.trace_add("write", lambda *a: self._update_next_button_state())

        self._bind_tab_switch_shortcuts()

    def _bind_tab_switch_shortcuts(self):
        """يربط Ctrl+Tab/Ctrl+Shift+Tab مباشرة على كل خانة كتابة حقيقية
        بالاستمارة (بلا استثناء) لتطلق حدثاً افتراضياً (<<CDTabNext/
        Prev>>) نستقبله بـbind_all (راجع __init__) — اكتشفنا تجريبياً إن
        الاعتماد على bind_all("<Control-Tab>") لوحده ما يكفي: كل خانات
        Tk (tk.Entry) عندها ربط داخلي جاهز من Tk نفسه (<Key-Tab>، على
        مستوى الصنف "Entry" لا خانة بعينها) يمسك أي ضغطة Tab حتى لو
        مصحوبة بـCtrl *قبل* ما توصل لـbind_all أصلاً — نفس مبدأ تصادم
        اليوم/الشهر بالضبط (SplitDateEntry، لهم نفس الحل مباشرة داخل
        صنفهم بـui/common/widgets.py)، بس هذا يشمل كل خانة بالاستمارة
        (لا اليوم/الشهر بس). bind_all("<Control-Tab>") بـ__init__ يبقى
        كخط دفاع ثاني لأي عنصر مو خانة كتابة (زر، الـcanvas نفسه...)."""
        def emit_next(event):
            event.widget.event_generate("<<CDTabNext>>")
            return "break"

        def emit_prev(event):
            event.widget.event_generate("<<CDTabPrev>>")
            return "break"

        for widget in self.field_widgets.values():
            targets = getattr(widget, "entries", None) or [getattr(widget, "entry", widget)]
            for entry in targets:
                if isinstance(entry, tk.Entry):
                    entry.bind("<Control-Tab>", emit_next)
                    entry.bind("<Control-Shift-Tab>", emit_prev)

    def _init_first_tab(self):
        """أول تبويب عند فتح الشاشة — فاضٍ بالبداية دائماً (أي مسودة
        مُسترجَعة تُطبَّق بعده مباشرة عبر _apply_pending_draft_tabs، مو
        هنا)، بس نلتقط حالة الودجت الحية بدل افتراض فراغها مباشرة —
        أبسط وأسلم من التمييز بين الحالتين."""
        tab_id = self._next_tab_id
        self._next_tab_id += 1
        fields, date_val, time_val, delivrance_val = self._capture_state_from_widgets()
        state = self._new_tab_state(tab_id)
        state["fields"] = fields
        state["date"] = date_val
        state["time"] = time_val
        state["date_delivrance"] = delivrance_val
        state["no"] = fields.get("no", "")
        state["last_committed"] = self._last_committed_snapshot
        self._tabs.append(state)
        frame, label_var = self._make_tab_widget(tab_id, self._tab_label_text(state["no"]))
        self._tab_buttons[tab_id] = (frame, label_var)
        self._active_tab_id = tab_id
        self._refresh_tab_styles()
        self._update_tab_scroll_arrows()
        self._focus_no_field()

    def _apply_pending_draft_tabs(self):
        """يطبّق مسودة اتسترجعت (بعد موافقة _maybe_restore_draft) على
        تبويبات فعلية — أول عنصر بالتبويب الأول (فاضٍ أصلاً وقت
        الاستدعاء)، وكل عنصر إضافي بتبويب جديد مستقل — حتى لو كانت
        المسودة لعدة تبويبات مفتوحة وقت الإغلاق غير المتوقع، كلها ترجع."""
        pending = self._pending_draft_tabs
        self._pending_draft_tabs = None
        if not pending:
            return
        first_entry, *rest = pending
        self._apply_draft_entry_to_active_tab(first_entry)
        for entry in rest:
            self._new_tab()
            self._apply_draft_entry_to_active_tab(entry)

    def _apply_draft_entry_to_active_tab(self, entry):
        self._apply_state_to_widgets(entry)
        tab = self._tab_by_id(self._active_tab_id)
        if tab is not None:
            tab["fields"] = entry["fields"]
            tab["date"] = entry["date"]
            tab["time"] = entry["time"]
            tab["date_delivrance"] = entry["date_delivrance"]
            tab["no"] = entry["fields"].get("no", "")
            tab["client_id"] = entry.get("client_id")
        self._reset_undo_history()  # حد "مستند مختلف" — نفس مبدأ _load_data_into_form

    def _update_active_tab_label(self):
        if self._active_tab_id is None:
            return
        _frame, label_var = self._tab_buttons.get(self._active_tab_id, (None, None))
        if label_var is not None:
            label_var.set(self._tab_label_text(self.no_var.get()))

    def _field_var(self, key):
        """يرجّع StringVar الحقل المطابق لاسمه — التفاف موحّد حتى الأماكن
        اللي تتعامل مع أسماء الحقول كنصوص (إعدادات المكتب، المسودة) ما
        تحتاج تعرف التفاصيل الداخلية (زي date_delivrance اللي متغيّره
        الحقيقي جوه delivrance_entry، أو passport_no اللي اسم متغيّره
        الفعلي passport_var مو passport_no_var)."""
        if key == "date_delivrance":
            return self.delivrance_entry.var
        if key == "passport_no":
            return self.passport_var
        return getattr(self, f"{key}_var")

    # ---------- إعدادات المكتب الثابتة (تُتذكَّر بين الجلسات) ----------
    def _load_office_settings(self):
        settings = _load_json(CD_SETTINGS_PATH)
        for key in OFFICE_FIELD_KEYS:
            value = settings.get(key)
            if value:
                self._field_var(key).set(value)

    def _save_office_settings(self):
        if self._suppress_office_settings_save:
            # موقوفة وقتياً وسط تحميل مستند قديم (_load_data_into_form) —
            # نعرض قيم Agence/Guichet/Caisse/Guichetier الحقيقية لذاك
            # المستند بالشاشة (دقّة/أمانة بالعرض)، بس بلا ما نخلي هذا
            # التحميل يبدّل إعدادات المكتب الدائمة (تمثّل شباكك اليوم، مو
            # الزبون المفتوح بهذا التبويب) — راجع الشرح المفصّل هناك.
            return
        _save_json(CD_SETTINGS_PATH, {key: self._field_var(key).get() for key in OFFICE_FIELD_KEYS})

    # ---------- مسودة العمل الجاري (استرجاع بعد إغلاق غير متوقع) ----------
    # تغطّي *كل* التبويبات المفتوحة وقت الحفظ (مو النشط بس) — خلل حقيقي
    # كان موجود: تبويب تغلقه بـ✕، أو تبويبات ثانية مفتوحة بالخلفية وقت
    # إغلاق البرنامج، كانت تُفقد نهائياً بلا أي أثر. الآن كل تبويب فيه
    # بيانات يُحفظ لحاله، ويرجع بتبويب مستقل بأول فتح تالي.
    def _capture_all_tabs_state(self):
        """يرجّع قائمة بحالة كل تبويب مفتوح حالياً — التبويب النشط من
        الودجت الحية مباشرة (أحدث حالة فعلية)، والباقي من آخر نسخة
        مخزَّنة له (تُحدَّث تلقائياً وقت كل تبديل تبويب، راجع _activate_tab)."""
        result = []
        for tab in self._tabs:
            if tab["id"] == self._active_tab_id:
                fields, date_val, time_val, delivrance_val = self._capture_state_from_widgets()
                result.append({
                    "fields": fields, "date": date_val, "time": time_val,
                    "date_delivrance": delivrance_val,
                    "client_id": self.client_picker.get_client_id(),
                })
            else:
                result.append({
                    "fields": tab["fields"], "date": tab["date"], "time": tab["time"],
                    "date_delivrance": tab["date_delivrance"],
                    "client_id": tab.get("client_id"),
                })
        return result

    def _maybe_restore_draft(self):
        draft = _load_json(CD_DRAFT_PATH)
        tab_drafts = draft.get("tabs") if isinstance(draft, dict) else None
        if not tab_drafts:
            return
        count = len(tab_drafts)
        tabs_desc = "تبويب واحد" if count == 1 else f"{count} تبويبات"
        restore = _confirm(
            "مسودة محفوظة",
            f"فيه عمل غير محفوظ من آخر مرة ({tabs_desc} — يبدو إنو البرنامج انقفل قبل ما تكمل).\n"
            "تريد نسترجعه؟",
        )
        if restore:
            # التطبيق الفعلي (فتح تبويبات) لازم يصير بعد ما تجهز البنية
            # التحتية للتبويبات — راجع _apply_pending_draft_tabs، تُستدعى
            # من _load_background بعد _init_first_tab مباشرة.
            self._pending_draft_tabs = [_deserialize_tab_draft(d) for d in tab_drafts]
        else:
            self._clear_draft()

    def _schedule_draft_save(self):
        # تأجيل بسيط (بدل حفظ فوري بكل ضغطة حرف) — يجمع عدة تعديلات
        # متتالية بحفظة وحدة، أخف على القرص بلا أي فرق ملموس للمستخدم.
        if self._draft_save_after_id is not None:
            self.after_cancel(self._draft_save_after_id)
        self._draft_save_after_id = self.after(800, self._save_draft_now)

    def _save_draft_now(self):
        self._draft_save_after_id = None
        all_states = self._capture_all_tabs_state()
        non_empty = [s for s in all_states if self._tab_state_has_data(s)]
        if non_empty:
            _save_json(CD_DRAFT_PATH, {"tabs": [_serialize_tab_draft(s) for s in non_empty]})
        else:
            self._clear_draft()

    def flush_draft_save(self):
        """يلغي أي حفظ مؤجَّل (Debounce بـ_schedule_draft_save) لو موجود،
        ثم يحفظ فوراً حالة كل التبويبات المفتوحة الآن — حتى لو ماكو حفظ
        مؤجَّل (نضمن المسودة تعكس الحقيقة دائماً وقت المغادرة). خلل حقيقي
        كان موجود: إغلاق النافذة أو التنقّل لشاشة ثانية قبل ما تمر 800ms
        من آخر ضغطة حرف كان يهدم الشاشة قبل ما يوصل المؤقّت يشتغل، فآخر
        تعديل يضيع بصمت. لازم يُستدعى قبل أي إغلاق/تنقّل بعيد عن CD
        (راجع clear_body/_on_close_request بـui/home/app_window.py)."""
        if self._draft_save_after_id is not None:
            self.after_cancel(self._draft_save_after_id)
            self._draft_save_after_id = None
        self._save_draft_now()

    def _clear_draft(self):
        try:
            os.remove(CD_DRAFT_PATH)
        except OSError:
            pass

    # ---------- تراجع/إعادة (Ctrl+Z / Ctrl+Y) ----------
    def _snapshot(self):
        """صورة كاملة لحقول *المعاملة* الحالية (نطاق _TRANSACTIONAL_DRAFT_KEYS
        — التاريخ/الوقت مستثنيان، راجع الشرح بمكان تعريفها). حقول المكتب
        (Agence/Guichet/Caisse/Guichetier) مستثناة عمداً من نطاق التراجع/
        الإعادة — عابرة للتبويبات (تمثّل الشباك الحالي، مو الزبون)، فما
        نريد Ctrl+Z بتبويب وحد يرجّعها لقيمة قديمة صارت تخص تبويب ثاني."""
        return {key: self._field_var(key).get() for key in _TRANSACTIONAL_DRAFT_KEYS}

    def _restore_snapshot(self, snapshot):
        # نمنع إعادة حساب المثلث (taux/eur/dzd) وسط الاسترجاع — ترتيب
        # استرجاع الحقول عشوائي (dict عادي)، فلو تُرك المثلث شغّال ممكن
        # يحسب Soit من eur الجديد + taux القديم (لسا ما وصل دوره)، فيطلع
        # رقم غلط قبل ما نوصل نضبط taux — نطبّق كل القيم أولاً كما هي
        # بالضبط، بلا أي حساب وسيط.
        self._triangle_updating = True
        try:
            for key, value in snapshot.items():
                self._field_var(key).set(value)
        finally:
            self._triangle_updating = False
        # نفس ملاحظة _currency_entry: var.set() يعطّل validate أوتوماتيكياً
        # — نرجّعه يدوياً لحقول المبالغ الثلاثة.
        for key in ("eur", "dzd", "taux"):
            self.field_widgets[key].configure(validate="key")

    def _undo(self):
        # حراسة إضافية لاختصار Ctrl+Z نفسه (زر "↶ تراجع" يتعطّل بصرياً
        # أصلاً بصفر تبويبات، لكن الاختصار يتجاوز حالة الزر المعطَّل).
        if self._active_tab_id is None:
            return
        # تبويب للقراءة فقط: var.set() (اللي يستخدمها _restore_snapshot)
        # يشتغل برمجياً بغض النظر عن حالة "readonly" بالودجت نفسها (هذي
        # تمنع الكتابة اليدوية بس) — لازم حراسة صريحة هون وإلا التراجع/
        # الإعادة يقدران يلتفّان على القفل ويعدّلان حالة "منتهية" بالغلط.
        if self._readonly_active:
            return
        if not self._undo_stack:
            return
        current = self._snapshot()
        self._redo_stack.append(current)
        previous = self._undo_stack.pop()
        self._restore_snapshot(previous)
        self._last_committed_snapshot = previous

    def _redo(self):
        if self._active_tab_id is None:
            return
        if self._readonly_active:
            return
        if not self._redo_stack:
            return
        current = self._snapshot()
        self._undo_stack.append(current)
        nxt = self._redo_stack.pop()
        self._restore_snapshot(nxt)
        self._last_committed_snapshot = nxt

    def _maybe_checkpoint_undo(self):
        # نتجاهل الكتابة الناتجة عن استرجاع تراجع/إعادة أو حساب المثلث
        # نفسه — بس التعديل الحقيقي (كتابة يدوية فعلية) يستاهل نقطة تراجع.
        if self._triangle_updating:
            return
        if self._undo_checkpoint_after_id is not None:
            self.after_cancel(self._undo_checkpoint_after_id)
        # تأجيل بسيط (زي حفظ المسودة بالضبط) — يجمع دفعة كتابة متتالية
        # بنقطة تراجع وحدة، بدل نقطة لكل حرف (مزعج وغير مفيد عملياً).
        self._undo_checkpoint_after_id = self.after(800, self._commit_undo_checkpoint)

    def _commit_undo_checkpoint(self):
        self._undo_checkpoint_after_id = None
        current = self._snapshot()
        if current == self._last_committed_snapshot:
            return
        self._undo_stack.append(self._last_committed_snapshot)
        self._redo_stack.clear()  # تعديل جديد بعد تراجع يُبطل تاريخ الإعادة (نفس عادة برامج الكتابة)
        self._last_committed_snapshot = current

    def _reset_undo_history(self):
        """يمسح تاريخ التراجع/الإعادة بالكامل ويثبّت الحالة الحالية كنقطة
        بداية جديدة — يُستدعى عند حدود "معاملة منتهية" (توليد مستند
        بنجاح، الضغط على "مستند جديد"، فتح تبويب جديد، أو تحميل مستند
        سابق من السجل) حتى Ctrl+Z ما يقدر يرجع لبيانات زبون سابق ويخلطها
        بالمعاملة الجارية."""
        self._undo_stack.clear()
        self._redo_stack.clear()
        if self._undo_checkpoint_after_id is not None:
            self.after_cancel(self._undo_checkpoint_after_id)
            self._undo_checkpoint_after_id = None
        self._last_committed_snapshot = self._snapshot()

    def _load_data_into_form(self, data):
        """يحمّل قاموس بيانات كامل (نفس شكل collect_data()) للاستمارة —
        يشمل التاريخ والوقت وتاريخ الحصول والمبالغ (بعكس _restore_snapshot
        المستخدمة للتراجع/الإعادة، اللي تستثني التاريخ/الوقت عمداً لأن
        استرجاع حالتهما الداخلية أعقد). يُستخدم لفتح مستند سابق من السجل
        بتبويب جديد (راجع _open_data_in_new_tab).

        نعرض قيم حقول المكتب (Agence/Guichet/Caisse/Guichetier) الحقيقية
        المسجَّلة بذاك المستند بالضبط (أمانة بالعرض — تشوف نفس الشي اللي
        كان وقت إنشائه)، لكن بلا ما نخلي هذا يبدّل إعدادات المكتب الدائمة
        (cd_settings.json — تمثّل شباكك اليوم، مو الزبون المفتوح بهذا
        التبويب): _suppress_office_settings_save يوقف الحفظ التلقائي
        وقتياً طول هذا التحميل بس."""
        text_keys = [
            k for k in DRAFT_FIELD_KEYS
            if k not in ("date_delivrance", "eur", "dzd", "taux")
        ]
        self._triangle_updating = True
        self._suppress_office_settings_save = True
        try:
            for key in text_keys:
                self._field_var(key).set(data.get(key) or "")
            for key, decimals in (("taux", TAUX_DEC_DIGITS), ("eur", 2), ("dzd", 2)):
                value = data.get(key)
                self._field_var(key).set(_fmt_amount(value, decimals) if value is not None else "")
        finally:
            self._triangle_updating = False
            self._suppress_office_settings_save = False
        for key in ("eur", "dzd", "taux"):
            self.field_widgets[key].configure(validate="key")
        self.date_entry.set_date(data.get("date"))
        self.time_entry.set_time_str(data.get("time"))
        self.delivrance_entry.set_date(data.get("date_delivrance"))
        # خانة الزبون (من full_data_json المحفوظ — collect_data صار يضمّها).
        self.client_picker.set_client_id(data.get("client_id"))
        self._reset_undo_history()  # حد "مستند مختلف تماماً" — راجع شرح _reset_undo_history

    def _active_tab_has_data(self):
        """True لو فيه أي بيانات مكتوبة (شخصية أو تاريخ/وقت) بالتبويب
        *النشط حالياً* (الودجت الحية) ما اتحفظت بمستند بعد. حقول المكتب
        الثابتة (Agence/Guichet/...) مستثناة عمداً — محفوظة أصلاً
        بإعداداتها الخاصة، تعبئتها وحدها مو "عمل جاري" يستاهل تنبيه."""
        for key in _TRANSACTIONAL_DRAFT_KEYS:
            if (self._field_var(key).get() or "").strip():
                return True
        d = self.date_entry
        if d.day_var.get() or d.month_var.get() or d.year_var.get():
            return True
        if self.time_entry.var.get():
            return True
        return False

    def has_unsaved_data(self):
        """True لو فيه أي بيانات مكتوبة ما اتحفظت بمستند بعد، **بأي تبويب
        مفتوح حالياً** (مو بس التبويب الظاهر أمامك) — تُستخدم قبل أي
        مغادرة تخسر أكثر من تبويب (رجوع، إغلاق البرنامج بالكامل)."""
        for tab in self._tabs:
            if tab["id"] == self._active_tab_id:
                if self._active_tab_has_data():
                    return True
            elif self._tab_state_has_data(tab):
                return True
        return False

    def has_unsaved_changes(self):
        """True لو فيه أي تبويب مفتوح حالياً (نشط أو لأ) فيه تعديل حقيقي
        ما تولّد منه مستند بعد (أو تغيّر عن آخر مستند تولّد منه) — نفس
        منطق _tab_is_dirty المستخدم أصلاً لـ✕ التبويب بالضبط، بس يفحص
        كل التبويبات المفتوحة معاً مو وحد بس. الفرق عن has_unsaved_data()
        أعلاه: هذي تفحص "فيه بيانات؟" بس (تُطلق تنبيه كاذب حتى بعد حفظ
        ناجح، طالما الحقول مو فاضية بعده) — has_unsaved_changes() تفحص
        "فيه شي فعلاً ما اتحفظ؟" الحقيقي. تُستخدم قبل أي مغادرة تخسر أكثر
        من تبويب دفعة وحدة (رجوع، إغلاق البرنامج بالكامل)."""
        return any(self._tab_is_dirty(tab["id"]) for tab in self._tabs)

    def _on_back(self):
        # بلا أي تحذير هنا (بعكس إغلاق التبويب ✕ أو إغلاق البرنامج
        # بالكامل — has_unsaved_changes() تبقى مستخدَمة هناك بلا أي
        # تغيير) — CD صارت تبويب خدمة حي يبقى مفتوحاً بالخلفية بكامل
        # حالته، فـEscape/الرجوع للرئيسية ما يخسر أي شي فعلياً، والتحذير
        # كان كاذباً (يوهم بخسارة بيانات ما تنخسر أصلاً).
        self.app.show_home()

    def _update_net_crediter(self):
        val = _safe_float_or_none(self.dzd_var.get())
        self.net_crediter_var.set(f"{val:,.2f}".translate(str.maketrans(",.", ".,")) if val is not None else "")

    def _recompute_dzd(self):
        """Montant en devise (EUR) أو Tx de change اتغيّرا -> Soit (DZD)
        = EUR × taux، أوتوماتيكياً. taux نفسه أبداً ما يتغيّر من هون."""
        if self._triangle_updating:
            return
        taux = _safe_float_or_none(self.taux_var.get())
        eur = _safe_float_or_none(self.eur_var.get())
        if taux is None or eur is None:
            return
        self._set_triangle_result("dzd", eur * taux)

    def _recompute_eur(self):
        """Soit (DZD) اتغيّر -> Montant en devise (EUR) = DZD ÷ taux،
        أوتوماتيكياً. taux نفسه أبداً ما يتغيّر من هون."""
        if self._triangle_updating:
            return
        taux = _safe_float_or_none(self.taux_var.get())
        dzd = _safe_float_or_none(self.dzd_var.get())
        if taux is None or dzd is None or taux == 0:
            return
        self._set_triangle_result("eur", dzd / taux)

    def _set_triangle_result(self, key, result):
        self._triangle_updating = True
        try:
            # eur/dzd المحسوبة أوتوماتيكياً تاخذ نفس التنسيق الفرنسي
            # اللي ياخذوه لما تُكتبان يدوياً (فاصل آلاف "." + فاصلة
            # عشرية "," برقمين عشريين).
            self._triangle_vars[key].set(f"{result:,.2f}".translate(str.maketrans(",.", ".,")))
            # نفس ملاحظة _currency_entry: تعديل النص برمجياً (var.set)
            # يعطّل validate أوتوماتيكياً — نرجّعه يدوياً.
            self.field_widgets[key].configure(validate="key")
        finally:
            self._triangle_updating = False

    # ---------- جمع البيانات وتوليد المستند ----------
    def collect_data(self):
        try:
            entry_date = self.date_entry.get_date()
        except ValueError:
            entry_date = None
        try:
            time_str = self.time_entry.get_time_str()
        except ValueError:
            time_str = ""
        try:
            delivrance_date = self.delivrance_entry.get_date()
        except ValueError:
            delivrance_date = None

        taux = _safe_float_or_none(self.taux_var.get())
        eur = _safe_float_or_none(self.eur_var.get())
        dzd = _safe_float_or_none(self.dzd_var.get())

        return {
            "no": self.no_var.get().strip(),
            "date": entry_date,
            "time": time_str,
            "client_id": self.client_picker.get_client_id(),
            "agence_no": self.agence_no_var.get().strip(),
            "agence": self.agence_var.get().strip(),
            "devise_code": self.devise_code_var.get().strip(),
            "devise": self.devise_var.get().strip(),
            "guichet_no": self.guichet_no_var.get().strip(),
            "guichet": self.guichet_var.get().strip(),
            "caisse_no": self.caisse_no_var.get().strip(),
            "caisse": self.caisse_var.get().strip(),
            "guichetier": self.guichetier_var.get().strip(),
            "passager": self.passager_var.get().strip(),
            "passport_no": self.passport_var.get().strip(),
            "date_delivrance": delivrance_date,
            "taux": taux,
            "eur": eur,
            "dzd": dzd,
        }

    # الحقول الأساسية اللي تحدّد هوية المستند — لو كلها أو بعضها فاضي،
    # ننبّه قبل التوليد بدل ما نطلع ملف Word رسمي فاضي بصمت (خطر حقيقي
    # على مستند عمل، مو مجرد تفصيل شكلي).
    _REQUIRED_FIELDS = [
        ("no", "رقم البوردرو (No)"),
        ("date", "التاريخ"),
        ("passager", "اسم الراكب"),
    ]

    def _do_generate(self, dest_dir=None):
        """يتحقق من الحقول الأساسية، يبني المستند (Word+PDF)، يسجّله
        بسجل CD (قابل للبحث لاحقاً من "🕘 السجل")، وينظّف مسودة العمل
        الجاري — نقطة مشتركة بين زر الحفظ وزر الطباعة، حتى ما يتكرر نفس
        المنطق. يرجّع مسار ملف Word، أو None لو انلغى أو صار خطأ.

        dest_dir (اختياري): مجلد محدَّد صراحة يستبدل به مكان الحفظ
        (زر "💾 حفظ في مكان آخر" — دايماً داخل travail بس، راجع
        _save_to_other_location) — بلا تمرير، يتبع القاعدة العادية:

        القاعدة العامة لتحديد "تحديث فوق حالة موجودة" مقابل "حالة جديدة":
        لو هذا التبويب بالذات جاي من حالة محمَّلة أصلاً (فتحتها للتعديل
        من السجل، أو حفظتها قبل هيك بنفس هذا التبويب) — أي حفظ منه الآن
        **يحدّث فوق نفس الملفين ونفس سطر قاعدة البيانات** (يستبدلهم، بغض
        النظر حتى لو تغيّر رقم البوردرو نفسه — القرار مربوط بهوية
        التبويب لا بالرقم). غير هيك (تبويب فاضٍ من الصفر) → حالة جديدة
        عادي (سطر وملفات جديدة)، ومن الآن فصاعداً هذا التبويب نفسه يصير
        "محمَّلاً" من الحالة اللي بس سجّلها، فأي حفظ تالٍ له يحدّث فوقها
        بنفس المبدأ."""
        if self._active_tab_id is None:
            # حراسة إضافية لاختصار Ctrl+P (زر "💾 حفظ"/"🖨️ طباعة" يتعطّل
            # بصرياً بصفر تبويبات، لكن الاختصار يتجاوز حالة الزر المعطَّل).
            return None
        if not hasattr(self, "layout"):
            alerts.warning("تنبيه", "الورقة لسا ما جهزت، انتظر لحظة وحاول مرة ثانية")
            return None

        # حفظ حالة محمَّلة أصلاً (loaded_from) **بلا أي تعديل حقيقي عنها**
        # = بلا أثر (زي برامج ويندوز العادية — "حفظ" على ملف ما تغيّر
        # فيه شي ما يسوي شي، بلا داعي للقلق منه). بلا هالفحص، "🖨️ طباعة"
        # كانت رح تعيد توليد الملفين من الصفر كل مرة حتى لو ما تغيّر شي —
        # هون نرجّع مسار الملفين الموجودين أصلاً بلا أي إعادة توليد
        # (الطباعة تكمل عادي من نفس PDF الموجود). "حفظ في مكان آخر"
        # (dest_dir) مستثنى عمداً — طلب صريح لعمل شي (نقل/نسخ لمكان
        # جديد) حتى لو المحتوى نفسه ما تغيّر.
        if dest_dir is None and self._tab_is_dirty(self._active_tab_id) is False:
            active_tab = self._tab_by_id(self._active_tab_id)
            loaded_from = active_tab.get("loaded_from") if active_tab is not None else None
            # تغيّر الزبون وحده لا يعلّم التبويب "قذر" (خانة الزبون مو ضمن
            # لقطة المقارنة عمداً — اختيارية دائماً)، لكنه **يستوجب حفظ
            # فعلي** لأنه يعني نقل الملفين (move_case، راجع تحت) — فما
            # نعتبره "بلا أثر" إلا لو الزبون كمان نفسه المخزَّن.
            if loaded_from and loaded_from.get("client_id") == self.client_picker.get_client_id():
                return loaded_from.get("file_path")

        data = self.collect_data()

        missing = [label for key, label in self._REQUIRED_FIELDS if not data.get(key)]
        if missing:
            proceed = _confirm(
                "تنبيه",
                "الحقول التالية فاضية أو غير صالحة:\n"
                + "\n".join(f"• {m}" for m in missing)
                + "\n\nتريد تكمل وتنشئ المستند مع هذا؟",
            )
            if not proceed:
                return None

        active_tab = self._tab_by_id(self._active_tab_id)
        loaded_from = active_tab.get("loaded_from") if active_tab is not None else None
        old_docx = loaded_from.get("file_path") if loaded_from else None
        old_pdf = loaded_from.get("pdf_path") if loaded_from else None

        target_client_id = data.get("client_id")
        existing_row_id = loaded_from.get("row_id") if loaded_from else None
        old_client_id = loaded_from.get("client_id") if loaded_from else None

        if dest_dir is not None:
            # "حفظ في مكان آخر": مكان جديد صراحة (يستبدل، مو نسخة إضافية
            # جنب القديم — راجع _save_to_other_location).
            docx_target = _named_path(dest_dir, data["passager"], "docx")
            pdf_target = _named_path(dest_dir, data["passager"], "pdf")
        elif old_docx:
            if target_client_id != old_client_id and existing_row_id is not None:
                # ⚠️ قرار تنفيذي (مرحلة 4.3): زبون التبويب تغيّر بعد أول
                # حفظ ناجح — ننقل الملفين فعلياً لمكانهم الجديد (مجلد
                # الزبون أو Autre/<شهر doc_date>) عبر عملية "نقل الحالة"
                # الموحّدة، بدل حساب مسار من الصفر يترك نسخة قديمة يتيمة ورا.
                try:
                    moved_docx, moved_pdf = move_case(existing_row_id, target_client_id)
                    docx_target = moved_docx or old_docx
                    pdf_target = moved_pdf or old_pdf
                except Exception:  # noqa: BLE001
                    docx_target, pdf_target = old_docx, old_pdf
            else:
                # تحديث فوق نفس الملفين بالضبط (نفس الاسم والمكان القديم).
                docx_target, pdf_target = old_docx, old_pdf
        elif target_client_id is not None:
            # أول حفظ وزبون معروف من البداية — الملف يروح **مباشرة** لمجلد
            # الزبون بلا مرور بـAutre أصلاً (راجع "الحفظ الفوري" بالبند 2
            # بمستند التصميم).
            client = get_client(target_client_id)
            if client is not None:
                client_dir = get_client_dir(client["folder_name"])
                docx_target = _named_path(client_dir, data["passager"], "docx")
                pdf_target = _named_path(client_dir, data["passager"], "pdf")
            else:
                docx_target = pdf_target = None
        else:
            docx_target = pdf_target = None  # تلقائي: travail/Autre/<شهر doc_date>


        try:
            path = generate_cd_document(data, out_path=docx_target)
        except Exception as exc:  # noqa: BLE001
            alerts.error("خطأ", f"تعذر إنشاء المستند:\n{exc}")
            return None

        # PDF دائم يتولّد مع كل حفظ حقيقي تلقائياً من الآن (بطلب صريح —
        # PDF هو "المنتج النهائي" المهم، Word نسخة خام للتعديل لاحقاً بس).
        # فشله ثانوي (زي فشل تسجيل السجل تحت): ما يوقف تسليم Word الفعلي،
        # لأنه أصلاً موجود ومحفوظ سليم.
        try:
            pdf_path = generate_cd_pdf(data, out_path=pdf_target)
        except Exception:  # noqa: BLE001
            pdf_path = None

        # لو "حفظ في مكان آخر" وفيه ملفات قديمة بمكان مختلف تماماً (حالة
        # محمَّلة أصلاً)، نمسحها — يستبدل، مو ينسخ زيادة (بطلب صريح).
        if dest_dir is not None:
            for old in (old_docx, old_pdf):
                if old and os.path.exists(old) and old not in (path, pdf_path):
                    try:
                        os.remove(old)
                    except OSError:
                        pass

        record = {
            "dossier_no": data["no"],
            "passager": data["passager"],
            "passport_no": data["passport_no"],
            "doc_date": data["date"].isoformat() if data["date"] else None,
            "agence": data["agence"],
            "guichet": data["guichet"],
            "eur_amount": data["eur"],
            "dzd_amount": data["dzd"],
            "file_path": path,
            "pdf_path": pdf_path,
            "client_id": target_client_id,
        }
        row_id = loaded_from.get("row_id") if loaded_from else None
        try:
            if row_id is not None:
                update_cd_document(row_id, record, full_data=data)
            else:
                row_id = log_cd_document(record, full_data=data)
        except Exception:  # noqa: BLE001
            logging.getLogger("officemanager").exception(
                "فشل تسجيل مستند CD بسجل قاعدة البيانات (file_path=%r, row_id=%r)",
                path, row_id,
            )
        else:
            if active_tab is not None and row_id is not None:
                # من الآن، هذا التبويب "محمَّل" من هذي الحالة بالذات — أي
                # حفظ تالٍ له (حتى لو غيّرت رقم البوردرو أو الزبون) يحدّث
                # فوقها. client_id المخزَّن هنا = مرجع المقارنة للحفظة
                # الجاية (تغيّر الزبون → move_case، راجع فوق).
                active_tab["loaded_from"] = {
                    "row_id": row_id, "file_path": path, "pdf_path": pdf_path,
                    "client_id": target_client_id,
                }

        # المعاملة كملت واتحفظت كمستند حقيقي — نعيد حساب المسودة بدل مسحها
        # بالكامل (self._clear_draft()) حتى ما نمسح بياناتها لو فيه
        # تبويبات ثانية مفتوحة بنفس الوقت لسا غير محفوظة (راجع _save_draft_now).
        self._save_draft_now()
        # نحدّث "آخر حالة معروفة كمستند فعلي" لهذا التبويب تحديداً بالحالة
        # الحالية بالضبط — من الآن، ✕ يسكّر هذا التبويب بصمت (بلا سؤال) طالما
        # ما تغيّر شي عنها (راجع _tab_is_dirty).
        if active_tab is not None:
            fields, date_val, time_val, delivrance_val = self._capture_state_from_widgets()
            active_tab["saved_snapshot"] = self._snapshot_of(fields, date_val, time_val, delivrance_val)
        self._session_docs.append(data)  # تراكم خام (راجع الشرح بـ__init__)
        self._reset_undo_history()  # حد "معاملة منتهية" — راجع شرح _reset_undo_history
        # الشريط الجانبي يقفز مباشرة للمستند اللي بس اتولّد ويحدّده — تشوف
        # نتيجة شغلك فوراً بلا أي بحث يدوي بمجلدات الأشهر (بطلب صريح).
        # refresh() أولاً حتى تنقرأ شجرة المجلد من جديد (الملف/مجلد الشهر
        # ممكن يكون جديد كلياً، مو موجود بالنسخة المخزَّنة بالشجرة أصلاً).
        # نحدّد PDF (المنتج النهائي المهم فعلياً، بطلب صريح) لو اتولّد
        # صح، وإلا نرجع لـWord (لو فشل توليد PDF لأي سبب — نادر).
        self.explorer_panel.refresh()
        self.explorer_panel.reveal_path(pdf_path or path)
        # نسخة احتياطية فورية بخيط منفصل (بلا تعليق الواجهة) — كل حفظ
        # حقيقي يستاهل حماية فورية، مو بس انتظار النسخة اليومية (راجع
        # backup.py). بلا أثر لو ماكو وجهات معدَّة بعد (قائمة فاضية).
        backup.run_backup_async()
        return path

    def generate_document(self):
        # حراسة إضافية (نفس نمط _undo/_redo بالضبط) — زر "💾 حفظ" يتعطّل
        # بصرياً أصلاً وقت readonly (راجع _update_readonly_guarded_buttons)،
        # لكن الاختصار المرتبط (زي Ctrl+داخل بعض السياقات) أو أي نداء
        # برمجي ثاني يقدر يتجاوز حالة الزر المعطَّل.
        if self._readonly_active:
            return
        # نتحقق *قبل* التوليد (اللي يحدّث الحالة نفسها) هل هذا الطلب
        # بلا أثر فعلياً (نفس شرط تجاوز _do_generate بالضبط: حالة محمَّلة
        # أصلاً بلا أي تعديل حقيقي) — حتى ما نفتح ملف قديم بلا داعي لمجرد
        # إنه "رجع نفس المسار"، بينما نفتحه عادي لأي حفظ حقيقي (حتى لو
        # تبويب فاضٍ وافقت على توليده رغم نقص الحقول).
        tab = self._tab_by_id(self._active_tab_id) if self._active_tab_id is not None else None
        is_noop = bool(
            tab and tab.get("loaded_from")
            and not self._tab_is_dirty(self._active_tab_id)
            and tab["loaded_from"].get("client_id") == self.client_picker.get_client_id()
        )
        path = self._do_generate()
        if path and not is_noop:
            open_path(path)

    def _save_to_other_location(self):
        """"💾 حفظ في مكان آخر": نفس الحفظ الرسمي بالضبط (نفس التحقق،
        نفس منطق تحديث/تسجيل جديد)، بس بمجلد تختاره أنت **داخل travail
        بس** بدل المجلد التلقائي — بطلب صريح (مرونة التنظيم، زي مجلد
        باسم زبون معيّن)، بلا أي وصول خارج travail (نفس قيد الشريط
        الجانبي بالضبط، لضمان الملف يبقى مرئي بالشريط ومحمي بالنسخ
        الاحتياطي التلقائي بغض النظر أي مجلد فرعي اخترته)."""
        # حراسة إضافية (نفس نمط _undo/_redo/generate_document بالضبط).
        if self._readonly_active:
            return
        travail_root = os.path.abspath(get_travail_root())
        chosen = filedialog.askdirectory(
            title="اختر مجلداً داخل travail لحفظ المستند فيه", initialdir=travail_root, parent=self,
        )
        if not chosen:
            return
        chosen_abs = os.path.abspath(chosen)
        try:
            same = os.path.commonpath([chosen_abs, travail_root]) == travail_root
        except ValueError:
            same = False  # مسارات بأقراص مختلفة مثلاً — أكيد مو داخل travail
        if not same:
            alerts.error("مكان غير مسموح", "لازم تختار مجلداً داخل travail بس.")
            return
        path = self._do_generate(dest_dir=chosen)
        if path:
            open_path(path)

    def _print_flow(self):
        """يولّد المستند (Word+PDF، نفس مسار زر الحفظ — يبقى دائماً
        السجل الرسمي المحفوظ)، ويطبع من **نفس نسخة PDF الدائمة** اللي
        بس اتولّدت (مو نسخة مؤقتة منفصلة زي قبل — بما إن كل حفظ يولّد
        PDF دائم فعلي الآن أصلاً، ما فيه داعي لنسخة إضافية مؤقتة تُحذف
        بعدها، راجع _do_generate)."""
        path = self._do_generate()
        if not path:
            return
        active_tab = self._tab_by_id(self._active_tab_id)
        loaded_from = active_tab.get("loaded_from") if active_tab is not None else None
        print_path = loaded_from.get("pdf_path") if loaded_from else None
        if not print_path or not os.path.exists(print_path):
            alerts.error("خطأ", "تعذر تجهيز نسخة الطباعة (PDF) — راجع خطأ الحفظ أعلاه لو ظهر.")
            return
        copies = simpledialog.askinteger(
            "طباعة", "عدد النسخ؟ (زي نسخة للزبون ونسخة للأرشيف)",
            initialvalue=1, minvalue=1, maxvalue=10, parent=self,
        )
        if not copies:
            return
        try:
            for _ in range(copies):
                os.startfile(print_path, "print")
        except OSError as exc:
            alerts.error("خطأ", f"تعذر إرسال الملف للطابعة:\n{exc}")

    def new_document(self):
        """يفضّي حقول المعاملة الحالية (رقم/تاريخ/راكب/جواز/مبالغ) بنفس
        التبويب الحالي لبدء مستند جديد فيه (بدون فتح تبويب إضافي — لهذا
        زر "+"/Ctrl+T)، ويُبقي حقول المكتب الثابتة (Agence/Guichet/Caisse/
        Guichetier) كما هي."""
        if self._active_tab_id is None:
            return
        # تبويب للقراءة فقط: نفس حراسة _undo/_redo بالضبط — var.set()
        # يشتغل برمجياً بغض النظر عن قفل الودجت، فلازم حراسة صريحة هون
        # وإلا هذا الزر يقدر يفضّي حالة "عمل منتهي" بالغلط رغم القفل.
        # زر "🔓 فتح للتعديل" بشريط التنبيه هو الطريق الصحيح لو فعلاً
        # يريد المستخدم التعديل (بلا حاجة لأي تأكيد إضافي هناك).
        if self._readonly_active:
            alerts.info("عرض فقط", "هذا عمل منتهي مفتوح للقراءة فقط.\nاضغط \"🔓 فتح للتعديل\" أولاً لو تريد التعديل.")
            return
        if self._tab_is_dirty(self._active_tab_id):
            proceed = _confirm(
                "تنبيه",
                "فيه بيانات مكتوبة ما اتحفظت بمستند بعد.\nتريد تفضّي الحقول وتبدأ مستند جديد؟",
            )
            if not proceed:
                return
        for key in _TRANSACTIONAL_DRAFT_KEYS:
            self._field_var(key).set("")
        self.date_entry.clear()
        self.time_entry.clear()
        self.client_picker.clear()  # معاملة جديدة = زبون جديد (يُختار من جديد)
        # نعيد حساب المسودة بدل مسحها بالكامل (self._clear_draft()) —
        # هذا التبويب صار فاضياً فعلاً (يُستثنى تلقائياً)، بس تبويبات
        # ثانية مفتوحة بنفس الوقت لازم تبقى محمية (راجع _save_draft_now).
        self._save_draft_now()
        # التبويب رجع فاضياً فعلاً — "نظيف" من جديد، ✕ يسكّره بصمت لو ما
        # كتبت فيه شي بعد (راجع _tab_is_dirty).
        tab = self._tab_by_id(self._active_tab_id)
        if tab is not None:
            empty_fields = {k: "" for k in _TRANSACTIONAL_DRAFT_KEYS}
            tab["saved_snapshot"] = self._snapshot_of(empty_fields, None, "", None)
        self._reset_undo_history()  # حد "معاملة جديدة" — راجع شرح _reset_undo_history

    # ملاحظة: "📁 فتح مجلد المستندات" انحذف (زر وطريقة) — الشريط الجانبي
    # يسوي نفس الوظيفة وأفضل (تصفّح + فتح بمستكشف ويندوز + كل عمليات
    # الملفات)، بطلب صريح تجنّباً للتكرار.

    def _show_shortcuts_help(self):
        alerts.info(
            "اختصارات لوحة المفاتيح",
            "Ctrl+T — تبويب جديد (زي كروم)\n"
            "Ctrl+W — إغلاق التبويب الحالي\n"
            "Ctrl+Tab / Ctrl+Shift+Tab — التبويب التالي/السابق\n"
            "Ctrl+P — توليد المستند وطباعته\n"
            "Ctrl+N — مستند جديد (بنفس التبويب)\n"
            "Ctrl+Shift+N — ⏭️ الزبون التالي (تبويب جديد لطابور متتالٍ:"
            " رقم البوردرو +1، نفس التاريخ، الوقت +4-7 دقائق عشوائي،"
            " نفس Tx de change/Devise)\n"
            "Ctrl+Z — تراجع\n"
            "Ctrl+Y (أو Ctrl+Shift+Z) — إعادة\n"
            "Ctrl + عجلة الفأرة — تكبير/تصغير حول موقع المؤشر\n"
            "Ctrl + (أو Ctrl =) — تكبير | Ctrl - — تصغير | Ctrl+0 — إرجاع لـ100%\n"
            "⤢ (بجانب نسبة الزوم) — ملاءمة الورقة كاملة بمساحة العرض\n"
            "حدود الزوم: 25% إلى 300%\n"
            "Esc — رجوع للرئيسية\n"
            "دبل-كليك بحقل مبلغ/تاريخ — تحديد قطعة وحيدة منه\n"
            "تريبل-كليك بأي حقل — تحديد الكل\n\n"
            "عنوان كل تبويب فوق = رقم البوردرو (No) المكتوب فيه. لما تكثر "
            "التبويبات وما تعود تتّسع، تظهر أسهم ◀/▶ للتمرير بينها وزر ▾ "
            "للقفز المباشر لأي وحد برقمه.",
        )

    # ---------- سجل المستندات السابقة ----------
    def open_history(self):
        CDHistoryWindow(self)

    def refresh(self):
        pass
