"""تشغيل مستقلّ لشاشة كشف الراتب (PySide6 — إعادة بناء المرحلة 3-أ):

    python -m ui2.hr.paie [--owner-hwnd <HWND>]

نافذة واحدة على ``office_system.db`` الحقيقية. الحساب في
:mod:`programme.payroll`، التخزين في :mod:`programme.payroll.repository`.
لا SQL ولا حساب هنا.

``--owner-hwnd`` (ويندوز): HWND نافذة OfficeManager — تُجعَل هذه النافذة
**مملوكة** له عبر ``GWLP_HWNDPARENT`` فتبقى فوقه وتُصغَّر/تُغلَق معه. لا
إعادة توطين ولا ضخّ حلقة أحداث. (نفس منطق :mod:`ui2.paie.__main__` — يُوحَّد
في وحدة مشتركة عند تثبيت الربط.)
"""
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox

from programme.database import get_connection
from programme.paths import ensure_user_data_migrated
from ui2 import theme
from ui2.hr.paie.bulletin_template import BulletinTemplateScreen


def _owner_hwnd_arg() -> int:
    for i, a in enumerate(sys.argv):
        if a == "--owner-hwnd" and i + 1 < len(sys.argv):
            try:
                return int(sys.argv[i + 1])
            except ValueError:
                return 0
        if a.startswith("--owner-hwnd="):
            try:
                return int(a.split("=", 1)[1])
            except ValueError:
                return 0
    return 0


def _make_owned(win, owner_hwnd: int) -> None:
    """يجعل ``win`` نافذة مملوكة لـ``owner_hwnd`` (ويندوز فقط). يُستدعى بعد
    ``show()`` (يلزم HWND أصلي صالح)."""
    if sys.platform != "win32" or not owner_hwnd:
        return
    try:
        import ctypes
        GWLP_HWNDPARENT = -8
        user32 = ctypes.windll.user32
        setter = getattr(user32, "SetWindowLongPtrW", None) or user32.SetWindowLongW
        setter(int(win.winId()), GWLP_HWNDPARENT, owner_hwnd)
    except Exception:                                    # noqa: BLE001
        pass


def main() -> int:
    app = QApplication(sys.argv)
    theme.apply_theme(app)

    ensure_user_data_migrated()
    conn = get_connection()
    conn.execute("PRAGMA busy_timeout = 5000")

    screen = BulletinTemplateScreen(conn=conn)
    win = QMainWindow()
    win.setWindowTitle("OfficeManager — كشف الراتب")
    win.resize(1040, 760)
    win.setCentralWidget(screen)
    win.show()

    owner_hwnd = _owner_hwnd_arg()
    QTimer.singleShot(0, lambda: _make_owned(win, owner_hwnd))
    # اقتراع على نافذة OfficeManager (رسائل عبر العمليات لا تصل Qt6 بثبات):
    #  اختفت → close() بلطف · صُغِّرت → صغِّر معها · استُعيدت → استعِد.
    if owner_hwnd and sys.platform == "win32":
        import ctypes
        _u = ctypes.windll.user32
        _watch = QTimer(win)
        _watch.setInterval(400)

        def _follow_owner():
            try:
                if not _u.IsWindow(owner_hwnd):
                    _watch.stop()
                    win.close()
                    return
                owner_min = bool(_u.IsIconic(owner_hwnd))
                if owner_min and not win.isMinimized() and win.isVisible():
                    win.showMinimized()
                elif not owner_min and win.isMinimized():
                    win.showNormal()
            except Exception:                            # noqa: BLE001
                _watch.stop()
        _watch.timeout.connect(_follow_owner)
        _watch.start()

    def _ask_restore() -> bool:
        return QMessageBox.question(
            win, "مسوّدة غير محفوظة",
            "وُجدت مسوّدة كشف لم تُحفَظ من جلسة سابقة.\n"
            "استعادتها؟ («لا» تتجاهلها وتمسحها.)",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes) == QMessageBox.Yes

    screen.maybe_restore_draft(_ask_restore)
    app.aboutToQuit.connect(screen.on_deactivate)
    try:
        return app.exec()
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
