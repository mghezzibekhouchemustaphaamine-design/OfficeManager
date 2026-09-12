"""CommandManager — يوجّه Work Commands من QAction واحدة إلى العمل
النشِط فقط (P2 §6).

Button / Shortcut / Menu مستقبلاً
            ↓
       QAction واحدة  (يملكها هذا الصنف)
            ↓
      CommandManager   (هذا الصنف)
            ↓
       Active Work     (WorkspaceManager.active_work())
            ↓
   handler الخاص بالعمل (WorkSession.command_binding)

**لا يعرف شيئاً عن أيّ service_key** (P2 §14) — يتعامل حصراً مع
``CommandId``/``WorkCommandBinding`` التي يوفّرها ``WorkSession`` النشِط.
مصدر الحقيقة الوحيد لِـvisible/enabled هو QAction نفسها (P2 §13): زرّ
CommandBar واختصار لوحة المفاتيح كلاهما يقرآن نفس QAction، لا حالة
مستقلّة لأيٍّ منهما."""
from typing import Dict, List, Tuple

from PySide6.QtGui import QAction, QKeySequence

from PySide6.QtCore import QObject, Signal

from ui2.shell.command_icons import command_icon
from ui2.shell.commands import COMMAND_REGISTRY, CommandId, CommandSpec
from ui2.shell.workspace_manager import WorkspaceManager


class CommandManager(QObject):
    """يملك QAction واحدة ثابتة لكلّ ``CommandId`` (P2 §3) — تُنشَأ مرّة
    واحدة، مملوكة من ``action_owner`` (ودجت داخل نافذة OfficeManager، لا
    نافذة مستقلّة) بحيث يبقى الاختصار محصوراً داخل النافذة (P2 §3:
    ``QAction.shortcutContext`` الافتراضيّ ``Qt.WindowShortcut`` — ليس
    system-global)."""

    #  ‏visible/enabled لأيّ Action تغيّرت — CommandBar يعيد البناء عندها.
    actionsChanged = Signal()
    #  ‏أمرٌ نُفِّذ فعلياً على العمل النشِط — (WorkKey, CommandId). عرضٌ
    #  عامّ (لا يعرف معنى الخدمة) يمكن لِـmain_window الاستماع إليه
    #  لتحديث WorkStatusBar برسالةٍ عامّة.
    commandExecuted = Signal(object, object)

    def __init__(self, workspace_manager: WorkspaceManager, action_owner, parent=None):
        super().__init__(parent)
        self._workspace_manager = workspace_manager
        self._actions: Dict[CommandId, QAction] = {}

        for spec in COMMAND_REGISTRY:
            action = QAction(spec.label, action_owner)
            action.setIcon(command_icon(spec.id))
            #  ‏P2.1 §10: "حفظ (Ctrl+S)" — الاختصار من Registry نفسها، لا
            #  تكراراً hard-coded في CommandBar. بلا اختصار → التسمية فقط.
            action.setToolTip(
                f"{spec.label} ({spec.shortcut})" if spec.shortcut else spec.label
            )
            if spec.shortcut:
                action.setShortcut(QKeySequence(spec.shortcut))
            #  لا عمل نشِط بعد — كل الأوامر تبدأ غير ظاهرة/معطَّلة (P2 §7).
            action.setVisible(False)
            action.setEnabled(False)
            action.triggered.connect(
                lambda checked=False, cid=spec.id: self._trigger(cid)
            )
            action_owner.addAction(action)
            self._actions[spec.id] = action

        workspace_manager.activated.connect(lambda _key: self.refresh())
        workspace_manager.opened.connect(lambda _session: self.refresh())
        workspace_manager.closed.connect(lambda _session: self.refresh())
        workspace_manager.commandsChanged.connect(self._on_commands_changed)

        self.refresh()

    # ------------------------------------------------------------- استعلام
    def action(self, command_id: CommandId) -> QAction:
        return self._actions[command_id]

    def actions_in_order(self) -> List[Tuple[CommandSpec, QAction]]:
        """كلّ (Spec, QAction) بترتيب Registry الثابت (P2 §8) — CommandBar
        يستهلك هذا مباشرةً، بلا فرزٍ خاصّ به."""
        return [(spec, self._actions[spec.id]) for spec in COMMAND_REGISTRY]

    # -------------------------------------------------------------- تحديث
    def _on_commands_changed(self, key) -> None:
        #  عملٌ غير النشِط أعلن تغيّراً — لا يهمّنا الآن (P2 §12: التبديل
        #  بين الأعمال يُحدَّث أصلاً عبر إشارة activated).
        if key == self._workspace_manager.active_key():
            self.refresh()

    def refresh(self) -> None:
        """يعيد ضبط visible/enabled لكلّ Action حسب العمل النشِط فقط
        (P2 §7/§12): لا عمل نشِط (Home/ServiceStartView) → كل الأوامر
        مخفيّة ومعطَّلة، بلا أثرٍ لأيّ عملٍ سابق في الخلفية."""
        session = self._workspace_manager.active_work()
        for spec in COMMAND_REGISTRY:
            action = self._actions[spec.id]
            binding = session.command_binding(spec.id) if session is not None else None
            action.setVisible(binding is not None)
            action.setEnabled(binding is not None and binding.is_enabled())
        self.actionsChanged.emit()

    def _trigger(self, command_id: CommandId) -> None:
        """توجيه التنفيذ — العمل النشِط فقط، ويتحقّق مجدداً من enabled
        (دفاعٌ إضافي: اختصار قد يصل حتى لو تغيّرت الحالة للتوّ، P2 §11)."""
        session = self._workspace_manager.active_work()
        if session is None:
            return
        binding = session.command_binding(command_id)
        if binding is None or not binding.is_enabled():
            return
        binding.handler()
        self.commandExecuted.emit(session.key, command_id)
