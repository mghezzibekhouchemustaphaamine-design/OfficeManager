"""تشغيل Shell وحده للتجربة — لا يستبدل ``main.py`` الرسمي.

    python -m ui2.shell                 # وضعٌ عاديّ — بلا Demo Tabs
    python -m ui2.shell --demo-tabs     # + تبويبات أعمالٍ تجريبية (P0.3 §6)
    python -m ui2.shell --demo-many-tabs  # + 13 عملاً لاختبار overflow (P2.1 §15)
"""
import sys

from PySide6.QtWidgets import QApplication

from ui2 import theme
from ui2.shell.main_window import OfficeMainWindow


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    theme.apply_theme(app)

    win = OfficeMainWindow()
    #  ‏P0.3 §6: Demo Tabs معزولةٌ خلف علمٍ صريح — لا تظهر تلقائياً في
    #  الوضع العاديّ (تحقّقٌ بصريّ فقط، ليست جزءاً من مسار المنتج).
    if "--demo-tabs" in sys.argv[1:]:
        win.enable_demo_tabs()
    elif "--demo-many-tabs" in sys.argv[1:]:
        win.enable_demo_many_tabs()
    win.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
