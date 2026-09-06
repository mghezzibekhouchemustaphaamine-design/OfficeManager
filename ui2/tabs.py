"""نظام تبويبات مُجرَّد ومستقل — لا يعرف أي خدمة بعينها.

(في ``ui/`` القديمة كان هذا التجريد محشوراً داخل ``ui/cd/tab.py`` — هنا
وحدة مستقلّة.)

تبويب اختيارياً يطبّق بروتوكول دورة الحياة:
    ``on_activate()``   عند صيرورته التبويب النشط
    ``on_deactivate()`` عند مغادرته
يستعمله :class:`ui2.shortcuts.ShortcutManager` لتسجيل/إلغاء اختصارات
مرتبطة بالتبويب.
"""
from typing import Dict, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget


class TabHost(QWidget):
    tabAdded = Signal(int)          # id
    tabClosed = Signal(int)         # id
    currentChanged = Signal(int)    # id التبويب النشط، أو -1

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tabs = QTabWidget(self)
        self._tabs.setDocumentMode(True)
        self._tabs.setMovable(True)
        self._tabs.setTabsClosable(True)
        self._tabs.tabCloseRequested.connect(self._on_close_requested)
        self._tabs.currentChanged.connect(self._on_current_changed)

        self._by_id: Dict[int, QWidget] = {}
        self._next_id = 1
        self._active_id = -1

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._tabs)

    # -------------------- الواجهة العمومية --------------------
    def add_tab(self, widget: QWidget, title: str, *, closable=True, focus=True) -> int:
        tid = self._next_id
        self._next_id += 1
        widget.setProperty("_tab_id", tid)
        self._by_id[tid] = widget
        idx = self._tabs.addTab(widget, title)
        if not closable:
            bar = self._tabs.tabBar()
            for side in (QTabWidget.RightSide, QTabWidget.LeftSide):
                btn = bar.tabButton(idx, side)
                if btn is not None:
                    bar.setTabButton(idx, side, None)
                    btn.deleteLater()
        if focus:
            self._tabs.setCurrentIndex(idx)
        self.tabAdded.emit(tid)
        return tid

    def close_tab(self, tid: int):
        widget = self._by_id.pop(tid, None)
        if widget is None:
            return
        idx = self._tabs.indexOf(widget)
        if idx >= 0:
            self._tabs.removeTab(idx)
        widget.setParent(None)
        widget.deleteLater()
        self.tabClosed.emit(tid)

    def close_all(self):
        for tid in list(self._by_id):
            self.close_tab(tid)

    def set_title(self, tid: int, title: str):
        widget = self._by_id.get(tid)
        if widget is not None:
            idx = self._tabs.indexOf(widget)
            if idx >= 0:
                self._tabs.setTabText(idx, title)

    def count(self) -> int:
        return self._tabs.count()

    def current_id(self) -> int:
        return self._active_id

    def current_widget(self) -> Optional[QWidget]:
        return self._by_id.get(self._active_id)

    def widget(self, tid: int) -> Optional[QWidget]:
        return self._by_id.get(tid)

    def tab_widget(self) -> QTabWidget:
        return self._tabs

    # -------------------- داخلي: دورة الحياة --------------------
    def _on_close_requested(self, idx: int):
        widget = self._tabs.widget(idx)
        tid = widget.property("_tab_id") if widget is not None else None
        if tid is not None:
            self.close_tab(int(tid))

    def _on_current_changed(self, idx: int):
        prev = self._by_id.get(self._active_id)
        if prev is not None and hasattr(prev, "on_deactivate"):
            prev.on_deactivate()

        widget = self._tabs.widget(idx) if idx >= 0 else None
        self._active_id = int(widget.property("_tab_id")) if widget is not None else -1

        cur = self._by_id.get(self._active_id)
        if cur is not None and hasattr(cur, "on_activate"):
            cur.on_activate()
        self.currentChanged.emit(self._active_id)
