"""تشغيل مستقلّ لشاشة كشف الراتب (PySide6 — إعادة بناء المرحلة 3-أ):

    python -m ui2.hr.paie

نافذة واحدة على ``office_system.db`` الحقيقية. الحساب في
:mod:`programme.payroll`، التخزين في :mod:`programme.payroll.repository`.
لا SQL ولا حساب هنا.
"""
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from PySide6.QtWidgets import QApplication, QMainWindow

from programme.database import get_connection
from programme.paths import ensure_user_data_migrated
from ui2 import theme
from ui2.hr.paie.bulletin_template import BulletinTemplateScreen


def main() -> int:
    app = QApplication(sys.argv)
    theme.apply_theme(app)

    ensure_user_data_migrated()
    conn = get_connection()
    conn.execute("PRAGMA busy_timeout = 5000")

    win = QMainWindow()
    win.setWindowTitle("OfficeManager — كشف الراتب")
    win.resize(1040, 760)
    win.setCentralWidget(BulletinTemplateScreen(conn=conn))
    win.show()
    try:
        return app.exec()
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
