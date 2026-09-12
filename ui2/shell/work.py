"""WorkKey/WorkSession — الهويّة والحالة الأساسية لعملٍ مفتوح (P1 §2/§3).

مفهومان صغيران متعمَّدان بالحدّ الأدنى — لا business logic، لا حفظ/طباعة/
إصدار حقيقيّ هنا. ``WorkspaceManager`` (في ``ui2.shell.workspace_manager``)
هو من يملك دورة الحياة؛ هذا الملف يعرّف فقط "ما هو العمل المفتوح".
"""
from dataclasses import dataclass
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget


@dataclass(frozen=True)
class WorkKey:
    """هويّة عملٍ مفتوح — ثابتة/قابلة للتجزئة، تُستعمَل لمنع فتح نفس
    العمل مرّتين (P1 §2/§5). مثال: ``WorkKey("paie", "918")``.

    ‏``work_id`` مؤقّتٌ لأعمالٍ جديدة غير محفوظة (لا يُنفَّذ هذا التدفّق
    الآن — راجع §16) أو معرِّف Work حقيقيّ لاحقاً؛ لا علاقة له بقاعدة
    البيانات هنا إطلاقاً."""

    service_key: str
    work_id: str


class WorkSession(QObject):
    """تمثيلٌ صغير لعملٍ مفتوح داخل Shell — هويّة + عنوان + محتوى +
    حالتا dirty/locked، مع إشاراتٍ عند تغيّر أيٍّ منها لتحديث WorkTabBar
    فوراً (P1 §3/§9). لا تحمل منطق حفظ/طباعة/إصدار — ``can_close``
    Hookٌ اختياريّ فارغ الآن (``None``) يسمح لاحقاً بحوار حفظ/تجاهل/
    إلغاء بلا إعادة كتابة ``WorkspaceManager`` (P1 §10)."""

    titleChanged = Signal(str)
    dirtyChanged = Signal(bool)
    lockedChanged = Signal(bool)

    def __init__(self, key: WorkKey, title: str, widget: QWidget, *,
                 dirty: bool = False, locked: bool = False,
                 can_close: Optional[Callable[[], bool]] = None,
                 parent=None):
        super().__init__(parent)
        self.key = key
        self.widget = widget
        #  ‏Hook مستقبليّ فقط (P1 §10): ``None`` الآن يعني "قابلٌ للإغلاق
        #  دائماً". خدمةٌ حقيقية لاحقاً قد تمرّر دالّةً تُرجع False لفتح
        #  حوار حفظ/تجاهل/إلغاء قبل الإغلاق — بلا تغيير هذا الصنف.
        self.can_close = can_close
        self._title = title
        self._dirty = bool(dirty)
        self._locked = bool(locked)

    @property
    def title(self) -> str:
        return self._title

    def set_title(self, value: str) -> None:
        value = str(value or "")
        if value != self._title:
            self._title = value
            self.titleChanged.emit(value)

    @property
    def dirty(self) -> bool:
        return self._dirty

    def set_dirty(self, value: bool) -> None:
        value = bool(value)
        if value != self._dirty:
            self._dirty = value
            self.dirtyChanged.emit(value)

    @property
    def locked(self) -> bool:
        return self._locked

    def set_locked(self, value: bool) -> None:
        value = bool(value)
        if value != self._locked:
            self._locked = value
            self.lockedChanged.emit(value)

    def display_text(self) -> str:
        """نصّ التبويب — العنوان + مؤشّرٌ صغير لا يدخل الهويّة (P1 §9):
        🔒 للقفل، وإلا ● للتعديل غير المحفوظ، وإلا العنوان وحده."""
        if self._locked:
            return f"{self._title} 🔒"
        if self._dirty:
            return f"{self._title} ●"
        return self._title
