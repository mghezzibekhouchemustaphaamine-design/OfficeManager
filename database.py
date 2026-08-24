"""
طبقة الاتصال بقاعدة البيانات (SQLite) وإنشاء الجداول.
"""
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "office_system.db")


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
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        """
    )
    conn.commit()
    conn.close()


def log_cd_document(record):
    """يسجّل مستند CD مولَّد فعلياً بجدول cd_documents، للبحث/الأرشفة لاحقاً.

    record: dict فيه dossier_no, passager, passport_no, doc_date, agence,
    guichet, eur_amount, dzd_amount, file_path (كلها اختيارية إلا
    file_path)."""
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO cd_documents
            (dossier_no, passager, passport_no, doc_date, agence, guichet,
             eur_amount, dzd_amount, file_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.get("dossier_no"), record.get("passager"), record.get("passport_no"),
            record.get("doc_date"), record.get("agence"), record.get("guichet"),
            record.get("eur_amount"), record.get("dzd_amount"), record["file_path"],
        ),
    )
    conn.commit()
    conn.close()


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
