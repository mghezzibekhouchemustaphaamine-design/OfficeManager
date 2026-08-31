"""إعدادات عامة للبرنامج مخزَّنة كـkey/value بجدول app_settings — عام
بما يكفي لأي إعداد مستقبلي (مو بس مدة القفل التلقائي)، بدل عمود/جدول
مخصّص لكل إعداد جديد. راجع ui/settings_screen.py للواجهة.
"""
from programme.database import get_connection

_AUTO_LOCK_MINUTES_KEY = "auto_lock_minutes"
_AUTO_LOCK_MINUTES_DEFAULT = 5


def get_setting(key, default=None):
    conn = get_connection()
    row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row is not None else default


def set_setting(key, value):
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", (key, str(value))
    )
    conn.commit()
    conn.close()


def get_auto_lock_minutes():
    """مدة القفل التلقائي بالدقايق — تخزين بس بهذي المرحلة، بلا أي
    تفعيل فعلي (التفعيل مرحلة قادمة). 5 افتراضياً لو ماكو قيمة محفوظة
    بعد، أو لو القيمة المحفوظة تالفة لسبب ما."""
    value = get_setting(_AUTO_LOCK_MINUTES_KEY)
    if value is None:
        return _AUTO_LOCK_MINUTES_DEFAULT
    try:
        return int(value)
    except ValueError:
        return _AUTO_LOCK_MINUTES_DEFAULT


def set_auto_lock_minutes(minutes):
    set_setting(_AUTO_LOCK_MINUTES_KEY, int(minutes))
