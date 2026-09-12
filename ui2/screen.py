"""قاعدة شاشة عمل في ``ui2/`` — نظير ``ui/hr/base.py:HRDocScreen`` لكن
لـ PySide6، ومكتملة الآليات.

**الغرض:** شاشات HR و CD ستُرحَّل فوق هذه القاعدة. الواجهة مُصمَّمة لما
سيرث منها لاحقاً، لا لتقليص شاشة بعينها. (في الطبقة القديمة كانت دورة
حياة الاختصارات وحفظ المسوّدة في ``HRDocScreen`` مجرّد ``pass`` فارغة،
والتطبيق الحقيقي مكرَّراً في ``ui/cd/tab.py`` و``ui/hr/bulletin_paie.py``
— هنا مصدر واحد.)

تعطي الوارثَ:

* **هيكل موحّد**: شريط أدوات + ترويسة (اختيارية) + شريط تحذير + محتوى
  (يتمدّد) + شريط حالة.
* **دورة حياة الاختصارات** عبر :class:`ui2.shortcuts.ShortcutManager` —
  تُسجَّل في :meth:`on_activate`، تُلغى في :meth:`on_deactivate` (بروتوكول
  :class:`ui2.tabs.TabHost`). لا ``bind_all``.
* **حفظ المسوّدة المؤجَّل** (debounce 800ms) بنمط ``cd_draft.json``، مع
  **رقم إصدار** داخل الملف: مسوّدة بإصدار مختلف تُتجاهَل بصمت وتُمسَح —
  لا محاولة تفسير بنية قديمة.
* **تتبّع التغييرات غير المحفوظة** عبر :meth:`mark_dirty` /
  :meth:`mark_clean` — لا يعتمد على :meth:`is_empty` (شاشة فيها أسطر
  محفوظة ليست فارغة لكنها بلا تغييرات معلّقة).
* **سياق الزبون المشترك**: إشارة :attr:`companySelected`.
* **:meth:`on_close`** — خطّاف تنظيف قبل آخر :meth:`on_deactivate`.

الوارث يستدعي :meth:`build_ui` في نهاية ``__init__`` (بعد تهيئة حالته)،
ويعرّف :meth:`build_body` (إلزامي) وبقيّة الخطاطيف اختيارية.
"""
import json
import os
from typing import Callable, Dict, Optional

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from programme import paths
from ui2 import theme
from ui2.shortcuts import ShortcutManager
from ui2.toolbar import ToolBar

_DRAFT_DEBOUNCE_MS = 800


class Screen(QWidget):
    """قاعدة شاشة — انظر توثيق الوحدة."""

    # ----- تدهسها الشاشات الوارثة -----
    TITLE = "شاشة"
    DRAFT_NAME = ""            # "" → لا مسوّدة لهذه الشاشة
    DRAFT_VERSION = 1          # ارفعه عند أيّ تغيير في بنية draft_state()

    companySelected = Signal(object)          # client_id | None
    #  ‏P3 §9: أصغر إشارةٌ عامّة ممكنة لحالة dirty — أيّ مضيفٍ خارجي
    #  (Shell WorkSession لاحقاً) يستطيع الربط بها بلا معرفة تفاصيل
    #  الشاشة الوارثة. تُصدَر فقط عند تغيّرٍ فعليّ (لا استدعاءً مكرَّراً
    #  بنفس القيمة) — mark_dirty()/mark_clean() تحت تصدرها.
    dirtyChanged = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sc: Optional[ShortcutManager] = None
        self._dirty = False
        self._client_id = None
        self._built = False

        self._draft_timer = QTimer(self)
        self._draft_timer.setSingleShot(True)
        self._draft_timer.setInterval(_DRAFT_DEBOUNCE_MS)
        self._draft_timer.timeout.connect(self._save_draft_now)

        # عناصر الهيكل — تُجمَّع في build_ui() بعد أن يهيّئ الوارث حالته
        self.toolbar = ToolBar(self)
        self.warnbar = QLabel("")
        self.warnbar.setWordWrap(True)
        self.warnbar.setStyleSheet(
            f"background:{theme.FIELD_EMPTY}; color:{theme.WARNING}; "
            f"border:1px solid {theme.WARNING}; border-radius:4px; padding:6px;")
        self.warnbar.hide()
        self.status = QLabel("")
        self.status.setStyleSheet(f"color:{theme.TEXT_DIM};")

    # ============================ بناء الهيكل ============================
    def build_ui(self) -> None:
        """يبني تخطيط الشاشة ويستدعي خطاطيف الوارث. يُستدعى مرّة واحدة من
        ``__init__`` الوارث بعد تهيئة حالته."""
        if self._built:
            return
        self._built = True
        lay = QVBoxLayout(self)
        lay.addWidget(self.toolbar)
        self.build_toolbar(self.toolbar)
        header = self.build_header()
        if header is not None:
            lay.addWidget(header)
        lay.addWidget(self.warnbar)
        lay.addWidget(self.build_body(), 1)
        lay.addWidget(self.status)

    # ===================== خطاطيف الوارث (اختيارية عدا build_body) =====================
    def build_toolbar(self, toolbar: ToolBar) -> None:
        """أضِف أفعال شريط الأدوات. افتراضياً: لا شيء."""

    def build_header(self) -> Optional[QWidget]:
        """ودجت الترويسة (الزبون/العامل/الفترة…) أو ``None``."""
        return None

    def build_body(self) -> QWidget:
        """المحتوى الرئيسي — إلزامي."""
        raise NotImplementedError

    def shortcuts(self) -> Dict[str, Callable[[], None]]:
        """``{«تسلسل مفاتيح»: دالة}`` — تُسجَّل عند التفعيل وتُلغى عند المغادرة."""
        return {}

    def draft_state(self) -> Optional[dict]:
        """حالة قابلة للتسلسل JSON تُحفظ كمسوّدة، أو ``None`` (لا شيء الآن)."""
        return None

    def apply_draft(self, data: dict) -> None:
        """يطبّق مسوّدة مستعادة (نفس شكل :meth:`draft_state`)."""

    def is_empty(self) -> bool:
        """للمسوّدة فقط: ``True`` → لا تُكتب مسوّدة، وتُمسَح الموجودة.
        **ليست** معيار :meth:`has_unsaved_changes`."""
        return True

    def on_close(self) -> None:
        """تنظيف قبل آخر :meth:`on_deactivate` (إغلاق تبويب/نافذة).
        افتراضياً: لا شيء."""

    # ===================== التغييرات غير المحفوظة =====================
    def mark_dirty(self) -> None:
        """يستدعيها الوارث عند كل تعديل حقيقي من المستخدم."""
        changed = not self._dirty
        self._dirty = True
        self.schedule_draft_save()
        if changed:
            self.dirtyChanged.emit(True)

    def mark_clean(self) -> None:
        """بعد حفظ ناجح (أو استمارة جديدة): يُصفّر العلَم ويمسح المسوّدة."""
        changed = self._dirty
        self._dirty = False
        self.clear_draft()
        if changed:
            self.dirtyChanged.emit(False)

    def has_unsaved_changes(self) -> bool:
        return self._dirty

    # =========================== دورة الحياة ===========================
    def on_activate(self) -> None:
        """صار التبويب نشطاً: سجِّل الاختصارات."""
        if self._sc is None:
            self._sc = ShortcutManager(self)
            self._sc.register_many(self.shortcuts())

    def on_deactivate(self) -> None:
        """غادر التبويب: ألغِ الاختصارات واحفظ المسوّدة فوراً."""
        if self._sc is not None:
            self._sc.unregister_all()
            self._sc = None
        self.flush_draft()

    def close_screen(self) -> None:
        """إغلاق نهائي يستدعيه المضيف قبل التدمير: :meth:`on_close` ثم
        :meth:`on_deactivate` أخيرة."""
        self.on_close()
        self.on_deactivate()

    # ----- توافق مع أسماء ui/home/app_window (إن استُضيفت بجانب شاشات ui/) -----
    def activate_shortcuts(self) -> None:
        self.on_activate()

    def deactivate_shortcuts(self) -> None:
        if self._sc is not None:
            self._sc.unregister_all()
            self._sc = None

    def flush_draft_save(self) -> None:
        self.flush_draft()

    # ============================== المسوّدة ==============================
    def _draft_path(self) -> Optional[str]:
        if not self.DRAFT_NAME:
            return None
        return os.path.join(paths.get_local_state_dir(),
                            f"{self.DRAFT_NAME}_draft.json")

    def schedule_draft_save(self) -> None:
        """يؤجّل حفظ المسوّدة (يجمع عدّة تعديلات متتالية في كتابة واحدة)."""
        if self.DRAFT_NAME:
            self._draft_timer.start()

    def _save_draft_now(self) -> None:
        path = self._draft_path()
        if path is None:
            return
        state = self.draft_state()
        if state is None or self.is_empty():
            self.clear_draft()
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"draft_version": self.DRAFT_VERSION, "state": state},
                          fh, ensure_ascii=False)
        except OSError:
            pass

    def flush_draft(self) -> None:
        """يلغي أيّ حفظ مؤجَّل ثم يحفظ فوراً — يُستدعى قبل أيّ إغلاق/تنقّل."""
        if self._draft_timer.isActive():
            self._draft_timer.stop()
        self._save_draft_now()

    def load_draft(self) -> Optional[dict]:
        """يقرأ المسوّدة إن وُجدت وكانت **بنفس الإصدار**. إصدار مختلف أو
        ملف تالف → يُمسَح ويُرجَع ``None`` (لا محاولة تفسير بنية قديمة)."""
        path = self._draft_path()
        if path is None or not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8") as fh:
                blob = json.load(fh)
        except (OSError, ValueError):
            self.clear_draft()
            return None
        if (not isinstance(blob, dict)
                or blob.get("draft_version") != self.DRAFT_VERSION):
            self.clear_draft()
            return None
        return blob.get("state")

    def maybe_restore_draft(self, ask: Callable[[], bool]) -> bool:
        """إن وُجدت مسوّدة صالحة: ينادي ``ask()`` — ``True`` →
        :meth:`apply_draft` وإرجاع ``True``؛ ``False`` → تُمسَح وإرجاع
        ``False``. لا مسوّدة → ``False`` بلا نداء ``ask``."""
        state = self.load_draft()
        if state is None:
            return False
        if ask():
            self.apply_draft(state)
            self._dirty = True
            return True
        self.clear_draft()
        return False

    def clear_draft(self) -> None:
        path = self._draft_path()
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass

    # ============================ سياق الزبون ============================
    def set_company(self, client_id) -> None:
        """يضبط الزبون النشط ويبثّ :attr:`companySelected` (شاشات أخرى في
        نفس المضيف تستمع)."""
        self._client_id = client_id
        self.companySelected.emit(client_id)

    @property
    def client_id(self):
        return self._client_id
