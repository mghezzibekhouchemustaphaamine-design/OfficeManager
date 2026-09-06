"""إدارة اختصارات لوحة المفاتيح مع تسجيل/إلغاء مرتبطين بدورة حياة
التبويب.

لا ``bind_all``: كل ``QShortcut`` ابن ودجت مضيف وبنطاق محدَّد
(افتراضياً ``WidgetWithChildrenShortcut``)، وتُلغى دفعةً بـ
:meth:`unregister_all` عند مغادرة التبويب — فلا تعارض عند فتح خدمتين
معاً (وهو ما كان ``bind_all`` بلا إلغاء في ``ui/`` القديمة سيسبّبه).

نمط الاستعمال في تبويب:

    def on_activate(self):
        self._sc = ShortcutManager(self)
        self._sc.register_many({"Ctrl+S": self.save, "Ctrl+W": self.close})

    def on_deactivate(self):
        self._sc.unregister_all()
"""
from typing import Callable, Dict, List

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QWidget


class ShortcutManager:
    def __init__(self, host: QWidget, *, scope=Qt.WidgetWithChildrenShortcut):
        self._host = host
        self._scope = scope
        self._shortcuts: List[QShortcut] = []

    def register(self, key: str, callback: Callable[[], None], *, scope=None) -> QShortcut:
        sc = QShortcut(QKeySequence(key), self._host)
        sc.setContext(scope or self._scope)
        sc.activated.connect(callback)
        self._shortcuts.append(sc)
        return sc

    def register_many(self, mapping: Dict[str, Callable[[], None]]):
        for key, callback in mapping.items():
            self.register(key, callback)

    def unregister_all(self):
        for sc in self._shortcuts:
            sc.setEnabled(False)
            sc.setParent(None)
            sc.deleteLater()
        self._shortcuts.clear()

    def __len__(self) -> int:
        return len(self._shortcuts)
