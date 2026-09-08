"""نقطة تشغيل مستقلّة لشاشة توليد الكشف (PySide6).

    python -m ui2.paie [--owner-hwnd <HWND>]

تُطلَق كعملية منفصلة من الشاشة الرئيسية لـ OfficeManager
(:meth:`ui.home.app_window.OfficeApp.open_paie_v2`) — لأنّ Tkinter و Qt
لكلٍّ حلقة أحداث خاصة، فتشغيلهما في عملية واحدة يُجمّد النافذة القديمة
ويوقف مؤقّت القفل التلقائي. هنا حلقة Qt وحدها، على نفس ``office_system.db``
الحقيقية.

``--owner-hwnd`` (ويندوز): HWND نافذة OfficeManager — تُجعَل هذه النافذة
**مملوكة** له عبر ``GWLP_HWNDPARENT`` فتبقى فوقه وتُصغَّر/تُغلَق معه. **لا**
إعادة توطين (embedding) ولا ضخّ حلقة أحداث — كلٌّ في عمليته.

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

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox

from programme.database import get_connection
from programme.paths import ensure_user_data_migrated
from programme.payroll import repository
from ui2 import theme
from ui2.paie.bulletin import BulletinScreen


def _owner_hwnd_arg() -> int:
    """قيمة ``--owner-hwnd`` من ``sys.argv`` (0 إن غابت / غير صالحة)."""
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
    """يجعل ``win`` نافذة مملوكة لـ``owner_hwnd`` (ويندوز فقط): تبقى فوقه،
    تُصغَّر/تُغلَق معه. لا إعادة توطين. يُستدعى بعد ``show()`` (يلزم HWND
    أصلي صالح)."""
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
    theme.apply_theme(app)                       # RTL + الخط العربي

    ensure_user_data_migrated()                  # idempotent — لو أُطلقت مستقلّةً
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
    screen = BulletinScreen(conn=conn)
    win = QMainWindow()
    win.setWindowTitle("OfficeManager — كشف الراتب")
    win.resize(1040, 680)
    win.setCentralWidget(screen)
    win.show()

    owner_hwnd = _owner_hwnd_arg()
    # نافذة مملوكة لـ OfficeManager (ويندوز) — بعد show() ليكون HWND صالحاً.
    QTimer.singleShot(0, lambda: _make_owned(win, owner_hwnd))
    # اقتراع على نافذة OfficeManager (رسائل عبر العمليات لا تصل Qt6 بثبات):
    #  • اختفت  → win.close() بلطف (aboutToQuit → حفظ المسوّدة).
    #  • صُغِّرت → صغِّر معها؛ استُعيدت → استعِد (ما لم تكن مخفيّة بالقفل).
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

    # مسوّدة غير محفوظة من جلسة سابقة (إغلاق قبل الحفظ) → اعرضها للاستعادة.
    def _ask_restore() -> bool:
        return QMessageBox.question(
            win, "مسوّدة غير محفوظة",
            "وُجدت مسوّدة كشف لم تُحفَظ من جلسة سابقة.\n"
            "استعادتها؟ («لا» تتجاهلها وتمسحها.)",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes) == QMessageBox.Yes

    screen.maybe_restore_draft(_ask_restore)

    # حفظ المسوّدة فوراً عند إغلاق النافذة (قبل أن تُهدَم الشاشة).
    app.aboutToQuit.connect(screen.on_deactivate)
    try:
        return app.exec()
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
