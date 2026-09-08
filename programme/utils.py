"""
دالة مساعدة عامة: فتح ملف بالبرنامج الافتراضي لنظام التشغيل.

(حُذفت ``generate_invoice_number`` و``export_rows_to_csv`` — كانتا مرتبطتين
بجدول ``invoices`` الميت الذي أُسقط في هجرة الأجور رقم 4؛ لم تكن أيّ منهما
مُستدعاة.)
"""
import os
import subprocess
import sys


def open_path(path):
    """يفتح ملفاً باستخدام البرنامج الافتراضي لنظام التشغيل."""
    if not path or not os.path.exists(path):
        return False
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.run(["open", path], check=False)
    else:
        subprocess.run(["xdg-open", path], check=False)
    return True
