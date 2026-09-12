"""WorkKey/WorkSession — الهويّة والحالة الأساسية لعملٍ مفتوح (P1 §2/§3).

مفهومان صغيران متعمَّدان بالحدّ الأدنى — لا business logic، لا حفظ/طباعة/
إصدار حقيقيّ هنا. ``WorkspaceManager`` (في ``ui2.shell.workspace_manager``)
هو من يملك دورة الحياة؛ هذا الملف يعرّف فقط "ما هو العمل المفتوح".
"""
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Union

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget

from ui2.shell.commands import CommandId


@dataclass
class WorkCommandBinding:
    """ربط أمرٍ واحد (P2 §4) بعملٍ مفتوح — ``handler`` ينفَّذ عند
    التفعيل، ``enabled`` إمّا قيمة ثابتة أو دالّة تُقيَّم في كلّ refresh
    (لتعكس dirty/locked/أيّ حالة مستقبلية بلا إعادة تسجيل الربط).

    وجود ربطٍ لأمرٍ = **SUPPORTED** (يظهر دائماً في CommandBar، مفعَّلاً
    أو معطَّلاً حسب ``is_enabled()``). غياب الربط = **UNSUPPORTED** (لا
    يظهر إطلاقاً) — قرار UX ثابت (P2 §4)."""

    handler: Callable[[], None]
    enabled: Union[bool, Callable[[], bool]] = True

    def is_enabled(self) -> bool:
        if callable(self.enabled):
            return bool(self.enabled())
        return bool(self.enabled)


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
    #  ‏P2 §5: Hook عامّ — "حالة أوامري تغيّرت" — لا يقتصر على dirty/
    #  locked (يُصدَر تلقائياً معهما، ويمكن إصداره يدوياً لاحقاً لأيّ
    #  سببٍ آخر كـselection عبر notify_commands_changed()).
    commandsChanged = Signal()

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
        self._commands: Dict[CommandId, WorkCommandBinding] = {}
        #  ‏dirty/locked يؤثّران غالباً على enabled() لأوامر مثل SAVE/
        #  UNDO/REDO — إعادة تقييمٍ تلقائية بلا أن يعرف WorkSession شيئاً
        #  عن أيّ Command بعينه (P2 §5).
        self.dirtyChanged.connect(lambda _v: self.commandsChanged.emit())
        self.lockedChanged.connect(lambda _v: self.commandsChanged.emit())

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

    # ------------------------------------------------------------ Commands
    def set_command(self, command_id: CommandId, handler: Callable[[], None],
                     enabled: Union[bool, Callable[[], bool]] = True) -> None:
        """يُعلن أنّ هذا العمل يدعم ``command_id`` (P2 §4) — يظهر دائماً
        في CommandBar، مفعَّلاً أو معطَّلاً حسب ``enabled``. عدم استدعاء
        هذا لأمرٍ ما يعني عدم دعمه إطلاقاً (لا يظهر)."""
        self._commands[command_id] = WorkCommandBinding(handler, enabled)
        self.commandsChanged.emit()

    def supports(self, command_id: CommandId) -> bool:
        return command_id in self._commands

    def command_binding(self, command_id: CommandId) -> Optional[WorkCommandBinding]:
        return self._commands.get(command_id)

    def notify_commands_changed(self) -> None:
        """Hook عامّ صريح (P2 §5) لأيّ خدمةٍ مستقبلية تريد طلب إعادة
        تقييم enabled/visible لأسبابٍ غير dirty/locked (مثل تغيّر تحديد)."""
        self.commandsChanged.emit()
