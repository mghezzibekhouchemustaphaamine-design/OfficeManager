"""WorkspaceManager — دورة حياة/حالة الأعمال المفتوحة (P1 §4).

**فصلٌ متعمَّد**: ``WorkTabBar`` (في ``ui2.shell.workspace``) عرضٌ بصريّ
بحت — لا يعرف شيئاً عن ``WorkSession``. هذا الصنف وحده مصدر الحقيقة:
من مفتوح، ما الترتيب، من النشِط. ``WorkspaceHost`` يستمع لإشاراته
ويعكسها على QTabBar/ContentStack — لا يُخزَّن أيّ شيءٍ في QTabBar نفسه
(راجع §8: التطابق Tab↔Work بمفتاحٍ صريح، لا عنوان).

لا قاعدة بيانات، لا WorkItem حقيقيّ، لا Service Contract هنا — إدارة
عمليّة الأعمال المفتوحة داخل هذه الجلسة فقط."""
from typing import Dict, List, Optional

from PySide6.QtCore import QObject, Signal

from ui2.shell.work import WorkKey, WorkSession


class WorkspaceManager(QObject):
    """يوفّر: ``open_work``/``activate_work``/``close_work``/``is_open``/
    ``active_work``/``open_works``. يُصدر إشاراتٍ عند كلّ تغيّر ليعكسها
    المستهلك (``WorkspaceHost``) على الواجهة — لا يلمس أيّ Widget UI
    (‏QTabBar/ContentStack) بنفسه."""

    #  ‏WorkSession جديدة انضمّت للسجلّ (بعد التحقّق من عدم التكرار).
    opened = Signal(object)                    # WorkSession
    #  العمل النشِط تغيّر — ``None`` يعني "لا عمل نشِط" (Home/ServiceStartView).
    activated = Signal(object)                 # Optional[WorkKey]
    #  عملٌ أُغلق وأُزيل من السجلّ نهائياً — الجلسة كاملةً (لا المفتاح
    #  وحده) ليتمكّن المستهلك (WorkspaceHost) من التخلّص من widget-ها.
    closed = Signal(object)                    # WorkSession
    #  تحديثاتٌ حيّة من WorkSession.title/dirty/locked — مع مفتاح
    #  صاحبها (لا اعتماد على تطابق نصّيّ، P1 §8/§9).
    titleChanged = Signal(object, str)         # WorkKey, str
    dirtyChanged = Signal(object, bool)        # WorkKey, bool
    lockedChanged = Signal(object, bool)       # WorkKey, bool
    #  ‏P2 §5: WorkSession.commandsChanged مُعاد إصدارها مع مفتاح
    #  صاحبها — CommandManager يستمع لها ليعيد تقييم visible/enabled.
    commandsChanged = Signal(object)           # WorkKey
    #  ‏P2 (Drag & Drop): ترتيب الأعمال المفتوحة تغيّر (سحب Tab) — لا
    #  يغيّر العمل النشِط ولا الهويّة/الـwidget، فقط الموضع في open_works().
    reordered = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sessions: Dict[WorkKey, WorkSession] = {}
        self._order: List[WorkKey] = []        # ترتيب الفتح — LEFT→RIGHT (P1 §1)
        self._active_key: Optional[WorkKey] = None

    # ------------------------------------------------------------- الاستعلام
    def is_open(self, key: WorkKey) -> bool:
        return key in self._sessions

    def active_work(self) -> Optional[WorkSession]:
        return self._sessions.get(self._active_key) if self._active_key else None

    def active_key(self) -> Optional[WorkKey]:
        return self._active_key

    def open_works(self) -> List[WorkSession]:
        """كلّ الأعمال المفتوحة، بترتيب الفتح الفعليّ (يطابق ترتيب
        Tabs من اليسار لليمين — P1 §1)."""
        return [self._sessions[k] for k in self._order]

    def get(self, key: WorkKey) -> Optional[WorkSession]:
        return self._sessions.get(key)

    # -------------------------------------------------------------- العمليات
    def open_work(self, session: WorkSession) -> WorkSession:
        """يفتح ``session`` وينشِّطها. إن كان مفتاحها مفتوحاً بالفعل —
        **لا Tab ثانية ولا Widget ثانية** (P1 §5): تُنشَّط الجلسة
        الموجودة فعلياً بدل إنشاء أخرى، والجلسة المُمرَّرة تُهمَل."""
        existing = self._sessions.get(session.key)
        if existing is not None:
            self.activate_work(session.key)
            return existing

        self._sessions[session.key] = session
        self._order.append(session.key)
        key = session.key
        session.titleChanged.connect(lambda t, k=key: self.titleChanged.emit(k, t))
        session.dirtyChanged.connect(lambda d, k=key: self.dirtyChanged.emit(k, d))
        session.lockedChanged.connect(lambda l, k=key: self.lockedChanged.emit(k, l))
        session.commandsChanged.connect(lambda k=key: self.commandsChanged.emit(k))
        self.opened.emit(session)
        self.activate_work(key)
        return session

    def activate_work(self, key: WorkKey) -> None:
        if key not in self._sessions:
            return
        self._active_key = key
        self.activated.emit(key)

    def deactivate(self) -> None:
        """لا عمل نشِط حالياً — تُستدعى عند عرض Home/ServiceStartView
        (P1 §13): الأعمال تبقى مفتوحة، فقط لا شيء منها "معروض/نشِط"."""
        self._active_key = None
        self.activated.emit(None)

    def close_work(self, key: WorkKey) -> bool:
        """يغلق العمل — يرفض إن رفض ``session.can_close()`` الإغلاق
        (Hook مستقبليّ، راجع ``WorkSession`` — دائماً يسمح الآن). عند
        إغلاق العمل **النشِط**: يُنشَّط المجاور (نفس الفهرس أو الأخير
        المتاح) إن بقيت أعمالٌ أخرى، وإلا لا عمل نشِطاً (Home — P1 §10)."""
        session = self._sessions.get(key)
        if session is None:
            return False
        if session.can_close is not None and not session.can_close():
            return False

        idx = self._order.index(key)
        was_active = key == self._active_key
        del self._sessions[key]
        self._order.pop(idx)
        self.closed.emit(session)

        if was_active:
            if self._order:
                next_idx = min(idx, len(self._order) - 1)
                self.activate_work(self._order[next_idx])
            else:
                self.deactivate()
        return True

    def move_work(self, from_index: int, to_index: int) -> None:
        """يزامن ترتيب ``_order`` مع سحبٍ بصريّ لِـTab في ``WorkTabBar``
        (‏``QTabBar.setMovable``). لا يغيّر ``WorkKey``، لا يعيد إنشاء أيّ
        widget، لا يمسّ dirty/locked، ولا يُفعِّل أيّ عمل — فقط موضعه في
        ``open_works()``. ``WorkTabBar`` تكون قد نقلت التبويب بصرياً
        فعلياً؛ هذا فقط يُبقي مصدر الحقيقة مطابقاً لها حرفياً."""
        n = len(self._order)
        if not (0 <= from_index < n) or not (0 <= to_index < n):
            return
        if from_index == to_index:
            return
        key = self._order.pop(from_index)
        self._order.insert(to_index, key)
        self.reordered.emit()
