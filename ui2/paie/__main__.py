"""نقطة تشغيل مستقلّة لشاشة توليد الكشف (PySide6).

    python -m ui2.paie

تُطلَق كعملية منفصلة من الشاشة الرئيسية لـ OfficeManager
(:meth:`ui.home.app_window.OfficeApp.open_paie_v2`) — لأنّ Tkinter و Qt
لكلٍّ حلقة أحداث خاصة، فتشغيلهما في عملية واحدة يُجمّد النافذة القديمة
ويوقف مؤقّت القفل التلقائي. هنا حلقة Qt وحدها، على نفس ``office_system.db``
الحقيقية.

الحساب كلّه في :mod:`programme.payroll`، والتخزين في
:mod:`programme.payroll.repository`. لا SQL ولا حساب في هذا الملف.
"""
import os
import sys

# جذر المشروع في المسار حتى يعمل ``python -m ui2.paie`` أياً كان cwd
# (نفس نمط ``demos/ui2_paie_gallery.py``).
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from PySide6.QtWidgets import QApplication, QMainWindow

from programme.database import get_connection
from programme.payroll import repository
from ui2 import theme
from ui2.paie.bulletin import BulletinScreen


def main() -> int:
    app = QApplication(sys.argv)
    theme.apply_theme(app)                       # RTL + الخط العربي

    conn = get_connection()                      # office_system.db الحقيقية
    # العملية القديمة (Tkinter) قد تكتب في نفس الملف بالتوازي — مهلة
    # انتظار بدل رفع «database is locked» فوراً. القديم يكتب
    # cd_documents/hr_documents/clients، والجديد جداول الأجور — تنازع
    # فعلي شبه معدوم، لكن المهلة احتياط رخيص.
    conn.execute("PRAGMA busy_timeout = 5000")
    # الاثنتان idempotent: init_db نفّذ الهجرات أصلاً، و ensure_default_client
    # يرجّع id الموجود إن كان الكتالوج موجوداً.
    repository.run_migrations(conn)
    repository.ensure_default_client(conn=conn)

    # نافذة بشاشة واحدة — لا حاجة لتبويبات. BulletinScreen يحمل شريط
    # أدواته الخاص (من ui2/toolbar).
    win = QMainWindow()
    win.setWindowTitle("OfficeManager — كشف الراتب")
    win.resize(1040, 680)
    win.setCentralWidget(BulletinScreen(conn=conn))
    win.show()
    try:
        return app.exec()
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
