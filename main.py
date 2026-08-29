"""
نظام إدارة الأعمال المكتبية - نقطة تشغيل البرنامج.

تشغيل البرنامج:
    python main.py

بناء النافذة الرئيسية والشاشة الرئيسية نفسها بـui/home/app_window.py —
هذا الملف نقطة الدخول بس (تهيئة قاعدة البيانات، نسخة احتياطية تلقائية،
ثم فتح النافذة).
"""
import programme.backup as backup
from programme.database import init_db
from ui.home.app_window import OfficeApp
from ui.resilience_wizard import maybe_show_setup_wizard


def main():
    init_db()
    # نسخة احتياطية تلقائية صامتة أول فتح بكل يوم (راجع backup.py) — قبل
    # ما ننشئ النافذة حتى، بلا أي تأخير ملموس (قاعدة البيانات صغيرة).
    backup.maybe_run_daily_backup()
    app = OfficeApp()
    # معالج إعداد حماية البيانات (3-2-1) — يظهر أول فتح بس لو الإعداد
    # ناقص (راجع ui/resilience_wizard.py)؛ بعد النافذة الرئيسية مباشرة
    # حتى يكون فوقها كنافذة فرعية (Toplevel) لا نافذة مستقلة يتيمة.
    maybe_show_setup_wizard(app)
    app.mainloop()


if __name__ == "__main__":
    main()
