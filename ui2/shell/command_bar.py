"""CommandBar — شريط أدوات خاصّ بالخدمة المفتوحة حالياً.

Prototype: حاوية فارغة بارتفاع ثابت — لا أزرار فعلية بعد. الهدف إثبات
أنها تحتفظ بمكانها/ارتفاعها سواء كان فيها محتوى أو لا (بند 5 في المهمّة)،
فلا يقفز الـ layout عند التنقّل بين Home وخدمة.
"""
from PySide6.QtWidgets import QHBoxLayout, QWidget

from ui2 import theme

HEIGHT = 40


class CommandBar(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(HEIGHT)
        #  ‏P0.1 §3: خلفية BG (لا SURFACE — تتماهى مع TopBar/WorkTabBar
        #  الأبيضين المجاورين) + حدّان علويّ وسفليّ خفيفان — يجعلان مكان
        #  «شريط أدوات الخدمة» مقروءاً بصرياً حتى فارغاً، بلا أيّ نصٍّ أو
        #  تسمية تصحيحية (لا "CommandBar" ولا Debug label للمستخدم).
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

    def clear(self) -> None:
        """يزيل كل الأدوات الحالية (بلا استخدام فعلي بعد — لمستقبل الخدمات)."""
        while self._lay.count() > 1:
            item = self._lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
