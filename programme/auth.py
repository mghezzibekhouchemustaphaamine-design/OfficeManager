"""منطق حساب الدخول الوحيد للبرنامج وسجل الجلسات (login_sessions) —
بوابة دخول بسيطة تظهر قبل أي شي بالبرنامج (راجع ui/login_screen.py
وmain.py). حساب واحد بس يُنشأ مرة وحدة عند أول تشغيل؛ لا يوجد هنا أي
منطق لإدارة حسابات متعددة أو صلاحيات — هذا خارج نطاق هذي المرحلة.

الباسوورد يُخزَّن كـhash حقيقي (PBKDF2-HMAC-SHA256 مع salt عشوائي لكل
حساب) عبر hashlib/secrets من المكتبة القياسية بس — بلا أي مكتبة خارجية
جديدة، بنفس فلسفة باقي المشروع.
"""
import hashlib
import secrets

from programme.database import get_connection

# 200,000 تكرار: توصية تقريبية حالية لـPBKDF2-SHA256 — تأخير غير محسوس
# بواجهة سطح مكتب (مرة وحدة عند الدخول)، بس كافي لإبطاء أي محاولة
# تخمين لو قاعدة البيانات نفسها انسرقت يوماً.
_HASH_ITERATIONS = 200_000

# id آخر جلسة دخول ناجحة بهذا التشغيل — يُستخدم بس عند الإغلاق العادي
# لتحديث logout_at لنفس السطر (راجع record_login/record_logout_current).
# متغيّر بالذاكرة بس (مو بقاعدة البيانات) لأن العملية كلها تشتغل بجلسة
# واحدة بس (برنامج سطح مكتب، مستخدم واحد بكل مرة).
_current_session_id = None


def _hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), _HASH_ITERATIONS
    )
    return f"{salt}${digest.hex()}"


def _verify_password(password, stored_hash):
    try:
        salt, _ = stored_hash.split("$", 1)
    except (ValueError, AttributeError):
        return False
    return secrets.compare_digest(_hash_password(password, salt), stored_hash)


def has_account():
    """True لو فيه حساب مُنشأ أصلاً — شاشة الدخول (ui/login_screen.py)
    تحدّد وضعها (دخول مقابل إنشاء حساب) بناءً على هذي الدالة بس."""
    conn = get_connection()
    row = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()
    conn.close()
    return row["c"] > 0


def create_account(username, password):
    """ينشئ الحساب الوحيد للبرنامج — يُستدعى مرة وحدة بس (أول تشغيل، لو
    has_account() False). لا تحقق هنا من عدم وجود حساب سابق — هذي
    مسؤولية شاشة الدخول عبر has_account()."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
        (username, _hash_password(password)),
    )
    conn.commit()
    conn.close()


def verify_login(username, password):
    """True لو اسم المستخدم موجود وكلمة المرور مطابقة له."""
    conn = get_connection()
    row = conn.execute(
        "SELECT password_hash FROM users WHERE username = ?", (username,)
    ).fetchone()
    conn.close()
    if row is None:
        return False
    return _verify_password(password, row["password_hash"])


def record_login(username):
    """يسجّل سطر جديد بـlogin_sessions (login_at الآن، logout_at فاضي) —
    يُستدعى فوراً بعد دخول ناجح. يحفظ id السطر بالذاكرة
    (_current_session_id) حتى record_logout_current() تعرف أي سطر
    تحدّث عند الإغلاق."""
    global _current_session_id
    conn = get_connection()
    cur = conn.execute("INSERT INTO login_sessions (username) VALUES (?)", (username,))
    _current_session_id = cur.lastrowid
    conn.commit()
    conn.close()


def record_logout_current():
    """يحدّث logout_at (الآن) لنفس سطر آخر دخول ناجح بهذا التشغيل — بلا
    أي تأثير لو ما فيه جلسة مسجّلة أصلاً (نداء وقائي، زي إغلاق قبل ما
    شاشة الدخول تخلص بنجاح)."""
    global _current_session_id
    if _current_session_id is None:
        return
    conn = get_connection()
    conn.execute(
        "UPDATE login_sessions SET logout_at = datetime('now','localtime') WHERE id = ?",
        (_current_session_id,),
    )
    conn.commit()
    conn.close()
    _current_session_id = None
