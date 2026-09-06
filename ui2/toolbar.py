"""شريط أدوات موحّد. اتجاه RTL يُدار مركزياً في ``ui2.theme``."""
from dataclasses import dataclass
from typing import Callable, Optional

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QSizePolicy, QToolBar, QWidget


@dataclass
class ToolAction:
    text: str
    slot: Callable[[], None]
    shortcut: Optional[str] = None
    tooltip: Optional[str] = None
    checkable: bool = False


class ToolBar(QToolBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMovable(False)
        self.setFloatable(False)

    def add(self, action: ToolAction) -> QAction:
        act = QAction(action.text, self)
        act.setCheckable(action.checkable)
        act.triggered.connect(lambda _checked=False, s=action.slot: s())
        if action.shortcut:
            act.setShortcut(QKeySequence(action.shortcut))
        if action.tooltip:
            act.setToolTip(action.tooltip)
        self.addAction(act)
        return act

    def add_stretch(self) -> QWidget:
        spacer = QWidget(self)
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.addWidget(spacer)
        return spacer

    def add_widget(self, widget: QWidget) -> QWidget:
        self.addWidget(widget)
        return widget
