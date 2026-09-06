"""النافذة الرئيسية — تجمع :class:`ui2.toolbar.ToolBar` و
:class:`ui2.tabs.TabHost` وشريط حالة. لا منطق خدمة."""
from PySide6.QtWidgets import QMainWindow, QWidget

from ui2.tabs import TabHost
from ui2.toolbar import ToolBar


class MainWindow(QMainWindow):
    def __init__(self, title: str = "OfficeManager", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(940, 600)

        self.toolbar = ToolBar(self)
        self.addToolBar(self.toolbar)

        self.tabs = TabHost(self)
        self.setCentralWidget(self.tabs)

        self.statusBar()

    def add_tab(self, widget: QWidget, title: str, **kwargs) -> int:
        return self.tabs.add_tab(widget, title, **kwargs)

    def status(self, text: str, msec: int = 4000):
        self.statusBar().showMessage(text, msec)
