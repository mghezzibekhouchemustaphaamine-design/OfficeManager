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

# أحرف/أرقام واضحة بصرياً بس (بلا 0/O ولا 1/I/L) — كود الاسترجاع يُكتب
# يدوياً على ورقة عادة، فالالتباس بين حرف ورقم يشبهه يعطّل الاسترجاع
# نفسه وقت الحاجة الفعلية له.
_RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_recovery_code(groups=4, group_length=4):
    """يولّد كود استرجاع عشوائي قوي (secrets، مو random) بصيغة مقروءة
    يسهل نسخها يدوياً — مثلاً "XXXX-XXXX-XXXX-XXXX". يُستعمل مرة وحدة
    عند إنشاء الحساب (راجع create_account) لإتاحة حذف الحساب لاحقاً لو
    نُسيت كلمة المرور (راجع reset_account_with_recovery_code)."""
    return "-".join(
        "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(group_length))
        for _ in range(groups)
    )


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
    has_account() False، أو بعد استرجاع ناجح — راجع
    reset_account_with_recovery_code). لا تحقق هنا من عدم وجود حساب
    سابق — هذي مسؤولية شاشة الدخول عبر has_account().

    يرجّع كود الاسترجاع الخام (raw) — يُعرض مرة وحدة بس بشاشة الدخول
    (ui/login_screen.py) مباشرة بعد الإنشاء؛ لا يُخزَّن ولا يُحفَظ هنا
    بأي شكل غير الـhash بقاعدة البيانات، فلو ضاع بعد هذي اللحظة ما فيه
    طريقة لاسترجاعه — بس لحذف الحساب وإنشاء واحد جديد."""
    recovery_code = generate_recovery_code()
    conn = get_connection()
    conn.execute(
        "INSERT INTO users (username, password_hash, recovery_code_hash) VALUES (?, ?, ?)",
        (username, _hash_password(password), _hash_password(recovery_code)),
    )
    conn.commit()
    conn.close()
    return recovery_code


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


def get_current_username():
    """ترجّع اسم المستخدم الحالي (الحساب الوحيد بالبرنامج) — None لو
    ماكو حساب أصلاً. تُستخدم لعرضه بشاشة الإعدادات (ui/settings_screen.py)."""
    conn = get_connection()
    row = conn.execute("SELECT username FROM users LIMIT 1").fetchone()
    conn.close()
    return row["username"] if row is not None else None


def update_account(current_password, new_username=None, new_password=None):
    """يحدّث اسم المستخدم و/أو كلمة المرور للحساب الحالي — بعد التحقق
    من current_password أولاً. recovery_code_hash ما ينلمس هنا إطلاقاً
    (تغييره خارج نطاق هذي الدالة — راجع reset_account_with_recovery_code
    لمسار مختلف كليّاً، مخصّص لحالة نسيان الباسوورد بس).

    يرجّع False (بدون أي تغيير) لو current_password غلط أو ماكو حساب
    أصلاً. يرجّع True لو التحقق نجح — حتى لو new_username وnew_password
    الاثنين None (نجاح بلا أي تعديل فعلي)."""
    conn = get_connection()
    row = conn.execute("SELECT id, password_hash FROM users LIMIT 1").fetchone()
    if row is None or not _verify_password(current_password, row["password_hash"]):
        conn.close()
        return False

    updates, params = [], []
    if new_username:
        updates.append("username = ?")
        params.append(new_username)
    if new_password:
        updates.append("password_hash = ?")
        params.append(_hash_password(new_password))
    if updates:
        params.append(row["id"])
        conn.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()
    conn.close()
    return True


def reset_account_with_recovery_code(code):
    """يتحقق من كود الاسترجاع مقابل recovery_code_hash المخزّن للحساب
    الحالي (حساب واحد بس بكل تنصيب). لو صحيح: يحذف سطر الحساب من users
    بس (بدون لمس login_sessions — يبقى تاريخ الجلسات القديمة كما هو)
    ويرجّع True. لو غلط أو ماكو حساب أصلاً: ما يغيّر أي شي ويرجّع False.

    بلا حد لعدد المحاولات — نطاق ضيّق بطلب صريح لهذي المرحلة."""
    conn = get_connection()
    row = conn.execute("SELECT id, recovery_code_hash FROM users LIMIT 1").fetchone()
    if row is None or not row["recovery_code_hash"]:
        conn.close()
        return False
    if not _verify_password(code, row["recovery_code_hash"]):
        conn.close()
        return False
    conn.execute("DELETE FROM users WHERE id = ?", (row["id"],))
    conn.commit()
    conn.close()
    return True


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
