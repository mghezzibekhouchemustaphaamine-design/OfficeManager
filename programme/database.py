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
    # --- الزبائن + الشريط الجانبي المبني على قاعدة البيانات (راجع
    # docs/cd-clients-architecture.md وdocs/cd-clients-implementation-brief.md).
    # كلها بنفس نمط full_data_json/pdf_path أعلاه: PRAGMA table_info ثم
    # ALTER TABLE لو العمود ناقص — قواعد بيانات المستخدمين الموجودة أصلاً
    # تترقّى بسلاسة بلا فقدان بيانات.
    #
    # cd_documents.client_id: ربط الحالة بزبون (جدول clients) — بلا
    # FOREIGN KEY صريح (SQLite ما يدعم إضافتها بسهولة على جدول موجود؛
    # الربط منطقي بالكود بس، زي باقي الجدول).
    if "client_id" not in existing_cols:
        cur.execute("ALTER TABLE cd_documents ADD COLUMN client_id INTEGER")
    # cd_documents.updated_at: يتحدّث كل حفظ لاحق عبر update_cd_document
    # (مصدر "آخر تعديل" بالشريط الجانبي/السجل، بدل وقت الملف الفيزيائي).
    if "updated_at" not in existing_cols:
        cur.execute("ALTER TABLE cd_documents ADD COLUMN updated_at TEXT")
    existing_client_cols = {row[1] for row in cur.execute("PRAGMA table_info(clients)")}
    # clients.folder_name: اسم مجلد الزبون الفعلي على القرص — يُحسب مرة
    # وحدة عند إنشاء الزبون (create_client) ويبقى ثابتاً بعدها حتى لو
    # تغيّر اسم الزبون لاحقاً. تعديل اسم زبون **لا** يغيّر اسم مجلده:
    # يفادي إعادة نقل كل ملفاته كل مرة يتعدّل فيها اسم، وهو السلوك
    # المتوقَّع بأي نظام ملفات حقيقي (راجع مستند التصميم بند 3).
    if "folder_name" not in existing_client_cols:
        cur.execute("ALTER TABLE clients ADD COLUMN folder_name TEXT")
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


def _sanitize_folder_name(name):
    """اسم مجلد آمن مشتق من اسم الزبون — نفس أسلوب _named_path بـ
    ui/cd/document.py (أحرف/أرقام/مسافة/شرطة سفلية/شرطة فقط). يرجّع
    "client" لو ما بقي أي حرف صالح (اسم رموز بالكامل — نادر)."""
    safe = "".join(c for c in (name or "") if c.isalnum() or c in " _-").strip()
    return safe or "client"


def list_clients(query="", limit=50):
    """بحث بالاسم (LIKE) — يرجّع [{id, name, phone, ...}] مرتّبة أبجدياً
    (أنسب لمكوّن اختيار). query فاضي يرجّع الكل (بحد limit)."""
    conn = get_connection()
    if query:
        like = f"%{query}%"
        rows = conn.execute(
            "SELECT * FROM clients WHERE name LIKE ? ORDER BY name COLLATE NOCASE LIMIT ?",
            (like, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM clients ORDER BY name COLLATE NOCASE LIMIT ?", (limit,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_client(client_id):
    """صف زبون واحد (dict) أو None."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
    conn.close()
    return dict(row) if row is not None else None


def create_client(name, phone=None, email=None, address=None, notes=None):
    """يُنشئ زبوناً جديداً: يحسب folder_name مرة وحدة (sanitize نفس أسلوب
    _named_path)، يفحص تصادمه مع folder_name موجود أصلاً (يضيف _02، _03...
    تلقائياً — نفس اصطلاح تصادم اسم ملف CD)، يُدرج الصف ويرجّع id."""
    base = _sanitize_folder_name(name)
    conn = get_connection()
    existing = {
        (r[0] or "").casefold()
        for r in conn.execute("SELECT folder_name FROM clients WHERE folder_name IS NOT NULL")
    }
    folder_name = base
    n = 2
    while folder_name.casefold() in existing:
        folder_name = f"{base}_{n:02d}"
        n += 1
    cur = conn.execute(
        "INSERT INTO clients (name, phone, email, address, notes, folder_name) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (name, phone, email, address, notes, folder_name),
    )
    client_id = cur.lastrowid
    conn.commit()
    conn.close()
    return client_id


def client_has_documents(client_id):
    """True لو فيه أي سطر cd_documents مرتبط بـclient_id — يكفي سطر واحد."""
    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM cd_documents WHERE client_id=? LIMIT 1", (client_id,),
    ).fetchone()
    conn.close()
    return row is not None


def delete_client(client_id):
    """يرفض (يرجّع False، بلا حذف) لو client_has_documents — منع حذف زبون
    له أي مستند مرتبط (راجع مستند التصميم بند 4-و). غير هيك يحذف ويرجّع True."""
    if client_has_documents(client_id):
        return False
    conn = get_connection()
    conn.execute("DELETE FROM clients WHERE id=?", (client_id,))
    conn.commit()
    conn.close()
    return True


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
             eur_amount, dzd_amount, file_path, pdf_path, full_data_json, client_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.get("dossier_no"), record.get("passager"), record.get("passport_no"),
            record.get("doc_date"), record.get("agence"), record.get("guichet"),
            record.get("eur_amount"), record.get("dzd_amount"), record["file_path"],
            record.get("pdf_path"),
            serialize_cd_data(full_data) if full_data is not None else None,
            record.get("client_id"),
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
            eur_amount=?, dzd_amount=?, file_path=?, pdf_path=?, full_data_json=?,
            client_id=?, updated_at=datetime('now','localtime')
        WHERE id=?
        """,
        (
            record.get("dossier_no"), record.get("passager"), record.get("passport_no"),
            record.get("doc_date"), record.get("agence"), record.get("guichet"),
            record.get("eur_amount"), record.get("dzd_amount"), record["file_path"],
            record.get("pdf_path"),
            serialize_cd_data(full_data) if full_data is not None else None,
            record.get("client_id"),
            row_id,
        ),
    )
    conn.commit()
    conn.close()


def get_cd_document(row_id):
    """صف cd_documents واحد (dict) بمعرّفه، أو None — يُستخدم لما نفتح
    حالة من الشريط الجانبي (الشجرة صارت تحمل row_id مباشرة، فما نحتاج
    مطابقة مسار نص زي find_cd_document_by_path القديمة)."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM cd_documents WHERE id=?", (row_id,)).fetchone()
    conn.close()
    return dict(row) if row is not None else None


def search_cd_documents(query="", limit=200, client_id=None):
    """يرجّع مستندات CD السابقة (الأحدث أولاً)، مع فلترة نصية اختيارية
    على اسم الراكب أو رقم البوردرو أو رقم الجواز، وفلترة اختيارية
    بـclient_id (تشتغل بالمعرّف لا بمطابقة نص الاسم — حتى ما يلتبس
    زبونين بنفس الاسم). كل صف يحمل عموداً إضافياً client_name (LEFT
    JOIN clients) يحتاجه عمود "الزبون" بالسجل."""
    conn = get_connection()
    sql = [
        "SELECT cd.*, c.name AS client_name",
        "FROM cd_documents cd LEFT JOIN clients c ON cd.client_id = c.id",
    ]
    where = []
    params = []
    if query:
        like = f"%{query}%"
        where.append("(cd.passager LIKE ? OR cd.dossier_no LIKE ? OR cd.passport_no LIKE ?)")
        params += [like, like, like]
    if client_id is not None:
        where.append("cd.client_id = ?")
        params.append(client_id)
    if where:
        sql.append("WHERE " + " AND ".join(where))
    sql.append("ORDER BY cd.id DESC LIMIT ?")
    params.append(limit)
    rows = conn.execute("\n".join(sql), params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_cd_documents_for_tree():
    """كل صفوف cd_documents (id, file_path, pdf_path, client_id, doc_date,
    created_at, updated_at) + client_name وclient_folder_name (LEFT JOIN
    clients) — المصدر الوحيد اللي يبني منه الشريط الجانبي شجرته (راجع
    ui/common/file_explorer.py). بلا أي فلترة نصية: الشريط يبني الشجرة
    كاملة ثم يفلتر بصرياً وقت البحث."""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT cd.id, cd.file_path, cd.pdf_path, cd.client_id,
               cd.doc_date, cd.created_at, cd.updated_at,
               c.name AS client_name, c.folder_name AS client_folder_name
        FROM cd_documents cd
        LEFT JOIN clients c ON cd.client_id = c.id
        ORDER BY cd.id DESC
        """
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
