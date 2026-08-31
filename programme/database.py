"""
طبقة الاتصال بقاعدة البيانات (SQLite) وإنشاء الجداول.
"""
import json
import os
import sqlite3
from datetime import date

# قاعدة البيانات الحقيقية تبقى بجذر المشروع (بلا أي تغيير بمكانها رغم
# نقل هذا الملف نفسه لمجلد programme/ — راجع تنظيم المشروع بالجذر)،
# فلازم مستوى إضافي (dirname مرتين) يطلع من programme/ للجذر بالضبط.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(_PROJECT_ROOT, "office_system.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            address TEXT,
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_number TEXT UNIQUE NOT NULL,
            client_id INTEGER,
            date TEXT NOT NULL,
            due_date TEXT,
            status TEXT NOT NULL DEFAULT 'غير مدفوعة',
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS invoice_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER NOT NULL,
            description TEXT NOT NULL,
            quantity REAL NOT NULL DEFAULT 1,
            unit_price REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            due_date TEXT,
            due_time TEXT,
            priority TEXT DEFAULT 'عادية',
            status TEXT NOT NULL DEFAULT 'قيد الانتظار',
            client_id INTEGER,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            file_path TEXT NOT NULL,
            category TEXT,
            client_id INTEGER,
            added_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE SET NULL
        );

        -- سجل كل مستند CD (Change Devise) يُنشأ فعلياً — يسمح بالبحث لاحقاً
        -- (زي: هل أعطيت فلان مستند الأسبوع اللي فات؟) بدون أي ربط بجدول
        -- clients (بعكس Dossier، هون كل مرة موظف/راكب جديد عادةً).
        CREATE TABLE IF NOT EXISTS cd_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dossier_no TEXT,
            passager TEXT,
            passport_no TEXT,
            doc_date TEXT,
            agence TEXT,
            guichet TEXT,
            eur_amount REAL,
            dzd_amount REAL,
            file_path TEXT NOT NULL,
            full_data_json TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        -- حساب الدخول الوحيد للبرنامج (بوابة دخول قبل أي شي — راجع
        -- ui/login_screen.py وprogramme/auth.py). حساب واحد بس يُنشأ
        -- مرة وحدة عند أول تشغيل؛ password_hash يخزّن salt وhash معاً
        -- بصيغة "salt$hash" (PBKDF2-HMAC-SHA256، مكتبة قياسية بس).
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        -- سجل دخول/خروج بسيط للمحاسبة — سطر جديد كل دخول ناجح
        -- (login_at)، يتحدّث logout_at لنفس السطر عند إغلاق البرنامج
        -- عادي (راجع _on_close_request بـui/home/app_window.py).
        CREATE TABLE IF NOT EXISTS login_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            login_at TEXT DEFAULT (datetime('now','localtime')),
            logout_at TEXT
        );

        -- إعدادات عامة للبرنامج بصيغة key/value — عامة بما يكفي لأي
        -- إعداد مستقبلي (راجع programme/settings.py)، بدل عمود/جدول
        -- مخصّص لكل إعداد جديد.
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """
    )
    # full_data_json: أضيف بعد ما كان الجدول موجود أصلاً بقواعد بيانات
    # سابقة — CREATE TABLE IF NOT EXISTS ما يضيف أعمدة لجدول موجود، لازم
    # ALTER TABLE يدوي لقواعد البيانات القديمة. يخزّن كل حقول الاستمارة
    # (نفس شكل collect_data()) كـJSON، حتى نقدر نرجّع مستند قديم كامل
    # لحقول الاستمارة (فتح/تعديل/إعادة طباعة) — الأعمدة الأخرى تبقى زي
    # ما هي للبحث السريع بالجدول فقط.
    existing_cols = {row[1] for row in cur.execute("PRAGMA table_info(cd_documents)")}
    if "full_data_json" not in existing_cols:
        cur.execute("ALTER TABLE cd_documents ADD COLUMN full_data_json TEXT")
    # pdf_path: أضيف لاحقاً بعد ما صار كل حفظ حقيقي يولّد PDF دائم تلقائياً
    # جنب Word (بطلب صريح — PDF هو "المنتج النهائي" المهم، Word نسخة خام
    # للتعديل). فاضي للمستندات القديمة المولَّدة قبل هذا التغيير (Word بس).
    if "pdf_path" not in existing_cols:
        cur.execute("ALTER TABLE cd_documents ADD COLUMN pdf_path TEXT")
    # recovery_code_hash: أضيف بعد ما كان جدول users موجود أصلاً بقواعد
    # بيانات سابقة (نفس سبب full_data_json فوق) — hash كود الاسترجاع
    # (راجع programme/auth.py:generate_recovery_code) يُستعمل لحذف
    # الحساب الحالي لو نُسيت كلمة المرور. فاضي للحسابات المُنشأة قبل
    # إضافة هذي الميزة.
    existing_user_cols = {row[1] for row in cur.execute("PRAGMA table_info(users)")}
    if "recovery_code_hash" not in existing_user_cols:
        cur.execute("ALTER TABLE users ADD COLUMN recovery_code_hash TEXT")
    conn.commit()
    conn.close()


def serialize_cd_data(data):
    """يحوّل قاموس بيانات استمارة CD (نفس شكل CDTab.collect_data()) لنص
    JSON قابل للتخزين — تواريخ date تتحوّل لنص ISO أولاً (JSON ما يعرف
    يخزّن كائن date مباشرة)."""
    d = dict(data)
    for key in ("date", "date_delivrance"):
        if d.get(key):
            d[key] = d[key].isoformat()
    return json.dumps(d, ensure_ascii=False)


def deserialize_cd_data(full_data_json):
    """عكس serialize_cd_data — يرجّع القاموس بنفس الشكل الأصلي (تواريخ ISO
    ترجع لكائنات date). يرجّع None لو النص فاضي/تالف (مستند قديم قبل
    إضافة full_data_json، أو خلل بالبيانات)."""
    if not full_data_json:
        return None
    try:
        d = json.loads(full_data_json)
    except ValueError:
        return None
    for key in ("date", "date_delivrance"):
        if d.get(key):
            d[key] = date.fromisoformat(d[key])
    return d


def log_cd_document(record, full_data=None):
    """يسجّل مستند CD مولَّد فعلياً بجدول cd_documents، للبحث/الأرشفة لاحقاً.

    record: dict فيه dossier_no, passager, passport_no, doc_date, agence,
    guichet, eur_amount, dzd_amount, file_path, pdf_path (كلها اختيارية
    إلا file_path) — تُستخدم للعرض/البحث السريع بجدول السجل. pdf_path
    فاضي للمستندات القديمة (قبل ما يصير PDF يتولّد تلقائياً مع كل حفظ).
    full_data (اختياري): قاموس بيانات الاستمارة الكامل (collect_data())،
    يُخزَّن كـJSON لإتاحة فتح/تعديل/إعادة طباعة المستند لاحقاً ببياناته
    الكاملة، لا بس الحقول المختصرة أعلاه.

    يرجّع id السطر الجديد — يُستخدم لاحقاً لتحديث نفس الحالة بدل تكرارها
    (راجع update_cd_document وشرح "حفظ" مقابل "حفظ في مكان آخر" بـtab.py)."""
    conn = get_connection()
    cur = conn.execute(
        """
        INSERT INTO cd_documents
            (dossier_no, passager, passport_no, doc_date, agence, guichet,
             eur_amount, dzd_amount, file_path, pdf_path, full_data_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.get("dossier_no"), record.get("passager"), record.get("passport_no"),
            record.get("doc_date"), record.get("agence"), record.get("guichet"),
            record.get("eur_amount"), record.get("dzd_amount"), record["file_path"],
            record.get("pdf_path"),
            serialize_cd_data(full_data) if full_data is not None else None,
        ),
    )
    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id


def update_cd_document(row_id, record, full_data=None):
    """يحدّث سطراً موجوداً أصلاً بجدول cd_documents (بدل إضافة سطر جديد) —
    "تصحيح لنفس الحالة" لا "حالة جديدة": تعديل حالة اتفتحت للتعديل
    وأُعيد حفظها بنفس التبويب (راجع "loaded_from" بـtab.py)، بغض النظر
    حتى لو تغيّر رقم البوردرو نفسه — القرار مربوط بهوية التبويب لا بالرقم."""
    conn = get_connection()
    conn.execute(
        """
        UPDATE cd_documents SET
            dossier_no=?, passager=?, passport_no=?, doc_date=?, agence=?, guichet=?,
            eur_amount=?, dzd_amount=?, file_path=?, pdf_path=?, full_data_json=?
        WHERE id=?
        """,
        (
            record.get("dossier_no"), record.get("passager"), record.get("passport_no"),
            record.get("doc_date"), record.get("agence"), record.get("guichet"),
            record.get("eur_amount"), record.get("dzd_amount"), record["file_path"],
            record.get("pdf_path"),
            serialize_cd_data(full_data) if full_data is not None else None,
            row_id,
        ),
    )
    conn.commit()
    conn.close()


def find_cd_document_by_path(path):
    """يلقى سطر cd_documents اللي ملف Word أو PDF فيه يطابق المسار
    المُعطى بالضبط (بعد تطبيع المسار — راجع os.path.abspath) — يُستخدم
    لما نفتح ملف من الشريط الجانبي (نقرة مزدوجة/📂 فتح) عشان نعرف هل
    له حالة CD كاملة نقدر نفتحها بالاستمارة (للقراءة فقط، حماية عمل
    منتهي — راجع _open_case_readonly بـui/cd/tab.py)، أو مو مرتبط بأي
    سطر أصلاً (يُفتح عادي بالنظام). يرجّع None لو ما لقى تطابق."""
    try:
        abs_path = os.path.abspath(path)
    except (TypeError, ValueError):
        return None
    conn = get_connection()
    rows = conn.execute("SELECT * FROM cd_documents WHERE file_path IS NOT NULL OR pdf_path IS NOT NULL").fetchall()
    conn.close()
    for row in rows:
        row = dict(row)
        for candidate in (row.get("file_path"), row.get("pdf_path")):
            if candidate and os.path.abspath(candidate) == abs_path:
                return row
    return None


def search_cd_documents(query="", limit=200):
    """يرجّع مستندات CD السابقة (الأحدث أولاً)، مع فلترة نصية اختيارية
    على اسم الراكب أو رقم البوردرو أو رقم الجواز."""
    conn = get_connection()
    if query:
        like = f"%{query}%"
        rows = conn.execute(
            """
            SELECT * FROM cd_documents
            WHERE passager LIKE ? OR dossier_no LIKE ? OR passport_no LIKE ?
            ORDER BY id DESC LIMIT ?
            """,
            (like, like, like, limit),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM cd_documents ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
