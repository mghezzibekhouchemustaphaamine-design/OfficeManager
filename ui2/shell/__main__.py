"""تشغيل Shell وحده للتجربة — لا يستبدل ``main.py`` الرسمي.

    python -m ui2.shell
"""
import sys

from PySide6.QtWidgets import QApplication

from ui2 import theme
from ui2.shell.main_window import OfficeMainWindow


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    theme.apply_theme(app)

    win = OfficeMainWindow()
    win.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
