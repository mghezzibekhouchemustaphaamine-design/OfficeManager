"""CommandBar — عرضٌ بصريّ بحت لأوامر العمل النشِط (P2 §8).

**لا منطق هنا**: ``CommandManager`` هو من يقرّر visible/enabled لكلّ
``QAction`` (P2 §6/§13) — هذا الصنف فقط يرتّبها في صفّ أفقيّ هادئ حسب
ترتيب Registry الثابت (لا dict order أيّ Work)، بفواصل بين المجموعات
التي تحوي أمراً ظاهراً واحداً على الأقلّ (P2 §15: لا فواصل فارغة).

Prototype قبل P2: كانت حاويةً فارغة ثابتة الارتفاع فقط — ذلك السلوك
(لا layout jumping، P0.2 §8) محفوظٌ الآن أيضاً: الارتفاع لا يتغيّر
سواء ظهرت أزرار أو لا."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QToolButton, QWidget

from ui2 import theme
from ui2.shell.commands import GROUP_ORDER

HEIGHT = 40


class CommandBar(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(HEIGHT)
        #  ‏STRUCTURAL DIRECTION != TEXT DIRECTION (نفس مبدأ WorkTabBar/
        #  WorkStatusBar): ترتيب الأوامر ثابتٌ حسب Registry (FILE ثم EDIT
        #  ثم WORKFLOW) بصرف النظر عن RTL العامّ الموروث من WorkspaceHost.
        self.setLayoutDirection(Qt.LeftToRight)
        self.setStyleSheet(
            f"background: {theme.BG};"
            f" border-top: 1px solid {theme.BORDER};"
            f" border-bottom: 1px solid {theme.BORDER};"
        )
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(
            theme.SPACE["md"], theme.SPACE["xs"], theme.SPACE["md"], theme.SPACE["xs"]
        )
        self._lay.setSpacing(theme.SPACE["xs"])
        self._lay.addStretch(1)
        self._command_manager = None

    def set_command_manager(self, command_manager) -> None:
        """يربط CommandBar بمصدر الأوامر — إعادة بناء فورية، ثمّ عند كلّ
        ``actionsChanged`` (تبديل عمل نشِط، تغيّر dirty/locked، ...)."""
        self._command_manager = command_manager
        command_manager.actionsChanged.connect(self._rebuild)
        self._rebuild()

    # ------------------------------------------------------------- البناء
    def _clear(self) -> None:
        #  ‏آخر عنصر (index أخير) هو الـstretch الثابت — لا يُزال أبداً،
        #  فيبقى ارتفاع/تموضع الشريط ثابتاً سواء كان فارغاً أو لا.
        while self._lay.count() > 1:
            item = self._lay.takeAt(0)
            w = item.widget()
            if w is not None:
                #  ‏setParent(None) فوريّ (بخلاف deleteLater وحدها التي
                #  تُبقيه ابناً حتى الحلقة التالية لِـevent loop) — لازمٌ
                #  كي لا يظهر مضاعَفاً في إعادة بناءٍ لاحقة قبل أن يُنفَّذ
                #  الحذف الفعليّ (مثلاً findChildren في نفس الدورة).
                w.setParent(None)
                w.deleteLater()

    def _rebuild(self) -> None:
        self._clear()
        if self._command_manager is None:
            return
        specs_actions = self._command_manager.actions_in_order()
        insert_at = 0
        for group in GROUP_ORDER:
            group_actions = [
                action for spec, action in specs_actions
                if spec.group == group and action.isVisible()
            ]
            if not group_actions:
                continue
            if insert_at > 0:
                self._lay.insertWidget(insert_at, self._make_separator())
                insert_at += 1
            for action in group_actions:
                btn = QToolButton(self)
                btn.setDefaultAction(action)
                btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
                btn.setAutoRaise(True)
                self._lay.insertWidget(insert_at, btn)
                insert_at += 1

    def _make_separator(self) -> QFrame:
        line = QFrame(self)
        line.setFrameShape(QFrame.VLine)
        line.setFrameShadow(QFrame.Sunken)
        return line

    def clear(self) -> None:
        """محفوظة للتوافق مع الاستخدام القديم — تُعيد الشريط لحالة
        فارغة (يُستدعى ``_rebuild`` تلقائياً عند أيّ ``actionsChanged``
        لاحق، فلا حاجة لاستدعائها يدوياً في المسار الطبيعي)."""
        self._clear()
