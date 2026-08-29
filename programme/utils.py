"""
دوال مساعدة عامة: توليد أرقام الفواتير، تصدير CSV، فتح الملفات.
"""
import csv
import os
import subprocess
import sys
from datetime import datetime


def generate_invoice_number(conn):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM invoices")
    count = cur.fetchone()[0] + 1
    return f"INV-{datetime.now().strftime('%Y%m')}-{count:04d}"


def export_rows_to_csv(rows, headers, file_path):
    with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)


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
