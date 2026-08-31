"""
نظام إدارة الأعمال المكتبية - نقطة تشغيل البرنامج.

تشغيل البرنامج:
    python main.py

بناء النافذة الرئيسية والشاشة الرئيسية نفسها بـui/home/app_window.py —
هذا الملف نقطة الدخول بس (تهيئة قاعدة البيانات، نسخة احتياطية تلقائية،
ثم فتح النافذة).
"""
import logging
import tkinter as tk
from tkinter import messagebox

import programme.backup as backup
from programme.database import init_db
from programme.logging_setup import configure_logging
from ui.home.app_window import OfficeApp
from ui.login_screen import run_login_flow
from ui.resilience_wizard import maybe_show_setup_wizard


logger = configure_logging()


def main():
    logger.info("OfficeManager startup")
    try:
        init_db()
        # نسخة احتياطية تلقائية صامتة أول فتح بكل يوم (راجع backup.py) — قبل
        # ما ننشئ النافذة حتى، بلا أي تأخير ملموس (قاعدة البيانات صغيرة).
        backup.maybe_run_daily_backup()
        # بوابة الدخول قبل أي شي بالواجهة — لو المستخدم سكّر نافذة
        # الدخول بدون دخول ناجح، نطلع بلا ما نفتح OfficeApp إطلاقاً.
        if not run_login_flow():
            logger.info("Login cancelled - exiting without opening OfficeApp")
            return
        app = OfficeApp()
        # معالج إعداد حماية البيانات (3-2-1) — يظهر أول فتح بس لو الإعداد
        # ناقص (راجع ui/resilience_wizard.py)؛ بعد النافذة الرئيسية مباشرة
        # حتى يكون فوقها كنافذة فرعية (Toplevel) لا نافذة مستقلة يتيمة.
        maybe_show_setup_wizard(app)
        app.mainloop()
    except Exception:
        logger.exception("Fatal error during OfficeManager startup")
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "تعذر تشغيل OfficeManager",
                "حدث خطأ أثناء تشغيل البرنامج.\n"
                "راجع ملف office_manager.log لمعرفة التفاصيل.",
                parent=root,
            )
            root.destroy()
        except Exception:
            # إذا تعذر حتى إنشاء واجهة الخطأ، يبقى الخطأ محفوظاً في السجل.
            pass
        raise


if __name__ == "__main__":
    main()
